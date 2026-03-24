"""
Centralized Pinecone vector store via LangChain.
"""
from functools import lru_cache

import structlog
from langchain_pinecone import PineconeVectorStore

from clients.gemini import get_embeddings
from config import settings


logger = structlog.get_logger()


def get_vectorstore(namespace: str = "") -> PineconeVectorStore:
    """
    Get a PineconeVectorStore instance for a given namespace.

    Args:
        namespace: Pinecone namespace (typically the doc_id)

    Returns:
        PineconeVectorStore instance
    """
    return PineconeVectorStore(
        index_name=settings.PINECONE_INDEX,
        embedding=get_embeddings(),
        namespace=namespace,
        pinecone_api_key=settings.PINECONE_API_KEY,
    )


@lru_cache(maxsize=1)
def get_pinecone_index():
    """
    Get the raw Pinecone index for direct upsert operations (used by workers).
    """
    from pinecone import Pinecone

    pc = Pinecone(api_key=settings.PINECONE_API_KEY)
    return pc.Index(settings.PINECONE_INDEX)
