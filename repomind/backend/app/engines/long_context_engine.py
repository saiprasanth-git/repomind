"""
Long-Context Engine — sends the ENTIRE repository to Gemini 1.5 Pro.

Plain English: Instead of searching for relevant parts (like RAG),
this engine reads the WHOLE codebase before answering — like a developer
who has memorized every file before answering your question.

Gemini 1.5 Pro supports up to 2,000,000 tokens of context — enough to
hold most real-world codebases in a single prompt.

Strengths:  No retrieval errors, sees all cross-file connections
Weaknesses: Slower (more tokens to process), more expensive, hits limits
            on very large repos (>500k tokens ≈ ~2M characters)

This engine is the core of the research experiment — we compare its
accuracy against RAG to find where each approach wins.
"""
import time
from uuid import UUID

import structlog
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.engines.base import BaseEngine, EngineResult, SourceReference
from app.engines.prompts import (
    LONG_CONTEXT_SYSTEM_PROMPT,
    LONG_CONTEXT_QUERY_TEMPLATE,
    PATCH_SYSTEM_PROMPT,
    PATCH_QUERY_TEMPLATE,
)
from app.models.chunk import CodeChunk
from app.models.repo import Repository

logger = structlog.get_logger()


class LongContextEngine(BaseEngine):
    """
    Long-context engine using Gemini 1.5 Pro's 2M token context window.

    Assembles the entire repository into a single prompt, sorted by file path
    for consistent ordering. No retrieval step — the model sees everything.
    """

    def __init__(self, model: str | None = None):
        self.model_name = model or settings.GEMINI_MODEL
        self._llm = None

    def _get_llm(self):
        """
        Lazy-initialize Gemini with settings optimized for long-context tasks.

        Key setting: max_output_tokens=8192 — long-context questions often need
        more detailed answers since the model has seen the full codebase.
        """
        if self._llm is None:
            self._llm = ChatGoogleGenerativeAI(
                model=self.model_name,
                google_api_key=settings.GOOGLE_API_KEY,
                temperature=0.05,           # Very low temp — we want precise answers
                max_output_tokens=8192,
                # These settings help with very long prompts:
                convert_system_message_to_human=False,
            )
        return self._llm

    async def _assemble_full_context(
        self,
        repo_id: UUID,
        db: AsyncSession,
    ) -> tuple[str, int, list[str]]:
        """
        Assembles all chunks into a single context string.

        Strategy:
        1. Group chunks by file path (to reconstruct full files)
        2. Sort files alphabetically (consistent ordering aids model navigation)
        3. Sort chunks within each file by chunk_index
        4. Concatenate with clear file separators
        5. Truncate if total tokens exceed the safety limit

        Returns:
            (full_context_string, estimated_token_count, list_of_file_paths)
        """
        # Fetch all chunks for this repo, ordered for reassembly
        result = await db.execute(
            select(CodeChunk)
            .where(CodeChunk.repository_id == repo_id)
            .order_by(CodeChunk.file_path, CodeChunk.chunk_index)
        )
        chunks = result.scalars().all()

        if not chunks:
            return "", 0, []

        # Group by file path
        files: dict[str, list[CodeChunk]] = {}
        for chunk in chunks:
            if chunk.file_path not in files:
                files[chunk.file_path] = []
            files[chunk.file_path].append(chunk)

        # Build the full context, file by file
        parts = []
        total_estimated_tokens = 0
        file_paths = sorted(files.keys())

        for file_path in file_paths:
            file_chunks = files[file_path]
            # Sort by chunk index to maintain original file order
            file_chunks.sort(key=lambda c: c.chunk_index)

            # Use the language from the first chunk for syntax highlighting hint
            language = file_chunks[0].language or ""

            # Reconstruct file content from chunks
            # Note: We strip the "# File: path" header we added during chunking
            # to avoid redundancy (we add a cleaner header here)
            file_content_parts = []
            for chunk in file_chunks:
                content = chunk.content
                # Remove the header we prepended during chunking
                if content.startswith(f"# File: {file_path}"):
                    content = content[len(f"# File: {file_path}"):].lstrip("\n")
                file_content_parts.append(content)

            # Join with overlap awareness — we deduplicate at boundaries
            file_content = _deduplicate_overlapping_chunks(file_content_parts)

            file_tokens = sum(c.token_count for c in file_chunks)

            # Check if adding this file would exceed our token budget
            if total_estimated_tokens + file_tokens > settings.LONG_CONTEXT_MAX_TOKENS:
                logger.warning(
                    "token budget reached, truncating context",
                    included_files=len(parts),
                    total_files=len(file_paths),
                    tokens_so_far=total_estimated_tokens,
                )
                # Add a note so the model knows context is truncated
                parts.append(
                    f"\n\n[NOTE: Repository truncated at token limit. "
                    f"{len(file_paths) - len(parts)} files not shown.]"
                )
                break

            parts.append(
                f"\n\n{'='*60}\n"
                f"FILE: {file_path}\n"
                f"{'='*60}\n"
                f"```{language}\n"
                f"{file_content}\n"
                f"```"
            )
            total_estimated_tokens += file_tokens

        full_context = "".join(parts)

        logger.info(
            "full context assembled",
            files=len(parts),
            estimated_tokens=total_estimated_tokens,
        )

        return full_context, total_estimated_tokens, file_paths[:len(parts)]

    def _parse_token_usage(self, response) -> tuple[int, int]:
        """Extracts input/output token counts from the LLM response."""
        try:
            usage = response.usage_metadata
            return usage.input_tokens, usage.output_tokens
        except Exception:
            return 0, 0

    async def query(
        self,
        repo_id: UUID,
        question: str,
        db: AsyncSession,
    ) -> EngineResult:
        """
        Answer a question by sending the entire codebase to Gemini.

        This is the long-context approach: no retrieval, full context window.
        """
        start_time = time.time()
        log = logger.bind(engine="long_context", repo_id=str(repo_id))
        log.info("long-context query started", question=question[:80])

        # Fetch repo info
        repo_result = await db.execute(
            select(Repository).where(Repository.id == repo_id)
        )
        repo = repo_result.scalar_one_or_none()
        if not repo:
            raise ValueError(f"Repository {repo_id} not found")

        # Assemble full codebase context
        full_context, total_tokens, included_files = await self._assemble_full_context(
            repo_id, db
        )

        log.info(
            "context assembled",
            tokens=total_tokens,
            files=len(included_files),
        )

        # Build messages
        system = LONG_CONTEXT_SYSTEM_PROMPT.format(
            repo_full_name=repo.full_name,
            total_files=repo.total_files,
            total_tokens=total_tokens,
        )
        human = LONG_CONTEXT_QUERY_TEMPLATE.format(
            full_context=full_context,
            question=question,
        )

        # Call Gemini
        llm = self._get_llm()
        messages = [SystemMessage(content=system), HumanMessage(content=human)]

        response = await llm.ainvoke(messages)
        answer = response.content

        input_tokens, output_tokens = self._parse_token_usage(response)
        latency_ms = (time.time() - start_time) * 1000

        log.info(
            "long-context query complete",
            latency_ms=round(latency_ms),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        # For long-context, we extract file citations from the answer text
        # by scanning for file path patterns mentioned in the response
        cited_files = _extract_cited_files(answer, included_files)

        sources = [
            SourceReference(
                file_path=fp,
                start_line=0,
                end_line=0,
                content_preview="",
                similarity_score=0.0,  # No similarity score in long-context
            )
            for fp in cited_files[:5]
        ]

        return EngineResult(
            answer=answer,
            sources=sources,
            engine_used="long_context",
            model=self.model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=self._estimate_cost(
                self.model_name, input_tokens, output_tokens
            ),
            chunks_retrieved=0,  # No retrieval in long-context
            metadata={
                "total_context_tokens": total_tokens,
                "files_in_context": len(included_files),
            },
        )

    async def generate_patch(
        self,
        repo_id: UUID,
        description: str,
        target_file: str | None,
        db: AsyncSession,
    ) -> EngineResult:
        """
        Generate a patch by sending the full codebase to Gemini.

        For patches, we always use long-context because generating a correct
        diff requires understanding how the changed code integrates with the rest.
        """
        start_time = time.time()
        log = logger.bind(engine="long_context_patch", repo_id=str(repo_id))
        log.info("long-context patch started", description=description[:80])

        repo_result = await db.execute(select(Repository).where(Repository.id == repo_id))
        repo = repo_result.scalar_one_or_none()
        if not repo:
            raise ValueError(f"Repository {repo_id} not found")

        full_context, total_tokens, included_files = await self._assemble_full_context(
            repo_id, db
        )

        target_hint = f"\nFocus the patch on file: `{target_file}`" if target_file else ""

        system = PATCH_SYSTEM_PROMPT.format(repo_full_name=repo.full_name)
        human = PATCH_QUERY_TEMPLATE.format(
            context=full_context,
            description=description,
            target_file_hint=target_hint,
        )

        llm = self._get_llm()
        messages = [SystemMessage(content=system), HumanMessage(content=human)]
        response = await llm.ainvoke(messages)

        answer = response.content
        input_tokens, output_tokens = self._parse_token_usage(response)

        affected_files = _extract_cited_files(answer, included_files)

        sources = [
            SourceReference(
                file_path=fp,
                start_line=0,
                end_line=0,
                content_preview="",
                similarity_score=0.0,
            )
            for fp in affected_files[:5]
        ]

        log.info(
            "long-context patch complete",
            latency_ms=round((time.time() - start_time) * 1000),
        )

        return EngineResult(
            answer=answer,
            sources=sources,
            engine_used="long_context",
            model=self.model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=self._estimate_cost(
                self.model_name, input_tokens, output_tokens
            ),
            chunks_retrieved=0,
            metadata={
                "affected_files": affected_files,
                "total_context_tokens": total_tokens,
            },
        )


# ── Utility Functions ─────────────────────────────────────────────────────────

def _deduplicate_overlapping_chunks(parts: list[str]) -> str:
    """
    Joins overlapping chunks while minimizing duplication at boundaries.

    When we split a file into chunks with overlap, adjacent chunks share
    some text. This function stitches them back together cleanly.

    Simple heuristic: find the longest common suffix/prefix between
    adjacent chunks and remove the duplicate.
    """
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]

    result = parts[0]
    for next_part in parts[1:]:
        # Find overlap: look for the longest suffix of `result` that is a
        # prefix of `next_part`
        overlap_len = 0
        max_overlap = min(len(result), len(next_part), 400)  # cap at 400 chars

        for i in range(max_overlap, 0, -1):
            if result.endswith(next_part[:i]):
                overlap_len = i
                break

        result = result + next_part[overlap_len:]

    return result


def _extract_cited_files(answer: str, known_files: list[str]) -> list[str]:
    """
    Extracts file paths from an LLM answer by matching against known file paths.

    The LLM often mentions files like `src/auth/login.py` in backticks or plain text.
    We scan the answer for any known file paths to build the citation list.
    """
    cited = []
    for file_path in known_files:
        # Check if the file path (or just the filename) appears in the answer
        filename = file_path.split("/")[-1]
        if file_path in answer or filename in answer:
            cited.append(file_path)

    return cited
