"""
Repository routes — HTTP endpoints for managing repositories.

GET  /repos           → list all indexed repos
POST /repos           → start indexing a new repo (returns immediately, runs in background)
GET  /repos/{id}      → get repo details
GET  /repos/{id}/status → poll ingestion progress
GET  /repos/{id}/tree → get file tree for the explorer sidebar
DELETE /repos/{id}    → remove a repo and all its chunks
"""
import asyncio
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete

from app.db.database import get_db
from app.models.repo import Repository, RepoStatus
from app.models.chunk import CodeChunk
from app.schemas.repo import (
    IngestRepoRequest,
    RepoResponse,
    RepoStatusResponse,
    RepoListResponse,
)
from app.ingestion.cloner import parse_github_url, get_repo_metadata
from app.ingestion.pipeline import run_ingestion_pipeline

logger = structlog.get_logger()
router = APIRouter(prefix="/repos", tags=["repositories"])


@router.get("", response_model=RepoListResponse)
async def list_repos(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List all repositories, most recently added first."""
    offset = (page - 1) * page_size

    count_result = await db.execute(select(func.count(Repository.id)))
    total = count_result.scalar()

    result = await db.execute(
        select(Repository)
        .order_by(Repository.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    repos = result.scalars().all()

    return RepoListResponse(
        repos=[RepoResponse.model_validate(r) for r in repos],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=RepoStatusResponse, status_code=202)
async def ingest_repo(
    request: IngestRepoRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Start ingesting a GitHub repository.

    Returns 202 Accepted immediately. Ingestion runs in the background.
    Poll GET /repos/{id}/status to track progress.
    """
    # Parse the URL to get owner/name
    try:
        owner, repo_name = parse_github_url(request.github_url)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Check if this repo is already indexed or being indexed
    existing = await db.execute(
        select(Repository).where(Repository.github_url == request.github_url)
    )
    existing_repo = existing.scalar_one_or_none()

    if existing_repo:
        if existing_repo.status == RepoStatus.READY:
            raise HTTPException(
                status_code=409,
                detail=f"Repository '{existing_repo.full_name}' is already indexed. "
                       "Delete it first to re-index."
            )
        if existing_repo.status in (RepoStatus.CLONING, RepoStatus.INDEXING):
            raise HTTPException(
                status_code=409,
                detail=f"Repository '{existing_repo.full_name}' is currently being indexed."
            )
        # Previous attempt failed — allow retry by reusing the same record
        repo = existing_repo
        repo.status = RepoStatus.PENDING
        repo.error_message = None
    else:
        # Create a new repo record
        repo = Repository(
            github_url=request.github_url,
            owner=owner,
            name=repo_name,
            full_name=f"{owner}/{repo_name}",
        )
        db.add(repo)

    await db.commit()
    await db.refresh(repo)

    # Start the ingestion pipeline as a background task
    # FastAPI's BackgroundTasks run AFTER the response is sent
    background_tasks.add_task(run_ingestion_pipeline, repo.id, request.github_url)

    logger.info("ingestion started", repo=f"{owner}/{repo_name}", repo_id=str(repo.id))

    return RepoStatusResponse.from_repo(repo)


@router.get("/{repo_id}", response_model=RepoResponse)
async def get_repo(repo_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get full details for a repository."""
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalar_one_or_none()

    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    return RepoResponse.model_validate(repo)


@router.get("/{repo_id}/status", response_model=RepoStatusResponse)
async def get_repo_status(repo_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Lightweight status endpoint for polling during ingestion.
    Returns progress percentage and current status.
    """
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalar_one_or_none()

    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    return RepoStatusResponse.from_repo(repo)


@router.get("/{repo_id}/tree")
async def get_repo_tree(repo_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Returns the file tree structure for the repository explorer sidebar.
    Built from the stored chunks (we don't need the original clone for this).
    """
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalar_one_or_none()

    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    if repo.status != RepoStatus.READY:
        raise HTTPException(
            status_code=400,
            detail=f"Repository is not ready yet (status: {repo.status})"
        )

    # Get all unique file paths from stored chunks
    files_result = await db.execute(
        select(CodeChunk.file_path, CodeChunk.language, CodeChunk.file_extension)
        .where(CodeChunk.repository_id == repo_id)
        .distinct(CodeChunk.file_path)
    )
    files = files_result.all()

    # Build nested tree structure
    tree = {}
    for file_path, language, extension in files:
        parts = file_path.split("/")
        current = tree
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                current[part] = {
                    "type": "file",
                    "language": language,
                    "extension": extension,
                    "path": file_path,
                }
            else:
                if part not in current:
                    current[part] = {"type": "directory", "children": {}}
                current = current[part].get("children", current[part])

    return {"tree": tree, "total_files": len(files)}


@router.delete("/{repo_id}", status_code=204)
async def delete_repo(repo_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Delete a repository and all its indexed chunks.
    This is irreversible — the repo will need to be re-indexed.
    """
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalar_one_or_none()

    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    await db.delete(repo)  # CASCADE deletes chunks and query_logs too
    await db.commit()

    logger.info("repository deleted", repo_id=str(repo_id), name=repo.full_name)
