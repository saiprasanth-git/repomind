"""
CodeChunk model — stores individual pieces of code with their vector embeddings.

Plain English: We cut every file into small pieces (like paragraphs in a book),
then create a numerical "fingerprint" of each piece. When you ask a question,
we find the pieces whose fingerprints are most similar to your question's fingerprint.
That's how we find the right code without reading the whole repo every time.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, Float, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector

from app.db.database import Base
from app.core.config import settings


class CodeChunk(Base):
    __tablename__ = "code_chunks"

    # ── Identity ──────────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Relationship to Repository ────────────────────────────────────────────
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    repository: Mapped["Repository"] = relationship(  # noqa: F821
        "Repository", back_populates="chunks"
    )

    # ── Location ──────────────────────────────────────────────────────────────
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    # e.g. "src/auth/login.py"
    file_extension: Mapped[str] = mapped_column(String(20), nullable=False)
    # e.g. ".py"
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # which chunk within the file (0, 1, 2...)
    start_line: Mapped[int] = mapped_column(Integer, default=0)
    end_line: Mapped[int] = mapped_column(Integer, default=0)

    # ── Content ───────────────────────────────────────────────────────────────
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # The actual code text for this chunk

    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # SHA-256 of content — lets us skip re-indexing unchanged files

    token_count: Mapped[int] = mapped_column(Integer, default=0)
    # Estimated number of LLM tokens in this chunk

    # ── The Vector Embedding ──────────────────────────────────────────────────
    # This is the core of the RAG system.
    # 768 dimensions = the output size of Google's text-embedding-004 model.
    # Each dimension is a float that captures some semantic meaning of the code.
    # Two chunks with similar meaning will have vectors that are "close" together
    # in this 768-dimensional space — which is how we do similarity search.
    embedding: Mapped[list[float]] = mapped_column(
        Vector(768), nullable=True  # nullable during ingestion, set before chunk is used
    )

    # ── Metadata ─────────────────────────────────────────────────────────────
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # detected programming language of the file

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # AI-generated one-sentence summary of what this chunk does (generated lazily)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # ── Indexes ───────────────────────────────────────────────────────────────
    __table_args__ = (
        # HNSW index on the embedding column for fast approximate nearest-neighbor search.
        # Without this, finding similar chunks requires comparing against EVERY chunk.
        # With HNSW, it's sub-millisecond even with millions of chunks.
        Index(
            "ix_code_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # Standard B-tree index for filtering by repository
        Index("ix_code_chunks_repo_file", "repository_id", "file_path"),
    )

    def __repr__(self) -> str:
        return f"<CodeChunk {self.file_path}:{self.chunk_index}>"
