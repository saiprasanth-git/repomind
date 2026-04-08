"""
Ingestion Pipeline — orchestrates the full flow from GitHub URL to searchable database.

Plain English: This is the conductor. It calls all the other ingestion modules
in the right order and updates the repository's status along the way so the
frontend can show a real-time progress bar.

The pipeline flow:
  1. CLONE    → Download the repo from GitHub
  2. PARSE    → Read every supported file
  3. CHUNK    → Split files into smaller pieces
  4. EMBED    → Convert each piece into a vector (numerical fingerprint)
  5. STORE    → Save everything to PostgreSQL
  6. CLEANUP  → Delete the local clone (we don't need it anymore)
"""
import asyncio
from datetime import datetime
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.models.repo import Repository, RepoStatus
from app.models.chunk import CodeChunk
from app.ingestion.cloner import clone_repository, cleanup_clone, get_repo_metadata, parse_github_url
from app.ingestion.parser import parse_repository
from app.ingestion.chunker import chunk_file
from app.ingestion.embedder import embed_chunks

logger = structlog.get_logger()


async def _update_repo_status(
    repo_id: UUID,
    status: RepoStatus,
    error_message: str | None = None,
    **kwargs,
) -> None:
    """Helper to update repo status in DB without holding a session open."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Repository).where(Repository.id == repo_id))
        repo = result.scalar_one_or_none()
        if repo:
            repo.status = status
            if error_message:
                repo.error_message = error_message
            for key, value in kwargs.items():
                setattr(repo, key, value)
            repo.updated_at = datetime.utcnow()
            await db.commit()


async def run_ingestion_pipeline(repo_id: UUID, github_url: str) -> None:
    """
    Full ingestion pipeline — runs as a background task after the API returns.

    This function is designed to be called with asyncio.create_task() so the
    HTTP response returns immediately (202 Accepted) while ingestion runs
    in the background.

    The frontend polls /api/v1/repos/{id}/status to track progress.

    Args:
        repo_id: UUID of the already-created Repository record
        github_url: GitHub URL to clone and index
    """
    log = logger.bind(repo_id=str(repo_id), url=github_url)
    clone_path: Path | None = None

    try:
        # ── Step 1: Clone ─────────────────────────────────────────────────────
        log.info("pipeline started: cloning")
        await _update_repo_status(repo_id, RepoStatus.CLONING)

        owner, repo_name = parse_github_url(github_url)

        # Fetch GitHub metadata in parallel with clone start
        metadata = await asyncio.get_event_loop().run_in_executor(
            None, get_repo_metadata, owner, repo_name
        )

        clone_path = await clone_repository(github_url, str(repo_id))
        

        # Update repo record with metadata
        await _update_repo_status(
            repo_id, RepoStatus.INDEXING,
            description=metadata.get("description"),
            language=metadata.get("language"),
            stars=metadata.get("stars", 0),
            default_branch=metadata.get("default_branch", "main"),
            repo_size_kb=metadata.get("size_kb", 0),
        )

        # ── Step 2: Parse ─────────────────────────────────────────────────────
        log.info("pipeline: parsing files")

        parsed_files = list(parse_repository(clone_path))
        log.info("files parsed", count=len(parsed_files))

        # ── Step 3: Chunk ─────────────────────────────────────────────────────
        log.info("pipeline: chunking files")

        all_chunks = []
        for parsed_file in parsed_files:
            file_chunks = chunk_file(parsed_file)
            all_chunks.extend(file_chunks)

        total_tokens = sum(c.token_count for c in all_chunks)
        log.info(
            "chunking complete",
            total_chunks=len(all_chunks),
            total_tokens=total_tokens,
        )

        await _update_repo_status(
            repo_id, RepoStatus.INDEXING,
            total_files=len(parsed_files),
            total_chunks=len(all_chunks),
            total_tokens=total_tokens,
        )

        # ── Step 4: Embed ─────────────────────────────────────────────────────
        log.info("pipeline: generating embeddings")

        embeddings = await embed_chunks(all_chunks, batch_size=50)

        # ── Step 5: Store ─────────────────────────────────────────────────────
        log.info("pipeline: storing chunks")

        # Delete any existing chunks for this repo (handles re-indexing)
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(CodeChunk).where(CodeChunk.repository_id == repo_id)
            )
            await db.commit()

        # Batch insert all chunks
        # We insert in batches of 200 to avoid hitting PostgreSQL parameter limits
        insert_batch_size = 200
        total_stored = 0

        for i in range(0, len(all_chunks), insert_batch_size):
            batch_chunks = all_chunks[i : i + insert_batch_size]
            batch_embeddings = embeddings[i : i + insert_batch_size]

            chunk_records = [
                CodeChunk(
                    repository_id=repo_id,
                    file_path=chunk.file_path,
                    file_extension=chunk.extension,
                    chunk_index=chunk.chunk_index,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    content=chunk.content,
                    content_hash=chunk.content_hash,
                    token_count=chunk.token_count,
                    language=chunk.language,
                    embedding=embedding,
                )
                for chunk, embedding in zip(batch_chunks, batch_embeddings)
            ]

            async with AsyncSessionLocal() as db:
                db.add_all(chunk_records)
                await db.commit()

            total_stored += len(chunk_records)
            log.info("stored batch", stored=total_stored, total=len(all_chunks))

        # ── Step 6: Mark as Ready ─────────────────────────────────────────────
        log.info("pipeline complete — repo is ready")

        await _update_repo_status(
            repo_id, RepoStatus.READY,
            indexed_files=len(parsed_files),
            indexed_at=datetime.utcnow(),
        )

    except Exception as e:
        log.error("pipeline failed", error=str(e), exc_info=True)
        await _update_repo_status(
            repo_id, RepoStatus.FAILED,
            error_message=str(e)
        )

    finally:
        # Always clean up the local clone, whether we succeeded or failed
        if clone_path:
            cleanup_clone(str(repo_id))
            log.info("local clone cleaned up")
