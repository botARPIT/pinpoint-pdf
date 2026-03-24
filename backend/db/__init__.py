"""
Database package - exports all models and session factories.
"""
from db.user_db import User, get_user_db, init_user_db, engine as user_engine
from db.embedding_db import (
    Document,
    Chunk,
    get_embedding_db,
    init_embedding_db,
    engine as embedding_engine,
)
from db.chat_db import (
    ChatSession,
    Message,
    get_chat_db,
    init_chat_db,
    engine as chat_engine,
)

__all__ = [
    # User DB
    "User",
    "get_user_db",
    "init_user_db",
    "user_engine",
    # Embedding DB
    "Document",
    "Chunk",
    "get_embedding_db",
    "init_embedding_db",
    "embedding_engine",
    # Chat DB
    "ChatSession",
    "Message",
    "get_chat_db",
    "init_chat_db",
    "chat_engine",
]


async def init_all_dbs():
    """Initialize all database schemas."""
    await init_user_db()
    await init_embedding_db()
    await init_chat_db()
