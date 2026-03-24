"""
Worker C - Embedding and Indexing Celery task.
Reads chunk payload from S3, embeds text, indexes in Pinecone,
creates DB records, and marks document as ready.
"""
import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import List

import structlog
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from celery_app import celery_app
from clients.pinecone_client import get_pinecone_index
from clients.s3 import get_s3_client, get_processed_bucket, build_object_uri
from config import settings
from db.embedding_db import Chunk as ChunkModel, Document
from workers.utils import run_sync, get_local_session
from workers.worker_c_index_store.embedder import embed_texts


logger = structlog.get_logger()

# Max vectors per Pinecone request (~780KB per batch, well under 4MB limit)
PINECONE_BATCH = 100
# Batch size/concurrency for object writes — fewer objects and parallel uploads
GCS_WRITE_BATCH_SIZE = settings.WORKER_CHUNK_UPLOAD_BATCH_SIZE
GCS_WRITE_CONCURRENCY = settings.WORKER_CHUNK_UPLOAD_CONCURRENCY


# ---------------------------------------------------------------------------
# Decomposed helpers
# ---------------------------------------------------------------------------

def _load_payload_from_s3(doc_id: str) -> List[dict]:
    """Download chunks_payload.json from S3."""
    s3 = get_s3_client()
    processed_bucket = get_processed_bucket()
    body = s3.get_object(
        Bucket=processed_bucket,
        Key=f"docs/{doc_id}/chunks_payload.json",
    )["Body"].read()
    return json.loads(body)


