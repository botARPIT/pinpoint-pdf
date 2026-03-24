"""
RAG package — summary-first retrieval augmented generation.

Subpackages:
    rag.query        — Multi-query expansion
    rag.retrieval    — Vector search, reranking, RRF, S3 fetching
    rag.generation   — LLM answer generation
"""
from rag.pipeline import run_rag_pipeline

__all__ = ["run_rag_pipeline"]
