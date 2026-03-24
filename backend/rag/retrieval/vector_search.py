"""
Vector search using LangChain PineconeVectorStore.
"""
import asyncio
from dataclasses import dataclass
from typing import List

import structlog

from clients.pinecone_client import get_vectorstore


logger = structlog.get_logger()


@dataclass
class RetrievedChunk:
    """Retrieved chunk with score."""
    chunk_id: str
    score: float
    doc_id: str
    section_path: str
    page_start: int
    page_end: int
    chunk_type: str
    summary_text: str = ""  # Summary text from Pinecone metadata


async def retrieve_chunks(
    doc_ids: List[str],
    queries: List[str],
    top_k: int = 10,
) -> List[RetrievedChunk]:
    """
    Retrieve chunks using multi-query retrieval via LangChain PineconeVectorStore.

    Args:
        doc_ids: Document IDs (each used as Pinecone namespace)
        queries: List of query variations
        top_k: Number of chunks to retrieve per query

    Returns:
        Deduplicated list of retrieved chunks (max-score dedup) across all docs.
    """
    all_results = {}
    if not doc_ids:
        return []
    allowed_doc_ids = set(doc_ids)

    # Run all (namespace, query) searches in parallel.
    search_tasks = []
    task_doc_ids = []
    for doc_id in doc_ids:
        vectorstore = get_vectorstore(namespace=doc_id)
        for query in queries:
            search_tasks.append(vectorstore.asimilarity_search_with_score(query, k=top_k))
            task_doc_ids.append(doc_id)

    results_list = await asyncio.gather(*search_tasks, return_exceptions=True)

    for doc_id, results in zip(task_doc_ids, results_list):
        if isinstance(results, Exception):
            logger.warning("Vector search failed for namespace", doc_id=doc_id, error=str(results))
            continue
        for doc, score in results:
            chunk_id = doc.metadata.get("chunk_id", doc.metadata.get("id", ""))
            chunk_doc_id = doc.metadata.get("doc_id", doc_id)
            if chunk_doc_id not in allowed_doc_ids:
                continue
            if chunk_id not in all_results or score > all_results[chunk_id].score:
                all_results[chunk_id] = RetrievedChunk(
                    chunk_id=chunk_id,
                    score=score,
                    doc_id=chunk_doc_id,
                    section_path=doc.metadata.get("section_path", ""),
                    page_start=doc.metadata.get("page_start", 0),
                    page_end=doc.metadata.get("page_end", 0),
                    chunk_type=doc.metadata.get("chunk_type", "paragraph"),
                    summary_text=doc.metadata.get("text", ""),
                )

    # Sort by score descending and cap candidate pool size.
    candidate_limit = max(top_k * max(len(queries), 1), top_k)
    chunks = sorted(all_results.values(), key=lambda x: x.score, reverse=True)[:candidate_limit]

    logger.info("Retrieved chunks", num_docs=len(doc_ids), num_queries=len(queries), num_chunks=len(chunks))
    return chunks
