"""
RAG Engine — Retrieval-Augmented Generation for codebase Q&A.

Plain English: When you ask a question, we first SEARCH our database for
the most relevant code chunks, then send ONLY those chunks to the AI.

This is like asking a librarian to find the relevant chapters BEFORE
you read them — instead of reading the entire library.

The key steps:
  1. Embed the question (convert it to a vector)
  2. Search pgvector for the most similar chunks (cosine similarity)
  3. Build a context string from the top-K chunks
  4. Send context + question to Gemini/GPT-4o
  5. Return the answer with source citations

Strengths:  Fast, cheap, scales to any repo size
Weaknesses: Can miss connections between distant parts of the codebase
"""
import time
from uuid import UUID

import structlog
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.core.config import settings
from app.engines.base import BaseEngine, EngineResult, SourceReference
from app.engines.prompts import (
    RAG_SYSTEM_PROMPT,
    RAG_QUERY_TEMPLATE,
    PATCH_SYSTEM_PROMPT,
    PATCH_QUERY_TEMPLATE,
)
from app.ingestion.embedder import embed_query
from app.models.chunk import CodeChunk
from app.models.repo import Repository

logger = structlog.get_logger()


class RAGEngine(BaseEngine):
    """
    Retrieval-Augmented Generation engine.

    Uses pgvector's cosine similarity search to find the most relevant
    code chunks for a question, then generates an answer from those chunks.
    """

    def __init__(self, model: str | None = None):
        self.model_name = model or settings.GEMINI_MODEL
        self._llm = None

    def _get_llm(self):
        """Lazy-initialize the LLM client."""
        if self._llm is None:
            if "gemini" in self.model_name:
                self._llm = ChatGoogleGenerativeAI(
                    model=self.model_name,
                    google_api_key=settings.GOOGLE_API_KEY,
                    temperature=0.1,      # Low temp = more focused, less creative
                    max_output_tokens=4096,
                )
            else:
                self._llm = ChatOpenAI(
                    model=self.model_name,
                    api_key=settings.OPENAI_API_KEY,
                    temperature=0.1,
                    max_tokens=4096,
                )
        return self._llm

    async def _retrieve_chunks(
        self,
        repo_id: UUID,
        question: str,
        db: AsyncSession,
        top_k: int | None = None,
    ) -> list[tuple[CodeChunk, float]]:
        """
        Retrieves the top-K most relevant chunks for a question using pgvector.

        Returns a list of (chunk, similarity_score) tuples, sorted by relevance.

        The SQL uses the `<=>` operator — pgvector's cosine distance operator.
        Cosine distance = 1 - cosine similarity, so lower distance = more similar.
        We convert to similarity (1 - distance) for human-readable scores.
        """
        k = top_k or settings.RAG_TOP_K

        # Step 1: Embed the question
        query_embedding = await embed_query(question)

        # Step 2: Vector similarity search using pgvector
        # The <=> operator computes cosine distance between vectors
        # We filter by repository_id first (uses B-tree index) then rank by distance
        similarity_query = text("""
            SELECT
                id,
                file_path,
                content,
                start_line,
                end_line,
                language,
                1 - (embedding <=> CAST(:query_embedding AS vector)) AS similarity_score
            FROM code_chunks
            WHERE repository_id = :repo_id
              AND embedding IS NOT NULL
              AND 1 - (embedding <=> CAST(:query_embedding AS vector)) >= :threshold
            ORDER BY embedding <=> CAST(:query_embedding AS vector)
            LIMIT :top_k
        """)

        result = await db.execute(
            similarity_query,
            {
                "query_embedding": str(query_embedding),
                "repo_id": str(repo_id),
                "threshold": settings.RAG_SIMILARITY_THRESHOLD,
                "top_k": k,
            }
        )
        rows = result.fetchall()

        # Fetch full chunk objects for the retrieved IDs
        if not rows:
            return []

        chunk_ids = [row.id for row in rows]
        scores = {row.id: row.similarity_score for row in rows}

        chunks_result = await db.execute(
            select(CodeChunk).where(CodeChunk.id.in_(chunk_ids))
        )
        chunks = {c.id: c for c in chunks_result.scalars().all()}

        # Return sorted by similarity score (highest first)
        return sorted(
            [(chunks[cid], scores[cid]) for cid in chunk_ids if cid in chunks],
            key=lambda x: x[1],
            reverse=True,
        )

    def _build_context(self, chunk_scores: list[tuple[CodeChunk, float]]) -> str:
        """
        Formats retrieved chunks into a context string for the LLM.

        Each chunk gets a header showing its file path and line numbers,
        making it easy for the LLM to cite sources accurately.
        """
        parts = []
        for i, (chunk, score) in enumerate(chunk_scores, 1):
            parts.append(
                f"[{i}] {chunk.file_path} (lines {chunk.start_line}-{chunk.end_line}, "
                f"relevance: {score:.2f})\n"
                f"```{chunk.language or ''}\n"
                f"{chunk.content}\n"
                f"```"
            )
        return "\n\n---\n\n".join(parts)

    def _parse_token_usage(self, response) -> tuple[int, int]:
        """Extracts input/output token counts from the LLM response."""
        try:
            usage = response.usage_metadata
            return usage.input_tokens, usage.output_tokens
        except Exception:
            # Fallback estimate if usage metadata isn't available
            return 0, 0

    async def query(
        self,
        repo_id: UUID,
        question: str,
        db: AsyncSession,
    ) -> EngineResult:
        """
        Answer a question using RAG.

        Full flow:
          embed question → pgvector search → build context → LLM call → parse response
        """
        start_time = time.time()
        log = logger.bind(engine="rag", repo_id=str(repo_id))

        log.info("rag query started", question=question[:80])

        # Fetch repo info for the system prompt
        repo_result = await db.execute(
            select(Repository).where(Repository.id == repo_id)
        )
        repo = repo_result.scalar_one_or_none()
        if not repo:
            raise ValueError(f"Repository {repo_id} not found")

        # Retrieve relevant chunks
        chunk_scores = await self._retrieve_chunks(repo_id, question, db)

        if not chunk_scores:
            log.warning("no chunks retrieved above threshold")
            return EngineResult(
                answer=(
                    "I couldn't find relevant code for your question in this repository. "
                    "Try rephrasing or asking about a specific file or component."
                ),
                sources=[],
                engine_used="rag",
                model=self.model_name,
                input_tokens=0,
                output_tokens=0,
                estimated_cost_usd=0.0,
                chunks_retrieved=0,
            )

        log.info("chunks retrieved", count=len(chunk_scores))

        # Build context string
        context = self._build_context(chunk_scores)

        # Build messages
        system = RAG_SYSTEM_PROMPT.format(repo_full_name=repo.full_name)
        human = RAG_QUERY_TEMPLATE.format(context=context, question=question)

        # Call LLM
        llm = self._get_llm()
        messages = [SystemMessage(content=system), HumanMessage(content=human)]

        response = await llm.ainvoke(messages)
        answer = response.content

        input_tokens, output_tokens = self._parse_token_usage(response)
        latency_ms = (time.time() - start_time) * 1000

        log.info(
            "rag query complete",
            latency_ms=round(latency_ms),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        # Build source references for the UI
        sources = [
            SourceReference(
                file_path=chunk.file_path,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                content_preview=chunk.content[:300],
                similarity_score=round(score, 3),
            )
            for chunk, score in chunk_scores[:5]  # Show top 5 sources in UI
        ]

        return EngineResult(
            answer=answer,
            sources=sources,
            engine_used="rag",
            model=self.model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=self._estimate_cost(self.model_name, input_tokens, output_tokens),
            chunks_retrieved=len(chunk_scores),
        )

    async def generate_patch(
        self,
        repo_id: UUID,
        description: str,
        target_file: str | None,
        db: AsyncSession,
    ) -> EngineResult:
        """
        Generate a code patch using RAG to find the relevant files.

        For patches, we retrieve more chunks (top 20) and optionally
        filter to a specific file if provided.
        """
        start_time = time.time()
        log = logger.bind(engine="rag_patch", repo_id=str(repo_id))
        log.info("patch generation started", description=description[:80])

        repo_result = await db.execute(select(Repository).where(Repository.id == repo_id))
        repo = repo_result.scalar_one_or_none()
        if not repo:
            raise ValueError(f"Repository {repo_id} not found")

        # For patches, we retrieve more chunks to understand the full context
        chunk_scores = await self._retrieve_chunks(repo_id, description, db, top_k=20)

        # If a target file is specified, prioritize its chunks
        if target_file:
            file_chunks = [(c, s) for c, s in chunk_scores if target_file in c.file_path]
            other_chunks = [(c, s) for c, s in chunk_scores if target_file not in c.file_path]
            chunk_scores = file_chunks + other_chunks[:5]  # file chunks + 5 for context

        context = self._build_context(chunk_scores[:15])

        target_hint = f"\nFocus the patch on file: `{target_file}`" if target_file else ""

        system = PATCH_SYSTEM_PROMPT.format(repo_full_name=repo.full_name)
        human = PATCH_QUERY_TEMPLATE.format(
            context=context,
            description=description,
            target_file_hint=target_hint,
        )

        llm = self._get_llm()
        messages = [SystemMessage(content=system), HumanMessage(content=human)]
        response = await llm.ainvoke(messages)

        answer = response.content
        input_tokens, output_tokens = self._parse_token_usage(response)

        # Extract affected files from the patch output
        affected_files = list({
            chunk.file_path for chunk, _ in chunk_scores[:5]
        })

        sources = [
            SourceReference(
                file_path=chunk.file_path,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                content_preview=chunk.content[:300],
                similarity_score=round(score, 3),
            )
            for chunk, score in chunk_scores[:5]
        ]

        log.info(
            "patch generation complete",
            latency_ms=round((time.time() - start_time) * 1000),
        )

        return EngineResult(
            answer=answer,
            sources=sources,
            engine_used="rag",
            model=self.model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=self._estimate_cost(self.model_name, input_tokens, output_tokens),
            chunks_retrieved=len(chunk_scores),
            metadata={"affected_files": affected_files},
        )
