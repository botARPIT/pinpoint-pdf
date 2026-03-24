"""
Shared utilities for Celery workers.
"""
import asyncio


def run_sync(coro):
    """Run an async coroutine synchronously (for Celery tasks).
    
    Creates a fresh event loop per invocation to avoid conflicts
    with Celery's fork-based worker pool.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()



from contextlib import asynccontextmanager


@asynccontextmanager
async def get_local_session():
    """Create a fresh async session for the current event loop.
    
    Uses NullPool to ensure connections are closed immediately, preventing
    'Event loop is closed' errors when the loop is torn down.
    """
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from config import settings
    
    # Use NullPool since we create/dispose engine per task
    engine = create_async_engine(
        settings.EMBEDDING_DB_URL, 
        echo=False, 
        poolclass=NullPool
    )
    
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
    
    # Ensure engine is disposed to close connections
    await engine.dispose()
