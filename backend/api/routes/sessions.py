"""
Sessions route - Manage chat sessions and history.
"""
from typing import List, Optional
from uuid import UUID
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.auth import get_current_user
from api.schemas import SessionResponse, SessionDetailResponse, MessageResponse, Source
from db import ChatSession, Message, User, get_chat_db

logger = structlog.get_logger()
router = APIRouter()

@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_chat_db),
):
    """List recent chat sessions."""
    # Join with messages to get preview/last message? 
    # For simplicity, just list sessions ordered by created_at desc.
    # ideally we want last_message_at, but we'll use created_at for now 
    # or join with messages.
    
    result = await db.execute(
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(ChatSession.user_id == current_user.user_id)
        .order_by(ChatSession.created_at.desc())
    )
    sessions = result.scalars().all()
    
    # Map to schema with preview from first user message
    response = []
    for session in sessions:
        messages = sorted(session.messages, key=lambda m: m.created_at)
        
        # Find first user message for preview
        preview: Optional[str] = None
        for msg in messages:
            if msg.role == "user":
                preview = msg.content[:80] + ("…" if len(msg.content) > 80 else "")
                break
        
        # Get last message timestamp
        last_message_at = messages[-1].created_at if messages else None
        
        response.append(SessionResponse(
            session_id=str(session.session_id),
            doc_id=str(session.doc_id),
            created_at=session.created_at,
            last_message_at=last_message_at,
            preview=preview or f"Chat {str(session.session_id)[:8]}…"
        ))
        
    return response

@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_chat_db),
):
    """Get chat session history."""
    # Fetch session with messages
    # Using specific query to ensure ownership
    result = await db.execute(
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(
            ChatSession.session_id == session_id,
            ChatSession.user_id == current_user.user_id
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
        
    # Sort messages by created_at (assuming they are ordered or have ID/timestamp)
    # Message model likely has created_at
    messages = sorted(session.messages, key=lambda m: m.created_at)
    
    msg_responses = []
    for msg in messages:
        sources_list = None
        if msg.sources:
            # msg.sources is JSON/dict, map to schema
            try:
                sources_list = [Source(**s) for s in msg.sources]
            except:
                sources_list = []

        msg_responses.append(MessageResponse(
            message_id=str(msg.message_id),
            role=msg.role,
            content=msg.content,
            created_at=msg.created_at,
            sources=sources_list
        ))

    return SessionDetailResponse(
        session_id=str(session.session_id),
        doc_id=str(session.doc_id),
        created_at=session.created_at,
        messages=msg_responses
    )
