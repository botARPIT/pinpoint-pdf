"""
Worker A - Preprocessing worker.
Dequeues PDF upload jobs, performs layout-aware parsing, and enqueues to next stage.
"""
import asyncio
import json
import time
from io import BytesIO

import structlog
from redis import asyncio as aioredis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from clients.s3 import get_processed_bucket, get_raw_bucket, get_s3_client
from config import settings
from db import Document, get_embedding_db, embedding_engine
from preprocessing.layout_parser import parse_layout
from preprocessing.table_extractor import extract_tables
from preprocessing.section_builder import build_structured_doc, structured_doc_to_json


logger = structlog.get_logger()


s3_client = get_s3_client()


async def process_pdf(doc_id: str, db: AsyncSession, redis: aioredis.Redis):
    """
    Process a single PDF: download, parse, upload structured output, enqueue next.
    
    Args:
        doc_id: Document ID
        db: Database session
        redis: Redis client
    """
    logger.info("Processing PDF", doc_id=doc_id)
    
    try:
        raw_bucket = get_raw_bucket()
        processed_bucket = get_processed_bucket()

        # Download raw PDF from S3
        s3_key = f"docs/{doc_id}/raw.pdf"
        response = s3_client.get_object(Bucket=raw_bucket, Key=s3_key)
        pdf_bytes = response["Body"].read()
        
        # Parse layout
        text_blocks = parse_layout(pdf_bytes)
        logger.info("Extracted text blocks", doc_id=doc_id, count=len(text_blocks))
        
        # Extract tables
        tables = extract_tables(BytesIO(pdf_bytes))
        logger.info("Extracted tables", doc_id=doc_id, count=len(tables))
        
        # Build structured document
        structured_doc = build_structured_doc(text_blocks, tables)
        structured_json = structured_doc_to_json(structured_doc)
        
        # Upload structured output to S3
        s3_client.put_object(
            Bucket=processed_bucket,
            Key=f"docs/{doc_id}/structured/structured_text.json",
            Body=json.dumps(structured_json["structured_text"]),
            ContentType="application/json"
        )
        s3_client.put_object(
            Bucket=processed_bucket,
            Key=f"docs/{doc_id}/structured/layout_map.json",
            Body=json.dumps(structured_json["layout_map"]),
            ContentType="application/json"
        )
        s3_client.put_object(
            Bucket=processed_bucket,
            Key=f"docs/{doc_id}/structured/tables.json",
            Body=json.dumps(structured_json["tables"]),
            ContentType="application/json"
        )
        
        # Update document status
        await db.execute(
            update(Document)
            .where(Document.doc_id == doc_id)
            .values(status="preprocessed")
        )
        await db.commit()
        
        # Enqueue to next stage
        await redis.lpush("chunk_summarize", json.dumps({"doc_id": doc_id}))
        
        logger.info("PDF preprocessing complete", doc_id=doc_id)
        
    except Exception as e:
        logger.error("Error processing PDF", doc_id=doc_id, error=str(e))
        # Update status to failed
        await db.execute(
            update(Document)
            .where(Document.doc_id == doc_id)
            .values(status="failed")
        )
        await db.commit()
        raise


async def worker_loop():
    """Main worker loop - polls Redis queue and processes jobs."""
    logger.info("Starting Worker A (Preprocessing)")
    
    # Initialize connections
    redis = await aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    
    async with AsyncSession(embedding_engine) as db:
        while True:
            try:
                # Blocking pop from queue (timeout 2 seconds)
                result = await redis.brpop("preprocess", timeout=settings.WORKER_POLL_INTERVAL)
                
                if result:
                    _, job_data = result
                    job = json.loads(job_data)
                    doc_id = job["doc_id"]
                    
                    await process_pdf(doc_id, db, redis)
                else:
                    # No job, continue polling
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error("Worker error", error=str(e))
                await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(worker_loop())