async def _upload_chunks_to_s3(doc_id: str, chunks_data: List[dict]):
    """Upload chunk JSONs to S3/GCS in batches to avoid rate limits.

    Instead of N individual files, creates ceil(N/batch_size) batch files.
    Each batch file is a JSON array of chunks.
    Key format: docs/{doc_id}/chunks/batch_{batch_index}.json
    """
    s3 = get_s3_client()
    processed_bucket = get_processed_bucket()
    semaphore = asyncio.Semaphore(GCS_WRITE_CONCURRENCY)
    batches = [
        (batch_idx // GCS_WRITE_BATCH_SIZE, chunks_data[batch_idx:batch_idx + GCS_WRITE_BATCH_SIZE])
        for batch_idx in range(0, len(chunks_data), GCS_WRITE_BATCH_SIZE)
    ]

    async def _upload_batch(batch_index: int, batch: list[dict]) -> None:
        s3_key = f"docs/{doc_id}/chunks/batch_{batch_index}.json"
        body = json.dumps(batch, ensure_ascii=False)
        async with semaphore:
            await asyncio.to_thread(
                s3.put_object,
                Bucket=processed_bucket,
                Key=s3_key,
                Body=body,
                ContentType="application/json",
            )
        logger.info(
            "Uploaded chunk batch to S3",
            doc_id=doc_id,
            batch_index=batch_index,
            batch_size=len(batch),
        )

    await asyncio.gather(*[_upload_batch(batch_index, batch) for batch_index, batch in batches])
    logger.info("All chunk batches uploaded", doc_id=doc_id, total_chunks=len(chunks_data))


async def _insert_chunk_records(doc_id: str, chunks_data: List[dict], db):
    """Insert chunk rows into the database (with summary_text)."""
    processed_bucket = get_processed_bucket()
    # chunk_id -> batch index mapping for batch-object storage
    chunk_batch_map = {
        chunk["chunk_id"]: idx // GCS_WRITE_BATCH_SIZE
        for idx, chunk in enumerate(chunks_data)
    }
    rows = []
    for chunk in chunks_data:
        chunk_id = chunk["chunk_id"]
        batch_index = chunk_batch_map[chunk_id]
        s3_key = f"docs/{doc_id}/chunks/batch_{batch_index}.json"
        rows.append(
            {
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "section_path": chunk["section_path"],
                "page_start": chunk["page_start"],
                "page_end": chunk["page_end"],
                "chunk_type": chunk["chunk_type"],
                "s3_path": build_object_uri(processed_bucket, s3_key),
                "token_count": chunk["token_count"],
                "summary_text": chunk.get("summary_text", ""),
            }
        )

    if rows:
        stmt = pg_insert(ChunkModel).values(rows).on_conflict_do_nothing(index_elements=["chunk_id"])
        await db.execute(stmt)
    logger.info("Inserted chunk records", doc_id=doc_id, count=len(chunks_data))


async def _embed_and_index(doc_id: str, user_id: str, chunks_data: List[dict]):
    """Embed chunk text and upsert vectors to Pinecone."""
    # Embed
    # Summary-first retrieval: embed summaries (fallback to full chunk text).
    texts_to_embed = [
        (c["chunk_id"], c.get("summary_text") or c.get("text", ""))
        for c in chunks_data
    ]
    embeddings = await embed_texts(texts_to_embed)
    logger.info("Generated embeddings", doc_id=doc_id, count=len(embeddings))

    # Build Pinecone vectors
    chunks_by_id = {c["chunk_id"]: c for c in chunks_data}
    vectors = []
    for emb in embeddings:
        chunk = chunks_by_id[emb.chunk_id]
        vectors.append({
            "id": emb.chunk_id,
            "values": emb.vector,
            "metadata": {
                "user_id": user_id,
                "doc_id": doc_id,
                "chunk_id": emb.chunk_id,
                "section_path": chunk["section_path"],
                "page_start": chunk["page_start"],
                "page_end": chunk["page_end"],
                "chunk_type": chunk["chunk_type"],
                # LangChain requires 'text' key to reconstruct Document objects
                "text": chunk.get("summary_text") or chunk.get("text", "")[:1000],
            },
        })

    # Upsert in batches
    index = get_pinecone_index()
    vector_batches = [
        vectors[i:i + PINECONE_BATCH] for i in range(0, len(vectors), PINECONE_BATCH)
    ]
    semaphore = asyncio.Semaphore(settings.PINECONE_UPSERT_CONCURRENCY)

    async def _upsert_batch(batch_idx: int, batch: list[dict]):
        async with semaphore:
            await asyncio.to_thread(index.upsert, vectors=batch, namespace=doc_id)
        logger.info(
            "Pinecone batch upserted",
            batch=batch_idx + 1,
            size=len(batch),
            total=len(vectors),
            total_batches=len(vector_batches),
        )

    await asyncio.gather(
        *[
            _upsert_batch(batch_idx, batch)
            for batch_idx, batch in enumerate(vector_batches)
        ]
    )


async def _mark_ready(doc_id: str, db):
    """Set document status to ready."""
    await db.execute(
        update(Document)
        .where(Document.doc_id == doc_id)
        .values(status="ready", ready_at=datetime.now(timezone.utc))
    )
    await db.commit()
    logger.info("Document marked ready", doc_id=doc_id)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

async def _index_and_store(doc_id: str):
    """Orchestrate: S3 upload, DB insert, embed, index, mark ready."""
    started_at = time.perf_counter()
    stage_ms: dict[str, int] = {}

    # Load payload from S3 (written by Worker B)
    load_started = time.perf_counter()
    chunks_data = _load_payload_from_s3(doc_id)
    stage_ms["load_payload"] = int((time.perf_counter() - load_started) * 1000)
    logger.info(
        "Loaded payload from S3",
        doc_id=doc_id,
        num_chunks=len(chunks_data),
        duration_ms=stage_ms["load_payload"],
    )

    if not chunks_data:
        logger.warning("No chunks to index", doc_id=doc_id)
        async with get_local_session() as db:
            await _mark_ready(doc_id, db)
        return

    async with get_local_session() as db:
        try:
            doc_uuid = uuid.UUID(doc_id)
            doc_row = await db.get(Document, doc_uuid)
            if doc_row is None:
                raise ValueError(f"Document not found: {doc_id}")
            user_id = str(doc_row.user_id)

            upload_started = time.perf_counter()
            await _upload_chunks_to_s3(doc_id, chunks_data)
            stage_ms["upload_chunks"] = int((time.perf_counter() - upload_started) * 1000)
            logger.info(
                "Chunk objects uploaded",
                doc_id=doc_id,
                duration_ms=stage_ms["upload_chunks"],
            )

            db_insert_started = time.perf_counter()
            await _insert_chunk_records(doc_id, chunks_data, db)
            await db.commit()
            stage_ms["db_insert"] = int((time.perf_counter() - db_insert_started) * 1000)
            logger.info(
                "Chunk records committed",
                doc_id=doc_id,
                duration_ms=stage_ms["db_insert"],
            )

            embed_index_started = time.perf_counter()
            await _embed_and_index(doc_id, user_id, chunks_data)
            stage_ms["embed_and_index"] = int((time.perf_counter() - embed_index_started) * 1000)
            logger.info(
                "Embeddings indexed",
                doc_id=doc_id,
                duration_ms=stage_ms["embed_and_index"],
            )

            mark_ready_started = time.perf_counter()
            await _mark_ready(doc_id, db)
            stage_ms["mark_ready"] = int((time.perf_counter() - mark_ready_started) * 1000)
            total_duration_ms = int((time.perf_counter() - started_at) * 1000)
            accounted_ms = sum(stage_ms.values()) or 1
            logger.info(
                "Index and store orchestration complete",
                doc_id=doc_id,
                total_duration_ms=total_duration_ms,
            )
            logger.info(
                "Index and store stage breakdown",
                doc_id=doc_id,
                num_chunks=len(chunks_data),
                load_payload_ms=stage_ms.get("load_payload", 0),
                upload_chunks_ms=stage_ms.get("upload_chunks", 0),
                db_insert_ms=stage_ms.get("db_insert", 0),
                embed_and_index_ms=stage_ms.get("embed_and_index", 0),
                mark_ready_ms=stage_ms.get("mark_ready", 0),
                load_payload_pct=round(stage_ms.get("load_payload", 0) * 100.0 / accounted_ms, 2),
                upload_chunks_pct=round(stage_ms.get("upload_chunks", 0) * 100.0 / accounted_ms, 2),
                db_insert_pct=round(stage_ms.get("db_insert", 0) * 100.0 / accounted_ms, 2),
                embed_and_index_pct=round(stage_ms.get("embed_and_index", 0) * 100.0 / accounted_ms, 2),
                mark_ready_pct=round(stage_ms.get("mark_ready", 0) * 100.0 / accounted_ms, 2),
            )

        except Exception as e:
            logger.error("Error indexing chunks", doc_id=doc_id, error=str(e))
            await db.rollback()
            async with get_local_session() as err_db:
                await err_db.execute(
                    update(Document)
                    .where(Document.doc_id == doc_id)
                    .values(status="failed", error_message=str(e)[:500])
                )
                await err_db.commit()
            raise


@celery_app.task(
    bind=True,
    name="workers.worker_c_index_store.tasks.index_and_store",
    max_retries=3,
    default_retry_delay=20,
    acks_late=True,
)
def index_and_store(self, doc_id: str):
    """
    Celery task: Embed, index, and store document chunks.
    Reads payload from S3 (written by Worker B).
    On success, document status becomes 'ready'.
    """
    try:
        run_sync(_index_and_store(doc_id))
        logger.info("Index and store complete", doc_id=doc_id)

    except Exception as exc:
        logger.error(
            "Indexing failed",
            doc_id=doc_id,
            attempt=self.request.retries + 1,
            error=str(exc),
        )
        raise self.retry(exc=exc)
