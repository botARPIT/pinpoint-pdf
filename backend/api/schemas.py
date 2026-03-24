"""
Pydantic schemas for API requests and responses.
Provides validation, serialization, and documentation.
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, validator

from config import settings


# ============================================================================
# Authentication Schemas
# ============================================================================

class AuthRequest(BaseModel):
    """Login/register request."""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class AuthTokenResponse(BaseModel):
    """JWT auth token response."""
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Authenticated user profile."""
    user_id: str
    email: str
    created_at: Optional[datetime] = None


# ============================================================================
# Upload Schemas
# ============================================================================

class UploadResponse(BaseModel):
    """PDF upload response."""
    doc_id: str = Field(..., description="Unique document identifier")
    filename: str = Field(..., description="Original filename")
    status: str = Field(default="processing", description="Processing status")
    file_size_mb: Optional[float] = Field(None, description="File size in MB")
    
    @validator('status')
    def validate_status(cls, v):
        """Ensure status is valid."""
        valid_statuses = ['processing', 'pending', 'ready', 'failed']
        if v not in valid_statuses:
            raise ValueError(f'Status must be one of {valid_statuses}')
        return v


# ============================================================================
# Chat Schemas
# ============================================================================

class ChatRequest(BaseModel):
    """Chat request with question."""
    doc_id: Optional[UUID] = Field(None, description="Document ID (optional focus document)")
    question: str = Field(..., min_length=3, max_length=1000, description="User question")
    session_id: Optional[UUID] = Field(None, description="Existing session ID (optional)")
    top_k: int = Field(settings.RAG_TOP_K, ge=1, le=50, description="Number of chunks to retrieve")
    top_n: int = Field(settings.RAG_TOP_N, ge=1, le=20, description="Number of chunks to rerank")
    
    @validator('question')
    def clean_question(cls, v):
        """Strip whitespace and validate non-empty."""
        v = v.strip()
        if not v:
            raise ValueError('Question cannot be empty')
        return v

    @validator('top_n')
    def validate_top_n(cls, v, values):
        """Ensure rerank cutoff does not exceed retrieval size."""
        top_k = values.get("top_k")
        if top_k is not None and v > top_k:
            raise ValueError("top_n must be less than or equal to top_k")
        return v


class Source(BaseModel):
    """Source citation for answer."""
    chunk_id: str
    doc_id: Optional[str] = None
    page: int = Field(..., ge=0, description="Page number (0-indexed)")
    section: str = Field(..., description="Section path")
    relevance_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Relevance score")


class ChatResponse(BaseModel):
    """Chat response with answer and sources."""
    answer: str = Field(..., min_length=1, description="Generated answer")
    sources: List[Source] = Field(default_factory=list, description="Source citations")
    session_id: str = Field(..., description="Chat session ID")
    latency_ms: int = Field(..., ge=0, description="Response latency in milliseconds")
    model_used: Optional[str] = Field(None, description="LLM model used")


# ============================================================================
# Document Status Schemas
# ============================================================================

class DocumentStatus(BaseModel):
    """Document processing status."""
    doc_id: str
    filename: str
    status: str = Field(..., description="Current processing status")
    uploaded_at: datetime
    ready_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    @validator('status')
    def validate_status(cls, v):
        """Ensure status is valid."""
        valid_statuses = ['pending', 'preprocessing', 'preprocessed', 'chunked', 'ready', 'failed']
        if v not in valid_statuses:
            raise ValueError(f'Status must be one of {valid_statuses}')
        return v


class DocumentListResponse(BaseModel):
    """List of user documents."""
    documents: List[DocumentStatus]
    total: int = Field(..., ge=0)


# ============================================================================
# Health Check Schema
# ============================================================================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(default="ok")
    env: str
    version: str
    timestamp: Optional[datetime] = None


# ============================================================================
# Session Schemas
# ============================================================================

class MessageResponse(BaseModel):
    """Message in a session."""
    message_id: str = Field(..., description="Message UUID")
    role: str = Field(..., description="user or assistant")
    content: str
    created_at: datetime
    sources: Optional[List[Source]] = None

class SessionResponse(BaseModel):
    """Chat session summary."""
    session_id: str
    doc_id: str
    created_at: datetime
    last_message_at: Optional[datetime] = None
    preview: Optional[str] = None

class SessionDetailResponse(SessionResponse):
    """Detailed session with messages."""
    messages: List[MessageResponse]
