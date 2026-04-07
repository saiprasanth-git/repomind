"""
Query Router — decides which engine to use for a given query.

Plain English: When the user selects "auto" mode, we decide whether
to use RAG or long-context based on:
  - How big the repo is (token count)
  - What type of question is being asked

This is one of the most interesting design decisions in RepoMind.
The router's decision logic is also what the research experiment validates.

Decision Logic:
  ┌─────────────────────────────────────────────────────┐
  │  Is the repo under 50k tokens?                      │
  │  YES → Long-Context (fast, cheap at this size)      │
  │                                                     │
  │  Is the question architectural? ("how does X work"  │
  │  "explain the overall structure")                   │
  │  YES → Long-Context (needs cross-file understanding)│
  │                                                     │
  │  Is the repo over 400k tokens?                      │
  │  YES → RAG (long-context would be too slow/expensive│
  │                                                     │
  │  Default → RAG (faster, cheaper for targeted queries│
  └─────────────────────────────────────────────────────┘
"""
import re
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.engines.base import BaseEngine, EngineResult
from app.engines.rag_engine import RAGEngine
from app.engines.long_context_engine import LongContextEngine
from app.models.repo import Repository

logger = structlog.get_logger()

# Question patterns that strongly suggest architectural/cross-file understanding
ARCHITECTURAL_PATTERNS = [
    r"\bhow does .+ work\b",
    r"\bexplain .+ architecture\b",
    r"\boverall structure\b",
    r"\bhow is .+ organized\b",
    r"\bwhat is the flow\b",
    r"\bdata flow\b",
    r"\bentry point\b",
    r"\bhow does .+ interact\b",
    r"\brelationship between\b",
    r"\bwhat happens when\b",
    r"\bwalk me through\b",
    r"\btrace .+ flow\b",
]

# Small repo threshold: below this, always use long-context
SMALL_REPO_TOKEN_THRESHOLD = 50_000

# Large repo threshold: above this, always use RAG
LARGE_REPO_TOKEN_THRESHOLD = 400_000


def _is_architectural_question(question: str) -> bool:
    """
    Returns True if the question requires understanding the full codebase structure.
    These questions benefit most from long-context — RAG retrieval can't see
    the relationships between distant files.
    """
    question_lower = question.lower()
    return any(
        re.search(pattern, question_lower)
        for pattern in ARCHITECTURAL_PATTERNS
    )


def _classify_question(question: str) -> str:
    """
    Classifies the question type for logging and experiment analysis.

    Categories:
    - navigation:    "where is X", "find the file for X"
    - explanation:   "how does X work", "explain X"
    - debug:         "why does X fail", "what's wrong with X"
    - patch:         "fix X", "change X to Y"
    - architecture:  "how is the system structured"
    """
    q = question.lower()

    if any(word in q for word in ["fix", "patch", "change", "update", "add", "remove", "refactor"]):
        return "patch"
    if any(word in q for word in ["why", "error", "fail", "bug", "issue", "wrong", "broken"]):
        return "debug"
    if any(word in q for word in ["where", "find", "locate", "which file"]):
        return "navigation"
    if any(word in q for word in ["how does", "explain", "walk", "describe", "what is"]):
        return "explanation"
    if _is_architectural_question(q):
        return "architecture"

    return "general"


class QueryRouter:
    """
    Routes queries to the appropriate engine and logs the decision.

    This is instantiated once and reused across requests.
    """

    def __init__(self):
        self._rag = RAGEngine()
        self._long_context = LongContextEngine()

    async def route(
        self,
        repo_id: UUID,
        question: str,
        requested_engine: str,
        db: AsyncSession,
    ) -> tuple[BaseEngine, str, str]:
        """
        Determines which engine to use.

        Args:
            repo_id:           Repository UUID
            question:          The user's question
            requested_engine:  "rag", "long_context", or "auto"
            db:                Database session

        Returns:
            (engine_instance, engine_name, question_type)
        """
        question_type = _classify_question(question)

        # If the user explicitly chose an engine, respect it
        if requested_engine == "rag":
            return self._rag, "rag", question_type
        if requested_engine == "long_context":
            return self._long_context, "long_context", question_type

        # Auto-routing logic
        repo_result = await db.execute(
            select(Repository).where(Repository.id == repo_id)
        )
        repo = repo_result.scalar_one_or_none()
        total_tokens = repo.total_tokens if repo else 0

        decision = _auto_route_decision(question, total_tokens)

        logger.info(
            "auto-routed query",
            decision=decision,
            question_type=question_type,
            total_tokens=total_tokens,
            question=question[:80],
        )

        engine = self._long_context if decision == "long_context" else self._rag
        return engine, decision, question_type


def _auto_route_decision(question: str, total_tokens: int) -> str:
    """
    Pure function for routing decision — easy to unit test.

    Returns "rag" or "long_context".
    """
    # Small repos: long-context is fast and cheap, always use it
    if total_tokens < SMALL_REPO_TOKEN_THRESHOLD:
        return "long_context"

    # Very large repos: RAG is the only practical option
    if total_tokens > LARGE_REPO_TOKEN_THRESHOLD:
        return "rag"

    # Mid-size repos: use question type to decide
    if _is_architectural_question(question):
        return "long_context"

    # Default for mid-size repos: RAG (faster, targeted)
    return "rag"


# Module-level singleton — created once, reused across all requests
query_router = QueryRouter()
