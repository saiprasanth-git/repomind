"""
File Parser — walks a cloned repo, reads every supported file,
and produces a list of raw file records ready for chunking.

Plain English: After downloading a repo, we walk through every folder
and file like a file explorer. For each code file we understand, we read
its contents and record where it is. We skip generated files, binary files,
and folders like node_modules that contain library code we didn't write.
"""
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator

import structlog

from app.core.config import settings

logger = structlog.get_logger()


@dataclass
class ParsedFile:
    """
    Represents one file from the repository after it has been read.

    file_path:   Relative path inside the repo, e.g. "src/auth/login.py"
    content:     Full text content of the file
    extension:   File extension, e.g. ".py"
    size_bytes:  File size in bytes
    content_hash: SHA-256 hash of the content (used to detect unchanged files)
    language:    Detected programming language
    """
    file_path: str
    content: str
    extension: str
    size_bytes: int
    content_hash: str
    language: str = "unknown"
    line_count: int = 0


# Map file extensions to human-readable language names
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (React)",
    ".js": "JavaScript",
    ".jsx": "JavaScript (React)",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".cpp": "C++",
    ".c": "C",
    ".h": "C/C++ Header",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".md": "Markdown",
    ".txt": "Text",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
    ".sql": "SQL",
    ".sh": "Shell",
    ".dockerfile": "Dockerfile",
    ".tf": "Terraform",
}


def _should_skip_path(path: Path, repo_root: Path) -> bool:
    """
    Returns True if we should skip this path entirely.

    We skip:
    - Excluded directories (node_modules, .git, etc.)
    - Files whose extension we don't support
    - Files that are too large (likely generated or binary)
    """
    # Check if any part of the path is an excluded directory
    relative = path.relative_to(repo_root)
    parts = set(relative.parts)
    if parts.intersection(set(settings.EXCLUDED_DIRS)):
        return True

    # For files: check extension and size
    if path.is_file():
        if path.suffix.lower() not in settings.SUPPORTED_EXTENSIONS:
            return True

        size_kb = path.stat().st_size / 1024
        if size_kb > settings.MAX_FILE_SIZE_KB:
            logger.debug("skipping large file", path=str(relative), size_kb=round(size_kb))
            return True

    return False


def _compute_hash(content: str) -> str:
    """SHA-256 hash of file content, used to detect unchanged files."""
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()


def parse_repository(repo_path: Path) -> Generator[ParsedFile, None, None]:
    """
    Walks a cloned repository and yields ParsedFile objects for every
    supported, readable file.

    This is a generator — it yields files one at a time rather than loading
    all of them into memory at once. Important for large repos.

    Args:
        repo_path: Path to the cloned repository on disk

    Yields:
        ParsedFile for each readable, supported file
    """
    total_files = 0
    skipped_files = 0
    error_files = 0

    for root, dirs, files in os.walk(repo_path):
        root_path = Path(root)

        # Prune excluded directories in-place so os.walk doesn't descend into them
        # This is more efficient than checking every file's path parts
        dirs[:] = [
            d for d in dirs
            if d not in settings.EXCLUDED_DIRS and not d.startswith(".")
        ]

        for filename in files:
            file_path = root_path / filename
            total_files += 1

            if _should_skip_path(file_path, repo_path):
                skipped_files += 1
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")

                # Skip effectively empty files
                if len(content.strip()) < 10:
                    skipped_files += 1
                    continue

                relative_path = str(file_path.relative_to(repo_path))
                extension = file_path.suffix.lower()
                language = EXTENSION_TO_LANGUAGE.get(extension, "unknown")

                yield ParsedFile(
                    file_path=relative_path,
                    content=content,
                    extension=extension,
                    size_bytes=file_path.stat().st_size,
                    content_hash=_compute_hash(content),
                    language=language,
                    line_count=content.count("\n") + 1,
                )

            except Exception as e:
                error_files += 1
                logger.warning(
                    "could not read file",
                    path=str(file_path.relative_to(repo_path)),
                    error=str(e)
                )

    logger.info(
        "repository parsing complete",
        total=total_files,
        indexed=total_files - skipped_files - error_files,
        skipped=skipped_files,
        errors=error_files,
    )


def get_file_tree(repo_path: Path) -> dict:
    """
    Returns a nested dictionary representing the repository's file tree.
    Used by the frontend to render the file explorer sidebar.

    Example output:
    {
      "src": {
        "auth": {
          "login.py": {"type": "file", "language": "Python", "size_bytes": 1234},
        }
      }
    }
    """
    tree = {}

    for root, dirs, files in os.walk(repo_path):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if d not in settings.EXCLUDED_DIRS and not d.startswith(".")]

        relative_root = root_path.relative_to(repo_path)
        parts = list(relative_root.parts)

        # Navigate to the right place in the tree
        current = tree
        for part in parts:
            if part not in current:
                current[part] = {}
            current = current[part]

        for filename in files:
            file_path = root_path / filename
            if _should_skip_path(file_path, repo_path):
                continue
            ext = file_path.suffix.lower()
            current[filename] = {
                "type": "file",
                "language": EXTENSION_TO_LANGUAGE.get(ext, "unknown"),
                "size_bytes": file_path.stat().st_size,
                "extension": ext,
            }

    return tree
