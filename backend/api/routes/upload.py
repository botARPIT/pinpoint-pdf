"""
Upload route - PDF upload and ingestion job enqueuing.
"""
import hashlib
import uuid

import structlog
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from api.schemas import UploadResponse
from clients.gemini import ensure_genai_auth_configured
from clients.s3 import get_s3_client, get_raw_bucket
from config import settings
from db import Document, User, get_embedding_db


logger = structlog.get_logger()
router = APIRouter()


def _to_upload_status(document_status: str) -> str:
    """Map internal doc status to upload response status."""
    if document_status in {"pending", "preprocessing", "preprocessed", "chunked"}:
        return "processing"
    if document_status == "ready":
        return "ready"
    return "failed"


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_pdf(
    file: UploadFile = File(...),
    force_reprocess: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_embedding_db),
):
    """
    Upload a PDF file for processing.

    - Validates file type and size
    - Uploads to raw object storage bucket
    - Creates/updates deduplicated document record
    - Enqueues preprocessing job
    """
    # Validate file type
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a PDF",
        )

    # Fail fast when Gemini auth is not configured to avoid guaranteed async worker failure.
    try:
        ensure_genai_auth_configured()
    except Exception as e:
        logger.error("Gemini auth misconfigured", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Gemini auth is not configured correctly",
        )

    # Read file
    contents = await file.read()
    file_size_mb = len(contents) / (1024 * 1024)

    # Validate size
    if file_size_mb > settings.MAX_PDF_SIZE_MB:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds {settings.MAX_PDF_SIZE_MB}MB limit",
        )

    # Deterministic doc_id for duplicate detection (same user + same bytes).
    content_sha256 = hashlib.sha256(contents).hexdigest()
    doc_uuid = uuid.uuid5(current_user.user_id, content_sha256)
    doc_id = str(doc_uuid)

    # Check existing upload with same deterministic ID.
    result = await db.execute(
        select(Document).where(
            Document.doc_id == doc_uuid,
            Document.user_id == current_user.user_id,
        )
    )
    existing_doc = result.scalar_one_or_none()

    if existing_doc and not force_reprocess and existing_doc.status != "failed":
        logger.info(
            "Duplicate upload detected",
            doc_id=doc_id,
            status=existing_doc.status,
            user_id=str(current_user.user_id),
        )
        return UploadResponse(
            doc_id=doc_id,
            filename=existing_doc.filename,
            status=_to_upload_status(existing_doc.status),
            file_size_mb=round(file_size_mb, 2),
        )

    # Upload raw file
    s3 = get_s3_client()
    raw_bucket = get_raw_bucket()
    raw_key = f"docs/{doc_id}/raw.pdf"
    try:
        s3.put_object(
            Bucket=raw_bucket,
            Key=raw_key,
            Body=contents,
            ContentType="application/pdf",
        )
    except ClientError as e:
        logger.error(
            "Object storage upload failed",
            bucket=raw_bucket,
            key=raw_key,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Object storage upload failed: {e.response.get('Error', {}).get('Code', 'ClientError')}",
        )
    except Exception as e:
        logger.error(
            "Object storage upload failed",
            bucket=raw_bucket,
            key=raw_key,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Object storage upload failed",
        )

    # Create/update document record
    if existing_doc:
        existing_doc.filename = file.filename
        existing_doc.status = "pending"
        existing_doc.ready_at = None
        existing_doc.error_message = None
        existing_doc.s3_prefix = f"docs/{doc_id}"
        await db.commit()
    else:
        document = Document(
            doc_id=doc_uuid,
            user_id=current_user.user_id,
            filename=file.filename,
            status="pending",
            s3_prefix=f"docs/{doc_id}",
        )
        db.add(document)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            result = await db.execute(
                select(Document).where(
                    Document.doc_id == doc_uuid,
                    Document.user_id == current_user.user_id,
                )
            )
            winner_doc = result.scalar_one_or_none()
            if winner_doc is None:
                raise
            return UploadResponse(
                doc_id=str(winner_doc.doc_id),
                filename=winner_doc.filename,
                status=_to_upload_status(winner_doc.status),
                file_size_mb=round(file_size_mb, 2),
            )

    # Dispatch Celery task for preprocessing
    from workers.worker_a_preprocess.tasks import preprocess_pdf
    try:
        preprocess_pdf.delay(doc_id)
    except Exception as e:
        logger.error("Failed to enqueue preprocessing task", doc_id=doc_id, error=str(e))
        await db.execute(
            update(Document)
            .where(Document.doc_id == doc_uuid)
            .values(status="failed", error_message="Failed to enqueue preprocessing task")
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Processing queue unavailable",
        )

    logger.info("PDF uploaded", doc_id=doc_id, filename=file.filename, user_id=str(current_user.user_id))

    return UploadResponse(
        doc_id=doc_id,
        filename=file.filename,
        status="processing",
        file_size_mb=round(file_size_mb, 2),
    )
