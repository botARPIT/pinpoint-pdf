"""
Worker C - Embedding and Indexing worker.
Implements the detailed indexing strategy:
1. Embed chunk summaries using Google text-embedding-004
2. Store chunks in S3 (docs/{doc_id}/chunks/*.json)
3. Insert embeddings into vector store (Pinecone/Chroma)
4. Create DB records (chunks table + summary_index_map table)
"""
import asyncio
import json
from typing import List

import structlog
from pinecone import Pinecone, ServerlessSpec
from redis import asyncio as aioredis
from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from clients.s3 import build_object_uri, get_processed_bucket, get_s3_client
from config import settings
from db import Chunk as ChunkModel, Document, SummaryIndexMap, embedding_engine
from workers.worker_c_index_store.embedder import embed_texts


logger = structlog.get_logger()


s3_client = get_s3_client()

# Pinecone client
pc = Pinecone(api_key=settings.PINECONE_API_KEY)


def get_or_create_index():
    """Get or create Pinecone index."""
    index_name = settings.PINECONE_INDEX
    
    if index_name not in pc.list_indexes().names():
        pc.create_index(
            name=index_name,
            dimension=768,  # text-embedding-004 dimension
            metric="cosine",
            spec=ServerlessSpec(
                cloud=settings.PINECONE_CLOUD,
                region=settings.PINECONE_REGION
            )
        )
        logger.info("Created Pinecone index", index_name=index_name)
    
    return pc.Index(index_name)


async def process_chunks(doc_id: str, chunks_data: List[dict], summaries_data: List[dict], db: AsyncSession):
    """
    Process chunks: embed summaries, upload to S3, index in vector store, create DB records.
    
    Args:
        doc_id: Document ID
        chunks_data: List of chunk dicts
        summaries_data: List of summary dicts
        db: Database session
    """
    logger.info("Indexing chunks", doc_id=doc_id, num_chunks=len(chunks_data))
    
    try:
        processed_bucket = get_processed_bucket()

        # Step 1: Upload chunks to S3
        for chunk in chunks_data:
            chunk_id = chunk["chunk_id"]
            s3_key = f"docs/{doc_id}/chunks/{chunk_id}.json"
            
            s3_client.put_object(
                Bucket=processed_bucket,
                Key=s3_key,
                Body=json.dumps(chunk),
                ContentType="application/json"
            )
            
            # Insert chunk record into DB
            await db.execute(
                insert(ChunkModel).values(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    section_path=chunk["section_path"],
                    page_start=chunk["page_start"],
                    page_end=chunk["page_end"],
                    chunk_type=chunk["chunk_type"],
                    s3_path=build_object_uri(processed_bucket, s3_key),
                    token_count=chunk["token_count"]
                )
            )
        
        logger.info("Uploaded chunks to S3", doc_id=doc_id)
        
        # Step 2: Embed summaries
        summary_map = {s["chunk_id"]: s["summary_text"] for s in summaries_data}
        texts_to_embed = [(chunk_id, summary_map.get(chunk_id, "")) for chunk_id in [c["chunk_id"] for c in chunks_data]]
        
        embeddings = await embed_texts(texts_to_embed)
        logger.info("Generated embeddings", doc_id=doc_id, num_embeddings=len(embeddings))
        
        # Step 3: Insert into vector store (Pinecone)
        index = get_or_create_index()
        
        vectors_to_upsert = []
        for embedding in embeddings:
            chunk = next(c for c in chunks_data if c["chunk_id"] == embedding.chunk_id)
            
            # Minimal metadata for vector store
            metadata = {
                "doc_id": doc_id,
                "chunk_id": embedding.chunk_id,
                "section_path": chunk["section_path"],
                "page_start": chunk["page_start"],
                "page_end": chunk["page_end"],
                "chunk_type": chunk["chunk_type"]
            }
            
            vectors_to_upsert.append({
                "id": embedding.chunk_id,
                "values": embedding.vector,
                "metadata": metadata
            })
        
        # Batch upsert to Pinecone
        index.upsert(vectors=vectors_to_upsert, namespace=doc_id)
        logger.info("Indexed in Pinecone", doc_id=doc_id, namespace=doc_id)
        
        # Step 4: Create summary_index_map records
        for embedding in embeddings:
            await db.execute(
                insert(SummaryIndexMap).values(
                    chunk_id=embedding.chunk_id,
                    vector_id=embedding.chunk_id  # Pinecone ID = chunk_id
                )
            )
        
        await db.commit()
        
        # Update document status to ready
        await db.execute(
            update(Document)
            .where(Document.doc_id == doc_id)
            .values(status="ready")
        )
        await db.commit()
        
        logger.info("Indexing complete", doc_id=doc_id)
        
    except Exception as e:
        logger.error("Error indexing chunks", doc_id=doc_id, error=str(e))
        await db.execute(
            update(Document)
            .where(Document.doc_id == doc_id)
            .values(status="failed")
        )
        await db.commit()
        raise


async def worker_loop():
    """Main worker loop."""
    logger.info("Starting Worker C (Index + Store)")
    
    redis = await aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    
    async with AsyncSession(embedding_engine) as db:
        while True:
            try:
                result = await redis.brpop("index_store", timeout=settings.WORKER_POLL_INTERVAL)
                
                if result:
                    _, job_data = result
                    job = json.loads(job_data)
                    doc_id = job["doc_id"]
                    chunks_data = job["chunks"]
                    summaries_data = job["summaries"]
                    
                    await process_chunks(doc_id, chunks_data, summaries_data, db)
                else:
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error("Worker error", error=str(e))
                await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(worker_loop())
