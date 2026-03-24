"""
Worker A - Preprocessing Celery task.
Downloads PDF from S3, performs layout-aware parsing, uploads structured output,
and chains to Worker B.
"""
import json
import time

import fitz
import structlog
from sqlalchemy import update

from celery_app import celery_app
from clients.s3 import get_s3_client, get_raw_bucket, get_processed_bucket
from config import settings
from db.embedding_db import Document
from preprocessing.layout_parser import parse_pdf
from preprocessing.table_extractor import extract_tables_from_document
from preprocessing.section_builder import build_structured_output
from workers.utils import run_sync, get_local_session


logger = structlog.get_logger()


async def _process_pdf(doc_id: str):
    """Process a single PDF: download, parse, upload structured output."""
    logger.info("Processing PDF", doc_id=doc_id)
    s3 = get_s3_client()
    raw_bucket = get_raw_bucket()
    processed_bucket = get_processed_bucket()

    async with get_local_session() as db:
        try:
            started_at = time.perf_counter()
            # Mark as preprocessing
            await db.execute(
                update(Document)
                .where(Document.doc_id == doc_id)
                .values(status="preprocessing")
            )
            await db.commit()

            # Download raw PDF from S3
            s3_key = f"docs/{doc_id}/raw.pdf"
            response = s3.get_object(Bucket=raw_bucket, Key=s3_key)
            pdf_bytes = response["Body"].read()

            # Parse layout + table extraction from a single opened PDF.
            pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            try:
                parse_started = time.perf_counter()
                parsed_doc = parse_pdf(doc=pdf_doc)
                logger.info(
                    "Parsed PDF",
                    doc_id=doc_id,
                    text_blocks=parsed_doc.total_text_blocks,
                    figures=parsed_doc.total_figures,
                    duration_ms=int((time.perf_counter() - parse_started) * 1000),
                )

                if settings.ENABLE_TABLE_EXTRACTION:
                    tables_started = time.perf_counter()
                    tables = extract_tables_from_document(pdf_doc)
                    logger.info(
                        "Extracted tables",
                        doc_id=doc_id,
                        count=len(tables),
                        duration_ms=int((time.perf_counter() - tables_started) * 1000),
                    )
                else:
                    tables = []
                    logger.info("Table extraction disabled", doc_id=doc_id)
            finally:
                pdf_doc.close()

            # Build structured output
            structured = build_structured_output(
                parsed_doc,
                tables,
                include_diagnostics=False,
            )

            # --- Upload only what Worker B consumes ---
            prefix = f"docs/{doc_id}/structured"

            # 1. structured_text.json
            s3.put_object(
                Bucket=processed_bucket,
                Key=f"{prefix}/structured_text.json",
                Body=json.dumps(structured.structured_text, ensure_ascii=False),
                ContentType="application/json",
            )

            # 2. tables.json
            s3.put_object(
                Bucket=processed_bucket,
                Key=f"{prefix}/tables.json",
                Body=json.dumps(structured.tables, ensure_ascii=False),
                ContentType="application/json",
            )

            # 3. figures.json
            s3.put_object(
                Bucket=processed_bucket,
                Key=f"{prefix}/figures.json",
                Body=json.dumps(structured.figures, ensure_ascii=False),
                ContentType="application/json",
            )

            logger.info(
                "Uploaded structured output",
                doc_id=doc_id,
                tables=len(structured.tables),
                figures=len(structured.figures),
            )

            # Update document status
            await db.execute(
                update(Document)
                .where(Document.doc_id == doc_id)
                .values(status="preprocessed")
            )
            await db.commit()

            logger.info(
                "PDF preprocessing complete",
                doc_id=doc_id,
                total_duration_ms=int((time.perf_counter() - started_at) * 1000),
            )

        except Exception as e:
            logger.error("Error processing PDF", doc_id=doc_id, error=str(e))
            await db.execute(
                update(Document)
                .where(Document.doc_id == doc_id)
                .values(status="failed", error_message=str(e)[:500])
            )
            await db.commit()
            raise


@celery_app.task(
    bind=True,
    name="workers.worker_a_preprocess.tasks.preprocess_pdf",
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def preprocess_pdf(self, doc_id: str):
    """
    Celery task: Preprocess a PDF document.
    On success, automatically chains to Worker B (chunk_summarize).
    On failure after max retries, marks document as failed.
    """
    try:
        run_sync(_process_pdf(doc_id))

        # Chain to Worker B
        from workers.worker_b_chunk_summarize.tasks import chunk_and_summarize
        chunk_and_summarize.delay(doc_id)

        logger.info("Chained to Worker B", doc_id=doc_id)

    except Exception as exc:
        logger.error(
            "Preprocessing failed",
            doc_id=doc_id,
            attempt=self.request.retries + 1,
            error=str(exc),
        )
        raise self.retry(exc=exc)
