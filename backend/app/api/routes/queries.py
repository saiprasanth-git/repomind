"""
Query routes — HTTP endpoints for asking questions and generating patches.

POST /repos/{id}/query  → ask a question about the repo
POST /repos/{id}/patch  → generate a code patch
GET  /repos/{id}/queries → get query history for a repo
GET  /repos/{id}/overview → get an AI-generated overview of the repo
"""
import time
from uuid import UUID
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.models.repo import Repository, RepoStatus
from app.models.query_log import QueryLog
from app.schemas.query import (
    QueryRequest,
    QueryResponse,
    PatchRequest,
    PatchResponse,
    SourceReference,
)
from app.engines.router import query_router

logger = structlog.get_logger()
router = APIRouter(tags=["queries"])


def _require_ready_repo(repo: Repository | None, repo_id: UUID) -> Repository:
    """Shared guard: ensures a repo exists and is fully indexed before queries."""
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    if repo.status != RepoStatus.READY:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Repository is not ready for queries (status: {repo.status.value}). "
                "Wait for ingestion to complete."
            ),
        )
    return repo


@router.post("/repos/{repo_id}/query", response_model=QueryResponse)
async def query_repo(
    repo_id: UUID,
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Ask a natural language question about a repository.

    The engine is selected automatically unless you specify "rag" or "long_context".

    Returns the answer with:
    - Source file citations
    - The engine that was used
    - Performance metrics (latency, tokens, cost)
    """
    start_time = time.time()

    # Verify repo exists and is ready
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = _require_ready_repo(result.scalar_one_or_none(), repo_id)

    log = logger.bind(repo=repo.full_name, question=request.question[:80])
    log.info("query received", engine_requested=request.engine)

    # Route to the correct engine
    engine, engine_used, question_type = await query_router.route(
        repo_id=repo_id,
        question=request.question,
        requested_engine=request.engine,
        db=db,
    )

    # Run the query
    try:
        engine_result = await engine.query(
            repo_id=repo_id,
            question=request.question,
            db=db,
        )
    except Exception as e:
        log.error("engine query failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Query failed: {str(e)}"
        )

    latency_ms = (time.time() - start_time) * 1000

    # Persist the query log (for experiment data and history)
    query_log = QueryLog(
        repository_id=repo_id,
        question=request.question,
        question_type=question_type,
        engine=engine_used,
        model=engine_result.model,
        answer=engine_result.answer,
        source_files=[s.file_path for s in engine_result.sources],
        chunks_retrieved=engine_result.chunks_retrieved,
        latency_ms=latency_ms,
        input_tokens=engine_result.input_tokens,
        output_tokens=engine_result.output_tokens,
        estimated_cost_usd=engine_result.estimated_cost_usd,
    )
    db.add(query_log)
    await db.commit()
    await db.refresh(query_log)

    log.info(
        "query complete",
        engine=engine_used,
        latency_ms=round(latency_ms),
        tokens_in=engine_result.input_tokens,
        tokens_out=engine_result.output_tokens,
    )

    return QueryResponse(
        query_id=query_log.id,
        question=request.question,
        answer=engine_result.answer,
        engine_used=engine_used,
        model=engine_result.model,
        sources=[
            SourceReference(
                file_path=s.file_path,
                start_line=s.start_line,
                end_line=s.end_line,
                content_preview=s.content_preview,
                similarity_score=s.similarity_score,
            )
            for s in engine_result.sources
        ],
        latency_ms=round(latency_ms, 1),
        input_tokens=engine_result.input_tokens,
        output_tokens=engine_result.output_tokens,
        estimated_cost_usd=engine_result.estimated_cost_usd,
        created_at=query_log.created_at,
    )


@router.post("/repos/{repo_id}/patch", response_model=PatchResponse)
async def generate_patch(
    repo_id: UUID,
    request: PatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a code patch in unified diff format.

    Describe what you want to change in plain English.
    Optionally specify a target file to focus the patch.

    Returns the patch (git diff format) plus a plain English explanation.
    """
    start_time = time.time()

    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = _require_ready_repo(result.scalar_one_or_none(), repo_id)

    log = logger.bind(repo=repo.full_name, desc=request.description[:80])
    log.info("patch generation requested")

    try:
        # For patches we always use RAG — it's better for targeted changes
        # (long-context is used internally for large patches via override)
        engine_result = await query_router._rag.generate_patch(
            repo_id=repo_id,
            description=request.description,
            target_file=request.target_file,
            db=db,
        )
    except Exception as e:
        log.error("patch generation failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Patch generation failed: {str(e)}")

    latency_ms = (time.time() - start_time) * 1000

    # Split answer into patch and explanation
    answer = engine_result.answer
    patch_content = answer
    explanation = ""

    if "## Explanation" in answer:
        parts = answer.split("## Explanation", 1)
        patch_content = parts[0].strip()
        explanation = parts[1].strip()

    # Log it
    query_log = QueryLog(
        repository_id=repo_id,
        question=f"[PATCH] {request.description}",
        question_type="patch",
        engine=engine_result.engine_used,
        model=engine_result.model,
        answer=answer,
        source_files=[s.file_path for s in engine_result.sources],
        chunks_retrieved=engine_result.chunks_retrieved,
        latency_ms=latency_ms,
        input_tokens=engine_result.input_tokens,
        output_tokens=engine_result.output_tokens,
        estimated_cost_usd=engine_result.estimated_cost_usd,
    )
    db.add(query_log)
    await db.commit()
    await db.refresh(query_log)

    log.info("patch complete", latency_ms=round(latency_ms))

    return PatchResponse(
        query_id=query_log.id,
        description=request.description,
        patch=patch_content,
        affected_files=engine_result.metadata.get("affected_files", []),
        explanation=explanation or "See patch above.",
        latency_ms=round(latency_ms, 1),
        created_at=query_log.created_at,
    )


@router.get("/repos/{repo_id}/queries")
async def get_query_history(
    repo_id: UUID,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the last N queries made against this repository.
    Used by the frontend to show query history in the sidebar.
    """
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    logs_result = await db.execute(
        select(QueryLog)
        .where(QueryLog.repository_id == repo_id)
        .order_by(QueryLog.created_at.desc())
        .limit(limit)
    )
    logs = logs_result.scalars().all()

    return {
        "repo_id": str(repo_id),
        "queries": [
            {
                "id": str(log.id),
                "question": log.question,
                "engine": log.engine,
                "latency_ms": log.latency_ms,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
    }


@router.get("/repos/{repo_id}/file-content")
async def get_file_content(
    repo_id: UUID,
    file_path: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the full content of a specific file, reconstructed from chunks.
    Used by the code viewer when a user clicks a file in the explorer.
    """
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    from app.models.chunk import CodeChunk
    chunks_result = await db.execute(
        select(CodeChunk)
        .where(
            CodeChunk.repository_id == repo_id,
            CodeChunk.file_path == file_path,
        )
        .order_by(CodeChunk.chunk_index)
    )
    chunks = chunks_result.scalars().all()

    if not chunks:
        raise HTTPException(
            status_code=404,
            detail=f"File '{file_path}' not found in repository"
        )

    # Reconstruct full file from chunks
    from app.engines.long_context_engine import _deduplicate_overlapping_chunks
    parts = []
    for chunk in chunks:
        content = chunk.content
        if content.startswith(f"# File: {file_path}"):
            content = content[len(f"# File: {file_path}"):].lstrip("\n")
        parts.append(content)

    full_content = _deduplicate_overlapping_chunks(parts)

    return {
        "file_path": file_path,
        "content": full_content,
        "language": chunks[0].language,
        "extension": chunks[0].file_extension,
        "total_lines": full_content.count("\n") + 1,
        "chunks": len(chunks),
    }
