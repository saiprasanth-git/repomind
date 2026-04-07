"""
QueryLog model — records every question asked and the answer given.

Plain English: Every time someone asks a question about a repo, we save:
- the question
- which engine answered it (RAG or Long-Context)
- the answer
- how long it took
- how many tokens it cost

This powers the research experiment — we need this data to compare the two approaches.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, Float, ForeignKey, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class QueryLog(Base):
    __tablename__ = "query_logs"

    # ── Identity ──────────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Relationship ──────────────────────────────────────────────────────────
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    repository: Mapped["Repository"] = relationship(  # noqa: F821
        "Repository", back_populates="query_logs"
    )

    # ── The Question ─────────────────────────────────────────────────────────
    question: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    # e.g. "navigation", "explanation", "patch", "debug", "architecture"

    # ── The Engine Used ───────────────────────────────────────────────────────
    engine: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    # "rag" or "long_context"

    model: Mapped[str] = mapped_column(String(100), nullable=False)
    # e.g. "gemini-1.5-pro", "gpt-4o"

    # ── The Answer ────────────────────────────────────────────────────────────
    answer: Mapped[str] = mapped_column(Text, nullable=False)

    source_files: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )
    # List of file paths cited in the answer: ["src/auth/login.py", ...]

    chunks_retrieved: Mapped[int] = mapped_column(Integer, default=0)
    # For RAG: how many chunks were retrieved. For long-context: 0.

    # ── Performance Metrics ───────────────────────────────────────────────────
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    # Total time from question to answer in milliseconds

    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # ── Eval Scores (set by experiment harness) ───────────────────────────────
    # These are filled in during the research experiment, not during normal usage
    accuracy_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 0.0 to 1.0 — how correct the answer was
    faithfulness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 0.0 to 1.0 — did the answer stay grounded in actual code (no hallucination)?
    human_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 1-5 star rating, set manually during evaluation

    # ── Flags ────────────────────────────────────────────────────────────────
    was_cached: Mapped[bool] = mapped_column(Boolean, default=False)
    is_experiment_run: Mapped[bool] = mapped_column(Boolean, default=False)
    # True if this query was part of the research experiment

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )

    def __repr__(self) -> str:
        return f"<QueryLog {self.engine} | {self.question[:50]}...>"
