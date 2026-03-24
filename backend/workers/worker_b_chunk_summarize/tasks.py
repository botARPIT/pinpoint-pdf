"""
Worker B - Chunking and Summarization Celery task.
Downloads structured doc from S3, chunks it, generates summaries,
writes payload to S3, and chains to Worker C (passing only doc_id).
"""
import json
import time

import structlog
from sqlalchemy import update

from celery_app import celery_app
from clients.s3 import get_s3_client, get_processed_bucket
from db.embedding_db import Document
from chunking.section_chunker import chunk_document
from workers.utils import run_sync, get_local_session
from workers.worker_b_chunk_summarize.summarizer import summarize_chunks


logger = structlog.get_logger()


async def _chunk_and_summarize(doc_id: str):
    """Chunk document, generate summaries, write payload to S3."""
    logger.info("Chunking and summarizing", doc_id=doc_id)
    s3 = get_s3_client()
    processed_bucket = get_processed_bucket()

    async with get_local_session() as db:
        try:
            started_at = time.perf_counter()
            # Download structured doc from S3
            structured_text = json.loads(
                s3.get_object(
                    Bucket=processed_bucket,
                    Key=f"docs/{doc_id}/structured/structured_text.json",
                )["Body"].read()
            )

            tables = json.loads(
                s3.get_object(
                    Bucket=processed_bucket,
                    Key=f"docs/{doc_id}/structured/tables.json",
                )["Body"].read()
            )

            # Load figure metadata (optional)
            figures = []
            try:
                figures = json.loads(
                    s3.get_object(
                        Bucket=processed_bucket,
                        Key=f"docs/{doc_id}/structured/figures.json",
                    )["Body"].read()
                )
            except Exception:
                logger.info("No figures.json found", doc_id=doc_id)

            # Chunk
            chunk_started = time.perf_counter()
            structured_doc = {
                "structured_text": structured_text,
                "tables": tables,
                "figures": figures,
            }
            chunks = chunk_document(structured_doc, doc_id=doc_id)
            logger.info(
                "Document chunked",
                doc_id=doc_id,
                num_chunks=len(chunks),
                duration_ms=int((time.perf_counter() - chunk_started) * 1000),
            )

            # Summarize (extractive — instant)
            summarize_started = time.perf_counter()
            summaries = summarize_chunks(chunks)
            summary_by_chunk_id = {s.chunk_id: s.summary_text for s in summaries}
            logger.info(
                "Summaries generated",
                doc_id=doc_id,
                count=len(summaries),
                duration_ms=int((time.perf_counter() - summarize_started) * 1000),
            )

            # Build payload
            chunks_data = [
                {
                    "chunk_id": c.chunk_id,
                    "doc_id": c.doc_id,
                    "text": c.text,
                    "section_path": c.section_path,
                    "section_level": c.section_level,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "chunk_type": c.chunk_type,
                    "token_count": c.token_count,
                    "table_id": c.table_id,
                    "figure_id": c.figure_id,
                    "summary_text": summary_by_chunk_id.get(c.chunk_id, ""),
                }
                for c in chunks
            ]

            # Write payload to S3 (instead of passing via Celery args)
            s3.put_object(
                Bucket=processed_bucket,
                Key=f"docs/{doc_id}/chunks_payload.json",
                Body=json.dumps(chunks_data, ensure_ascii=False),
                ContentType="application/json",
            )
            logger.info("Payload written to S3", doc_id=doc_id, num_chunks=len(chunks_data))

            # Update status
            await db.execute(
                update(Document)
                .where(Document.doc_id == doc_id)
                .values(status="chunked")
            )
            await db.commit()
            logger.info(
                "Chunk and summarize complete",
                doc_id=doc_id,
                total_duration_ms=int((time.perf_counter() - started_at) * 1000),
            )

        except Exception as e:
            logger.error("Error chunking document", doc_id=doc_id, error=str(e))
            await db.execute(
                update(Document)
                .where(Document.doc_id == doc_id)
                .values(status="failed", error_message=str(e)[:500])
            )
            await db.commit()
            raise


@celery_app.task(
    bind=True,
    name="workers.worker_b_chunk_summarize.tasks.chunk_and_summarize",
    max_retries=3,
    default_retry_delay=15,
    acks_late=True,
)
def chunk_and_summarize(self, doc_id: str):
    """
    Celery task: Chunk and summarize a preprocessed document.
    On success, chains to Worker C (passing only doc_id).
    """
    try:
        run_sync(_chunk_and_summarize(doc_id))

        # Chain to Worker C — only pass doc_id, it reads payload from S3
        from workers.worker_c_index_store.tasks import index_and_store
        index_and_store.delay(doc_id=doc_id)

        logger.info("Chained to Worker C", doc_id=doc_id)

    except Exception as exc:
        logger.error(
            "Chunking failed",
            doc_id=doc_id,
            attempt=self.request.retries + 1,
            error=str(exc),
        )
        raise self.retry(exc=exc)
