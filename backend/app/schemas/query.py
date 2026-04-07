"""
Query schemas — request/response shapes for asking questions about a repo.
"""
from pydantic import BaseModel, field_validator
from typing import Optional, Literal
from uuid import UUID
from datetime import datetime


class QueryRequest(BaseModel):
    """Request body for POST /repos/{id}/query"""
    question: str
    engine: Literal["rag", "long_context", "auto"] = "auto"
    # "auto" = we decide which engine to use based on repo size and question type

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 5:
            raise ValueError("Question must be at least 5 characters")
        if len(v) > 2000:
            raise ValueError("Question must be under 2000 characters")
        return v


class SourceReference(BaseModel):
    """A code file that was cited in answering a question."""
    file_path: str
    start_line: int
    end_line: int
    content_preview: str   # first 200 chars of the cited chunk
    similarity_score: Optional[float] = None  # for RAG results


class QueryResponse(BaseModel):
    """Response from POST /repos/{id}/query"""
    query_id: UUID
    question: str
    answer: str
    engine_used: str         # "rag" or "long_context"
    model: str               # e.g. "gemini-1.5-pro"
    sources: list[SourceReference]

    # Performance
    latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float

    created_at: datetime


class PatchRequest(BaseModel):
    """Request body for POST /repos/{id}/patch — generate a code fix."""
    description: str         # e.g. "Fix the SQL injection in the login function"
    target_file: Optional[str] = None  # Optional: constrain to a specific file

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("Description must be at least 10 characters")
        return v


class PatchResponse(BaseModel):
    """Response from POST /repos/{id}/patch"""
    query_id: UUID
    description: str
    patch: str               # Unified diff format (git diff style)
    affected_files: list[str]
    explanation: str         # Plain-English explanation of the change
    latency_ms: float
    created_at: datetime
