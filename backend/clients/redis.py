"""
Redis dependency for FastAPI routes.
Eliminates circular import from api.main.
"""
from fastapi import Request
from redis import asyncio as aioredis


async def get_redis(request: Request) -> aioredis.Redis:
    """
    FastAPI dependency to get Redis client from app state.
    
    Usage in routes:
        redis: aioredis.Redis = Depends(get_redis)
    """
    return request.app.state.redis
