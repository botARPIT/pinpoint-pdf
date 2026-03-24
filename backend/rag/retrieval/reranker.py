"""
Local cross-encoder reranking using sentence-transformers.
"""
import asyncio
from typing import List, Tuple

import structlog

from rag.retrieval.vector_search import RetrievedChunk


logger = structlog.get_logger()

_reranker = None
_reranker_load_failed = False


def _get_reranker():
    """Lazily initialize CrossEncoder to avoid hard dependency at import time."""
    global _reranker, _reranker_load_failed
    if _reranker is not None:
        return _reranker
    if _reranker_load_failed:
        return None

    try:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        return _reranker
    except Exception as e:
        _reranker_load_failed = True
        logger.warning("Cross-encoder unavailable; falling back to vector-score ranking", error=str(e))
        return None


async def rerank_chunks(
    query: str,
    chunks: List[RetrievedChunk],
    chunk_texts: List[str],
    top_n: int = 5,
) -> List[Tuple[RetrievedChunk, float]]:
    """
    Rerank chunks using local cross-encoder.

    Args:
        query: Original user query
        chunks: Retrieved chunks
        chunk_texts: Full text of each chunk (from S3)
        top_n: Number of top chunks to return

    Returns:
        List of (chunk, rerank_score) tuples
    """
    reranker = _get_reranker()
    if reranker is None:
        # Graceful fallback: keep retrieval ordering and cap to top_n.
        ranked = sorted(
            [(chunk, float(chunk.score)) for chunk in chunks],
            key=lambda x: x[1],
            reverse=True,
        )
        top_chunks = ranked[:top_n]
        logger.info("Reranked chunks (fallback)", num_input=len(chunks), top_n=top_n)
        return top_chunks

    # Prepare query-document pairs
    pairs = [[query, text] for text in chunk_texts]

    # Score with cross-encoder (run in thread to avoid blocking)
    scores = await asyncio.to_thread(reranker.predict, pairs)

    # Combine chunks with scores and sort
    ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)

    top_chunks = ranked[:top_n]

    logger.info("Reranked chunks", num_input=len(chunks), top_n=top_n)
    return top_chunks
