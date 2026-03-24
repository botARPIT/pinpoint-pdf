"""
Chat route - RAG-based question answering.
"""
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from api.schemas import ChatRequest, ChatResponse, Source
from config import settings
from db import ChatSession, Document, Message, User, get_chat_db, get_embedding_db


logger = structlog.get_logger()
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    embedding_db: AsyncSession = Depends(get_embedding_db),
    chat_db: AsyncSession = Depends(get_chat_db),
):
    """
    Ask a question across the user's uploaded PDFs.

    - Validates requested document ownership (if provided)
    - Gathers all ready documents for the user
    - Creates/reuses chat session
    - Calls multi-document RAG pipeline
    - Saves messages to chat history
    """
    # Load all user documents
    result = await embedding_db.execute(
        select(Document)
        .where(Document.user_id == current_user.user_id)
        .order_by(Document.uploaded_at.desc())
    )
    user_docs = result.scalars().all()
    if not user_docs:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No documents uploaded for this user",
        )

    # If caller supplies doc_id, validate ownership.
    requested_doc = None
    if request.doc_id is not None:
        requested_doc = next((d for d in user_docs if d.doc_id == request.doc_id), None)
        if requested_doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

    # Retrieval scope:
    # - If doc_id is provided, use only that document.
    # - Otherwise, search all ready documents owned by the user.
    if requested_doc is not None:
        if requested_doc.status != "ready":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Requested document is not ready yet",
            )
        ready_docs = [requested_doc]
    else:
        ready_docs = [doc for doc in user_docs if doc.status == "ready"]
    if not ready_docs:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No ready documents available yet",
        )
    ready_doc_ids = [str(doc.doc_id) for doc in ready_docs]

    # Get or create chat session
    if request.session_id:
        result = await chat_db.execute(
            select(ChatSession).where(
                ChatSession.session_id == request.session_id,
                ChatSession.user_id == current_user.user_id,
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found for this user",
            )
    else:
        # Keep a representative doc_id for session metadata.
        primary_doc = requested_doc or ready_docs[0]
        session = ChatSession(
            user_id=current_user.user_id,
            doc_id=primary_doc.doc_id,
        )
        chat_db.add(session)
        await chat_db.flush()

    # Save user message
    user_message = Message(
        session_id=session.session_id,
        role="user",
        content=request.question,
    )
    chat_db.add(user_message)

    # Run RAG pipeline
    from rag.pipeline import run_rag_pipeline

    answer, sources_data, latency_ms = await run_rag_pipeline(
        doc_ids=ready_doc_ids,
        question=request.question,
        db=embedding_db,
        top_k=request.top_k,
        top_n=request.top_n,
    )

    sources = [Source(**s) for s in sources_data]

    # Save assistant message
    assistant_message = Message(
        session_id=session.session_id,
        role="assistant",
        content=answer,
        sources=[s.model_dump() for s in sources],
        latency_ms=latency_ms,
    )
    chat_db.add(assistant_message)

    await chat_db.commit()

    logger.info(
        "Chat response",
        session_id=str(session.session_id),
        num_docs=len(ready_doc_ids),
    )

    return ChatResponse(
        answer=answer,
        sources=sources,
        session_id=str(session.session_id),
        latency_ms=latency_ms,
        model_used=settings.GEMINI_MODEL,
    )
