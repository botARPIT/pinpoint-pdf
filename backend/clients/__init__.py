"""
Shared client factories for external services.
Centralizes LangChain LLM, Embeddings, Pinecone, S3, and Redis client creation.
"""
from clients.gemini import get_llm, get_embeddings
from clients.pinecone_client import get_vectorstore, get_pinecone_index
from clients.s3 import (
    get_s3_client,
    get_raw_bucket,
    get_processed_bucket,
    build_object_uri,
    parse_object_uri,
    delete_prefix,
)

__all__ = [
    "get_llm",
    "get_embeddings",
    "get_vectorstore",
    "get_pinecone_index",
    "get_s3_client",
    "get_raw_bucket",
    "get_processed_bucket",
    "build_object_uri",
    "parse_object_uri",
    "delete_prefix",
]
