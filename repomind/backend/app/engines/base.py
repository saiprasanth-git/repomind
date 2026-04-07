"""
Base engine interface — defines the contract that both RAG and Long-Context engines must follow.

Plain English: Both engines answer the same question, just differently.
This "contract" (called an abstract base class) ensures both engines:
- Accept the same inputs
- Return the same output format
- Can be swapped without changing any other code

Think of it like a power outlet. Every device has the same two-pin interface,
regardless of whether it's a phone charger or a toaster.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class SourceReference:
    """
    A piece of code that was used to generate an answer.
    Shown to the user as clickable citations below the answer.
    """
    file_path: str
    start_line: int
    end_line: int
    content_preview: str        # First 300 chars of the chunk
    similarity_score: float = 0.0  # 0.0 for long-context (no retrieval step)


@dataclass
class EngineResult:
    """
    Unified result returned by both engines.
    The API layer serializes this into the HTTP response.
    """
    answer: str
    sources: list[SourceReference]
    engine_used: str            # "rag" or "long_context"
    model: str                  # e.g. "gemini-1.5-pro"
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    chunks_retrieved: int = 0   # > 0 for RAG, 0 for long-context
    metadata: dict = field(default_factory=dict)


class BaseEngine(ABC):
    """
    Abstract base class for RepoMind query engines.

    Both RAGEngine and LongContextEngine inherit from this.
    The QueryRouter uses this interface to call either engine transparently.
    """

    @abstractmethod
    async def query(
        self,
        repo_id: UUID,
        question: str,
        db: AsyncSession,
    ) -> EngineResult:
        """
        Answer a natural language question about a repository.

        Args:
            repo_id:  UUID of the indexed repository
            question: Plain English question from the user
            db:       Database session for reading chunks

        Returns:
            EngineResult with answer, sources, and performance metrics
        """
        ...

    @abstractmethod
    async def generate_patch(
        self,
        repo_id: UUID,
        description: str,
        target_file: str | None,
        db: AsyncSession,
    ) -> EngineResult:
        """
        Generate a unified diff patch based on a natural language description.

        Args:
            repo_id:      UUID of the indexed repository
            description:  What to fix/change, in plain English
            target_file:  Optional file path to constrain the patch to
            db:           Database session

        Returns:
            EngineResult with the patch in unified diff format as the answer
        """
        ...

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """
        Estimates the USD cost of an LLM call based on current pricing.

        Prices as of April 2026:
        - Gemini 1.5 Pro:   $1.25/1M input, $5.00/1M output  (≤128k tokens)
        - Gemini 1.5 Pro:   $2.50/1M input, $10.00/1M output (>128k tokens)
        - Gemini 1.5 Flash: $0.075/1M input, $0.30/1M output
        - GPT-4o:           $2.50/1M input, $10.00/1M output
        """
        pricing = {
            "gemini-1.5-pro":   (1.25 / 1_000_000, 5.00 / 1_000_000),
            "gemini-1.5-flash": (0.075 / 1_000_000, 0.30 / 1_000_000),
            "gpt-4o":           (2.50 / 1_000_000, 10.00 / 1_000_000),
        }
        input_price, output_price = pricing.get(model, (0.002 / 1_000, 0.002 / 1_000))

        # Long-context surcharge: Gemini Pro costs 2x for prompts > 128k tokens
        if "gemini-1.5-pro" in model and input_tokens > 128_000:
            input_price *= 2
            output_price *= 2

        return round(input_price * input_tokens + output_price * output_tokens, 6)
