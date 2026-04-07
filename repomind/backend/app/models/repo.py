"""
Repository model — stores metadata about each GitHub repo a user ingests.

Plain English: This is the "repository record" in our database.
When you paste a GitHub URL, we create one row here to track it.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Enum as SAEnum, Text, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.db.database import Base


class RepoStatus(str, enum.Enum):
    """
    The lifecycle of a repository as it moves through our system.

    PENDING   → URL submitted, not yet cloned
    CLONING   → Actively downloading the repo from GitHub
    INDEXING  → Reading files, creating chunks, generating embeddings
    READY     → Fully indexed, ready for questions
    FAILED    → Something went wrong (network error, too large, etc.)
    """
    PENDING = "pending"
    CLONING = "cloning"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


class Repository(Base):
    __tablename__ = "repositories"

    # ── Identity ──────────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    github_url: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)   # e.g. "torvalds"
    name: Mapped[str] = mapped_column(String(255), nullable=False)    # e.g. "linux"
    full_name: Mapped[str] = mapped_column(String(512), nullable=False)  # "torvalds/linux"
    default_branch: Mapped[str] = mapped_column(String(100), default="main")

    # ── Status ────────────────────────────────────────────────────────────────
    status: Mapped[RepoStatus] = mapped_column(
        SAEnum(RepoStatus), default=RepoStatus.PENDING, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Stats ─────────────────────────────────────────────────────────────────
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    indexed_files: Mapped[int] = mapped_column(Integer, default=0)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)   # estimated token count
    repo_size_kb: Mapped[float] = mapped_column(Float, default=0.0)

    # ── GitHub Metadata ───────────────────────────────────────────────────────
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stars: Mapped[int] = mapped_column(Integer, default=0)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)  # HEAD SHA

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    chunks: Mapped[list["CodeChunk"]] = relationship(  # noqa: F821
        "CodeChunk", back_populates="repository", cascade="all, delete-orphan"
    )
    query_logs: Mapped[list["QueryLog"]] = relationship(  # noqa: F821
        "QueryLog", back_populates="repository", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Repository {self.full_name} [{self.status}]>"
