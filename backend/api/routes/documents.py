"""
Documents route - Manage uploaded documents.
"""
import asyncio
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from api.schemas import DocumentListResponse, DocumentStatus
from clients.pinecone_client import get_pinecone_index
from clients.s3 import delete_prefix, get_raw_bucket, get_processed_bucket
from config import settings
from db import Document, User, get_embedding_db

logger = structlog.get_logger()
router = APIRouter()


def _delete_storage_prefixes(prefix: str) -> None:
    """Delete document objects from raw and processed buckets."""
    raw_bucket = get_raw_bucket()
    processed_bucket = get_processed_bucket()
    for bucket in {raw_bucket, processed_bucket}:
        delete_prefix(bucket, prefix)


def _delete_pinecone_namespace(doc_id: str) -> None:
    """Delete all vectors in a document namespace."""
    index = get_pinecone_index()
    index.delete(delete_all=True, namespace=doc_id)


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_embedding_db),
):
    """List all documents uploaded by the current user."""
    # Query documents
    result = await db.execute(
        select(Document)
        .where(Document.user_id == current_user.user_id)
        .order_by(Document.uploaded_at.desc())
    )
    documents = result.scalars().all()
    
    # Map to schema
    doc_list = []
    for doc in documents:
        doc_list.append(DocumentStatus(
            doc_id=str(doc.doc_id),
            filename=doc.filename,
            status=doc.status,
            uploaded_at=doc.uploaded_at,
            ready_at=doc.ready_at,
            error_message=doc.error_message
        ))
        
    return DocumentListResponse(
        documents=doc_list,
        total=len(doc_list)
    )

@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_embedding_db),
):
    """Delete a document."""
    # Check if exists and belongs to user
    result = await db.execute(
        select(Document).where(
            Document.doc_id == doc_id,
            Document.user_id == current_user.user_id
        )
    )
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    doc_id_str = str(doc_id)
    storage_prefix = doc.s3_prefix or f"docs/{doc_id_str}"

    # Cleanup object storage data for this document.
    try:
        await asyncio.to_thread(_delete_storage_prefixes, storage_prefix)
    except Exception as e:
        logger.error("Failed deleting document storage data", doc_id=doc_id_str, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to delete document objects from storage",
        )

    # Cleanup vector namespace if Pinecone is configured.
    if settings.PINECONE_API_KEY and not settings.PINECONE_API_KEY.startswith("your-"):
        try:
            await asyncio.to_thread(_delete_pinecone_namespace, doc_id_str)
        except Exception as e:
            logger.error("Failed deleting document vectors", doc_id=doc_id_str, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to delete document vectors from index",
            )

    # Delete from DB
    await db.delete(doc)
    await db.commit()

    logger.info("Document deleted", doc_id=doc_id_str, user_id=str(current_user.user_id))

    return None
