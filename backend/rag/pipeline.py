"""
Main RAG pipeline orchestrator.
Coordinates: query expansion → retrieval → rerank → S3 fetch (top-N) → generation.
Powered by LangChain.
"""
import time
from typing import List, Tuple

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from rag.query.multi_query import expand_query
from rag.retrieval.vector_search import retrieve_chunks
from rag.retrieval.reranker import rerank_chunks
from rag.retrieval.s3_fetcher import clear_batch_cache, fetch_chunks_from_s3
from rag.generation.rag_chain import generate_answer

from config import settings


logger = structlog.get_logger()


async def run_rag_pipeline(
    doc_ids: List[str],
    question: str,
    db: AsyncSession,
    top_k: int = settings.RAG_TOP_K,
    top_n: int = settings.RAG_TOP_N
) -> Tuple[str, List[dict], int]:
    """
    Run complete RAG pipeline.

    Flow: expand → retrieve → rerank on summaries → S3 fetch top-N → generate.
    """
    start_time = time.time()
    clear_batch_cache()
    try:
        # Step 1: Query expansion
        t1 = time.time()
        queries = await expand_query(question)
        logger.info("Step 1: Expansion", duration_ms=int((time.time() - t1) * 1000), num_queries=len(queries))

        # Step 2: Retrieval (returns chunks with summary_text from Pinecone metadata)
        t2 = time.time()
        retrieved_chunks = await retrieve_chunks(doc_ids, queries, top_k=top_k)
        logger.info("Step 2: Retrieval", duration_ms=int((time.time() - t2) * 1000), num_chunks=len(retrieved_chunks))

        if not retrieved_chunks:
            return "No relevant information found in your documents.", [], int((time.time() - start_time) * 1000)

        # Step 3: Rerank using summary text from Pinecone metadata (NO S3 fetch needed)
        t3 = time.time()
        summary_texts = [chunk.summary_text for chunk in retrieved_chunks]
        reranked = await rerank_chunks(question, retrieved_chunks, summary_texts, top_n=top_n)
        logger.info(
            "Step 3: Rerank (on summaries)",
            duration_ms=int((time.time() - t3) * 1000),
            top_n=len(reranked),
        )

        # Step 4: Fetch full chunk text from S3 — ONLY for top-N reranked chunks
        top_chunks = [chunk for chunk, _ in reranked]
        t4 = time.time()
        chunk_refs = [(chunk.chunk_id, chunk.doc_id) for chunk in top_chunks]
        chunk_texts = await fetch_chunks_from_s3(chunk_refs, db=db)
        logger.info(
            "Step 4: S3 Fetch (top-N only)",
            duration_ms=int((time.time() - t4) * 1000),
            num_fetched=len(top_chunks),
        )

        # Filter out empty chunks (S3 fetch failures)
        valid_pairs = [(chunk, text) for chunk, text in zip(top_chunks, chunk_texts) if text]
        if not valid_pairs:
            return "Error retrieving document chunks.", [], int((time.time() - start_time) * 1000)

        top_chunks, top_texts = zip(*valid_pairs)
        top_chunks = list(top_chunks)
        top_texts = list(top_texts)

        # Step 5: Generation with full text
        context_metadata = [
            {
                "page_start": chunk.page_start,
                "section_path": chunk.section_path,
            }
            for chunk in top_chunks
        ]

        t5 = time.time()
        answer = await generate_answer(question, top_texts, context_metadata)
        logger.info("Step 5: Generation", duration_ms=int((time.time() - t5) * 1000))

        # Prepare sources
        sources = [
            {
                "chunk_id": chunk.chunk_id,
                "page": chunk.page_start,
                "section": chunk.section_path,
                "doc_id": chunk.doc_id,
            }
            for chunk in top_chunks
        ]

        latency_ms = int((time.time() - start_time) * 1000)
        logger.info("RAG pipeline complete", total_ms=latency_ms)

        return answer, sources, latency_ms
    finally:
        clear_batch_cache()
