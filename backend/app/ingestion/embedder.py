"""
Embedder — converts text chunks into vector embeddings using Google's API.

Plain English: An embedding is a list of ~768 numbers that captures the
"meaning" of a piece of text. Similar texts get similar numbers.
"def authenticate_user" and "how does login work?" will have very similar
number lists, even though they use different words. That's the magic.

We batch chunks together to minimize API round trips (faster + cheaper).
"""
import asyncio
from typing import Any

import structlog
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.core.config import settings
from app.ingestion.chunker import Chunk

logger = structlog.get_logger()

# Module-level embedding client (initialized once, reused across calls)
_embeddings_client: GoogleGenerativeAIEmbeddings | None = None


def get_embeddings_client() -> GoogleGenerativeAIEmbeddings:
    """
    Returns a singleton embedding client.
    Creates it on first call, reuses on subsequent calls.
    """
    global _embeddings_client
    if _embeddings_client is None:
        _embeddings_client = GoogleGenerativeAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            google_api_key=settings.GOOGLE_API_KEY,
            task_type="retrieval_document",
            # task_type tells Google how we'll use these embeddings:
            # "retrieval_document" = we're indexing documents to be searched
            # "retrieval_query"    = we're embedding a query to search with
            # Using the right task_type improves retrieval accuracy by ~15%
        )
    return _embeddings_client


async def embed_chunks(
    chunks: list[Chunk],
    batch_size: int = 50
) -> list[list[float]]:
    """
    Generates embeddings for a list of chunks.

    Processes in batches to:
    1. Stay within API rate limits
    2. Not exceed the max batch size per API call
    3. Allow progress reporting for large repos

    Args:
        chunks: List of Chunk objects to embed
        batch_size: How many chunks to send per API call

    Returns:
        List of embedding vectors, in the same order as the input chunks.
        Each vector is a list of 768 floats.
    """
    client = get_embeddings_client()
    all_embeddings: list[list[float]] = []

    total_batches = (len(chunks) + batch_size - 1) // batch_size

    for batch_num, i in enumerate(range(0, len(chunks), batch_size)):
        batch = chunks[i : i + batch_size]
        texts = [chunk.content for chunk in batch]

        logger.info(
            "embedding batch",
            batch=f"{batch_num + 1}/{total_batches}",
            chunks_in_batch=len(batch),
        )

        try:
            # embed_documents is a sync call — we run it in a thread pool
            # to avoid blocking the async event loop
            embeddings = await asyncio.get_event_loop().run_in_executor(
                None,
                client.embed_documents,
                texts,
            )
            all_embeddings.extend(embeddings)

        except Exception as e:
            logger.error(
                "embedding batch failed",
                batch=batch_num + 1,
                error=str(e)
            )
            # On failure, insert zero vectors as placeholders
            # The affected chunks will be retrievable but won't rank well
            zero_vector = [0.0] * 768
            all_embeddings.extend([zero_vector] * len(batch))

        # Small delay between batches to respect rate limits
        if batch_num < total_batches - 1:
            await asyncio.sleep(0.1)

    return all_embeddings


async def embed_query(query: str) -> list[float]:
    """
    Embeds a single search query for retrieval.

    Uses task_type="retrieval_query" instead of "retrieval_document"
    to get embeddings optimized for search (not storage).
    """
    client = GoogleGenerativeAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        task_type="retrieval_query",
    )

    try:
        embedding = await asyncio.get_event_loop().run_in_executor(
            None,
            client.embed_query,
            query,
        )
        return embedding
    except Exception as e:
        logger.error("query embedding failed", error=str(e))
        raise RuntimeError(f"Failed to embed query: {e}") from e
