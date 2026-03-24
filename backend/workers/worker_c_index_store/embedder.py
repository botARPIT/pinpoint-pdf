"""
Embedding module using LangChain GoogleGenerativeAIEmbeddings.
"""
import asyncio
from typing import List
from dataclasses import dataclass

import structlog

from clients.gemini import get_embeddings
from config import settings


logger = structlog.get_logger()


@dataclass
class Embedding:
    """Embedding result."""
    chunk_id: str
    vector: List[float]


async def embed_texts(
    texts: List[tuple[str, str]],
    batch_size: int | None = None,
) -> List[Embedding]:
    """
    Embed texts using LangChain GoogleGenerativeAIEmbeddings.

    Args:
        texts: List of (chunk_id, text) tuples
        batch_size: Batch size for API calls. Uses settings default when None.

    Returns:
        List of Embedding objects
    """
    if not texts:
        return []

    batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE
    max_concurrency = settings.EMBEDDING_BATCH_CONCURRENCY
    embeddings_model = get_embeddings()
    batches: list[list[tuple[str, str]]] = [
        texts[i:i + batch_size] for i in range(0, len(texts), batch_size)
    ]
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _embed_batch(batch_idx: int, batch: list[tuple[str, str]]):
        batch_texts = [text for _, text in batch]
        async with semaphore:
            vectors = await embeddings_model.aembed_documents(batch_texts)
        logger.info(
            "Embedded batch",
            batch=batch_idx + 1,
            batch_size=len(batch),
            total_batches=len(batches),
        )
        return batch_idx, [
            Embedding(chunk_id=chunk_id, vector=vectors[j])
            for j, (chunk_id, _) in enumerate(batch)
        ]

    try:
        batch_results = await asyncio.gather(
            *[_embed_batch(idx, batch) for idx, batch in enumerate(batches)]
        )
    except Exception as e:
        logger.error("Error embedding batch", error=str(e))
        raise

    ordered_results = sorted(batch_results, key=lambda x: x[0])
    embeddings: list[Embedding] = []
    for _, batch_embeddings in ordered_results:
        embeddings.extend(batch_embeddings)
    return embeddings
