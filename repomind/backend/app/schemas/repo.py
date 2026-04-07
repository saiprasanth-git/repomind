"""
Pydantic schemas — define the shape of data coming IN and going OUT of the API.

Plain English: These are the "contracts" for our API.
- Request schemas: what the frontend must send to us
- Response schemas: what we send back to the frontend

Pydantic automatically validates all data and returns clear error messages
if anything is missing or the wrong type.
"""
from pydantic import BaseModel, HttpUrl, field_validator
from datetime import datetime
from typing import Optional
from uuid import UUID
import re

from app.models.repo import RepoStatus


# ── Request Schemas (what the frontend sends) ─────────────────────────────────

class IngestRepoRequest(BaseModel):
    """Request body for POST /repos — start indexing a new repository."""
    github_url: str

    @field_validator("github_url")
    @classmethod
    def validate_github_url(cls, v: str) -> str:
        v = v.strip()
        if not re.search(r"github\.com/[^/]+/[^/]+", v):
            raise ValueError(
                "Must be a valid GitHub repository URL "
                "(e.g. https://github.com/owner/repo)"
            )
        return v


# ── Response Schemas (what we send back) ──────────────────────────────────────

class RepoResponse(BaseModel):
    """Full repository details returned by GET /repos/{id}"""
    id: UUID
    github_url: str
    owner: str
    name: str
    full_name: str
    status: RepoStatus
    error_message: Optional[str]

    # Stats
    total_files: int
    indexed_files: int
    total_chunks: int
    total_tokens: int
    repo_size_kb: float

    # GitHub metadata
    description: Optional[str]
    language: Optional[str]
    stars: int

    # Timestamps
    created_at: datetime
    updated_at: datetime
    indexed_at: Optional[datetime]

    class Config:
        from_attributes = True  # Allows creating from SQLAlchemy model instances


class RepoStatusResponse(BaseModel):
    """Lightweight status response for polling during ingestion."""
    id: UUID
    status: RepoStatus
    indexed_files: int
    total_files: int
    total_chunks: int
    error_message: Optional[str]
    progress_percent: float

    @classmethod
    def from_repo(cls, repo) -> "RepoStatusResponse":
        progress = 0.0
        if repo.status == RepoStatus.CLONING:
            progress = 10.0
        elif repo.status == RepoStatus.INDEXING:
            if repo.total_files > 0:
                progress = 10.0 + (repo.indexed_files / repo.total_files * 80.0)
            else:
                progress = 20.0
        elif repo.status == RepoStatus.READY:
            progress = 100.0

        return cls(
            id=repo.id,
            status=repo.status,
            indexed_files=repo.indexed_files,
            total_files=repo.total_files,
            total_chunks=repo.total_chunks,
            error_message=repo.error_message,
            progress_percent=round(progress, 1),
        )


class RepoListResponse(BaseModel):
    """Paginated list of repositories."""
    repos: list[RepoResponse]
    total: int
    page: int
    page_size: int
