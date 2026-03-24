"""
Worker B - Chunking and Summarization worker.
Dequeues preprocessed docs, chunks them, generates summaries, and enqueues to next stage.
"""
import asyncio
import json

import structlog
from redis import asyncio as aioredis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from clients.s3 import get_processed_bucket, get_s3_client
from config import settings
from db import Document, embedding_engine
from chunking.section_chunker import chunk_document
from workers.worker_b_chunk_summarize.summarizer import summarize_chunks


logger = structlog.get_logger()


s3_client = get_s3_client()


async def process_document(doc_id: str, db: AsyncSession, redis: aioredis.Redis):
    """
    Process document: download structured doc, chunk, summarize, enqueue.
    
    Args:
        doc_id: Document ID
        db: Database session
        redis: Redis client
    """
    logger.info("Chunking and summarizing", doc_id=doc_id)
    
    try:
        processed_bucket = get_processed_bucket()

        # Download structured doc from S3
        response = s3_client.get_object(
            Bucket=processed_bucket,
            Key=f"docs/{doc_id}/structured/structured_text.json"
        )
        structured_text = json.loads(response["Body"].read())
        
        response = s3_client.get_object(
            Bucket=processed_bucket,
            Key=f"docs/{doc_id}/structured/tables.json"
        )
        tables = json.loads(response["Body"].read())
        
        structured_doc = {
            "structured_text": structured_text,
            "tables": tables
        }
        
        # Chunk document
        chunks = chunk_document(structured_doc, doc_id=doc_id)
        logger.info("Document chunked", doc_id=doc_id, num_chunks=len(chunks))
        
        # Summarize chunks
        summaries = await summarize_chunks(chunks)
        logger.info("Chunks summarized", doc_id=doc_id, num_summaries=len(summaries))
        
        # Prepare payload for next worker
        chunks_data = [
            {
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "text": chunk.text,
                "section_path": chunk.section_path,
                "section_level": chunk.section_level,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "chunk_type": chunk.chunk_type,
                "token_count": chunk.token_count,
                "table_id": chunk.table_id,
                "figure_id": chunk.figure_id
            }
            for chunk in chunks
        ]
        
        summaries_data = [
            {
                "chunk_id": summary.chunk_id,
                "summary_text": summary.summary_text
            }
            for summary in summaries
        ]
        
        # Update status
        await db.execute(
            update(Document)
            .where(Document.doc_id == doc_id)
            .values(status="chunked")
        )
        await db.commit()
        
        # Enqueue to next stage
        await redis.lpush("index_store", json.dumps({
            "doc_id": doc_id,
            "chunks": chunks_data,
            "summaries": summaries_data
        }))
        
        logger.info("Chunking complete", doc_id=doc_id)
        
    except Exception as e:
        logger.error("Error chunking document", doc_id=doc_id, error=str(e))
        await db.execute(
            update(Document)
            .where(Document.doc_id == doc_id)
            .values(status="failed")
        )
        await db.commit()
        raise


async def worker_loop():
    """Main worker loop."""
    logger.info("Starting Worker B (Chunk + Summarize)")
    
    redis = await aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    
    async with AsyncSession(embedding_engine) as db:
        while True:
            try:
                result = await redis.brpop("chunk_summarize", timeout=settings.WORKER_POLL_INTERVAL)
                
                if result:
                    _, job_data = result
                    job = json.loads(job_data)
                    doc_id = job["doc_id"]
                    
                    await process_document(doc_id, db, redis)
                else:
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error("Worker error", error=str(e))
                await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(worker_loop())
