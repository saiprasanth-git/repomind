"""
Repository Cloner — clones a GitHub repo to local disk for processing.

Plain English: When you give us a GitHub URL, this module downloads
the entire codebase to a temporary folder on our server so we can read
every file. Think of it like "Save Page As" but for an entire codebase.
"""
import re
import shutil
import os
from pathlib import Path
from urllib.parse import urlparse

import git
import structlog
from github import Github

from app.core.config import settings

logger = structlog.get_logger()


def parse_github_url(url: str) -> tuple[str, str]:
    """
    Extracts owner and repo name from a GitHub URL.

    Examples:
        "https://github.com/torvalds/linux"      → ("torvalds", "linux")
        "https://github.com/openai/openai-python" → ("openai", "openai-python")

    Raises ValueError if the URL is not a valid GitHub repo URL.
    """
    url = url.strip().rstrip("/")

    # Handle both HTTPS and SSH formats
    patterns = [
        r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$",
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            owner, repo = match.group(1), match.group(2)
            return owner, repo

    raise ValueError(
        f"Could not parse GitHub URL: '{url}'. "
        "Expected format: https://github.com/owner/repo"
    )


def get_repo_metadata(owner: str, repo_name: str) -> dict:
    """
    Fetches repository metadata from the GitHub API.
    Returns description, stars, default branch, etc.

    If no GITHUB_TOKEN is set, this works but with rate limiting (60 req/hour).
    With a token: 5,000 req/hour.
    """
    try:
        gh = Github(settings.GITHUB_TOKEN) if settings.GITHUB_TOKEN else Github()
        repo = gh.get_repo(f"{owner}/{repo_name}")

        return {
            "description": repo.description or "",
            "language": repo.language or "Unknown",
            "stars": repo.stargazers_count,
            "default_branch": repo.default_branch,
            "size_kb": repo.size,
        }
    except Exception as e:
        logger.warning("could not fetch github metadata", error=str(e))
        # Non-fatal — we can still clone and index without metadata
        return {
            "description": "",
            "language": "Unknown",
            "stars": 0,
            "default_branch": "main",
            "size_kb": 0,
        }


async def clone_repository(github_url: str, repo_id: str) -> Path:
    """
    Clones a GitHub repository to a local temporary directory.

    Args:
        github_url: Full GitHub HTTPS URL
        repo_id: UUID of the repository record (used for the folder name)

    Returns:
        Path to the cloned repository on disk

    Raises:
        ValueError: If URL is invalid
        RuntimeError: If clone fails (network error, private repo, etc.)
    """
    owner, repo_name = parse_github_url(github_url)

    clone_dir = Path(settings.CLONE_BASE_DIR) / str(repo_id)

    # Clean up any previous failed clone attempt
    if clone_dir.exists():
        shutil.rmtree(clone_dir)

    clone_dir.mkdir(parents=True, exist_ok=True)

    log = logger.bind(repo=f"{owner}/{repo_name}", clone_dir=str(clone_dir))
    log.info("starting clone")

    try:
        # Build the clone URL — inject GitHub token if available for private repos
        if settings.GITHUB_TOKEN:
            clone_url = f"https://{settings.GITHUB_TOKEN}@github.com/{owner}/{repo_name}.git"
        else:
            clone_url = f"https://github.com/{owner}/{repo_name}.git"

        # depth=1 = shallow clone (only latest commit, much faster)
        # We don't need git history for code understanding
        repo = git.Repo.clone_from(
            clone_url,
            clone_dir,
            depth=1,
            single_branch=True,
        )

        commit_sha = repo.head.commit.hexsha
        log.info("clone complete", commit_sha=commit_sha[:8])

        return clone_dir

    except git.GitCommandError as e:
        log.error("clone failed", error=str(e))
        # Clean up partial clone
        if clone_dir.exists():
            shutil.rmtree(clone_dir)
        raise RuntimeError(
            f"Failed to clone repository '{owner}/{repo_name}'. "
            "Check that the URL is correct and the repo is public."
        ) from e


def cleanup_clone(repo_id: str) -> None:
    """
    Deletes the local clone after indexing is complete.
    We don't keep repos on disk — they live in the database as chunks.
    """
    clone_dir = Path(settings.CLONE_BASE_DIR) / str(repo_id)
    if clone_dir.exists():
        shutil.rmtree(clone_dir)
        logger.info("cleaned up clone", repo_id=repo_id)
