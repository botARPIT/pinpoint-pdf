"""
FastAPI application core.
Handles lifespan, CORS, routing, and health checks.
"""
import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis import asyncio as aioredis

# Ensure project root is in path for imports like 'config' and 'db'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from db import user_engine, embedding_engine, chat_engine


logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan - startup and shutdown."""
    logger.info("Starting up application...")
    
    # Initialize Redis connection pool
    app.state.redis = await aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True
    )
    
    # Store DB engines in app state (already initialized in db modules)
    app.state.user_db_engine = user_engine
    app.state.embedding_db_engine = embedding_engine
    app.state.chat_db_engine = chat_engine
    
    logger.info("Application started", env=settings.ENV)
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    await app.state.redis.close()
    await user_engine.dispose()
    await embedding_engine.dispose()
    await chat_engine.dispose()
    logger.info("Application shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Pinpoint PDF",
    description="Layout-aware PDF RAG chatbot with summary-first retrieval",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "env": settings.ENV,
        "version": "0.1.0"
    }


# Include routers
from api.auth import router as auth_router
from api.routes.upload import router as upload_router
from api.routes.chat import router as chat_router
from api.routes.documents import router as documents_router
from api.routes.sessions import router as sessions_router

app.include_router(auth_router, tags=["auth"])
app.include_router(upload_router, prefix="/api", tags=["upload"])
app.include_router(chat_router, prefix="/api", tags=["chat"])
app.include_router(documents_router, prefix="/api", tags=["documents"])
app.include_router(sessions_router, prefix="/api", tags=["sessions"])
