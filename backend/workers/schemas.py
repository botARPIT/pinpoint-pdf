"""
Pydantic schemas for worker job payloads.
"""
from typing import List, Optional
from pydantic import BaseModel, Field, validator


class PreprocessJob(BaseModel):
    """Worker A preprocessing job."""
    doc_id: str = Field(..., min_length=1, description="Document ID to process")
    retry_count: int = Field(default=0, ge=0, le=3, description="Retry attempt number")
    
    @validator('doc_id')
    def validate_doc_id(cls, v):
        """Ensure doc_id is valid UUID format."""
        import uuid
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError('doc_id must be a valid UUID')
        return v


class ChunkSummarizeJob(BaseModel):
    """Worker B chunking and summarization job."""
    doc_id: str = Field(..., min_length=1)
    retry_count: int = Field(default=0, ge=0, le=3)


class IndexStoreJob(BaseModel):
    """Worker C indexing and storage job."""
    doc_id: str = Field(..., min_length=1)
    chunks: List[dict] = Field(..., min_items=1, description="Chunk data")
    summaries: List[dict] = Field(..., min_items=1, description="Summary data")
    retry_count: int = Field(default=0, ge=0, le=3)
    
    @validator('summaries')
    def validate_summaries_length(cls, v, values):
        """Ensure summaries length matches chunks length."""
        if 'chunks' in values and len(v) != len(values['chunks']):
            raise ValueError('summaries length must match chunks length')
        return v
    
    @validator('chunks')
    def validate_chunk_structure(cls, v):
        """Ensure all chunks have required fields."""
        required_fields = {'chunk_id', 'doc_id', 'text', 'section_path', 'page_start', 'page_end', 'chunk_type', 'token_count'}
        for i, chunk in enumerate(v):
            missing = required_fields - set(chunk.keys())
            if missing:
                raise ValueError(f'Chunk {i} missing required fields: {missing}')
        return v


class WorkerStatus(BaseModel):
    """Worker health status."""
    worker_name: str = Field(..., description="Worker identifier")
    status: str = Field(..., description="Current status")
    jobs_processed: int = Field(default=0, ge=0, description="Total jobs processed")
    jobs_failed: int = Field(default=0, ge=0, description="Total jobs failed")
    uptime_seconds: int = Field(default=0, ge=0, description="Worker uptime")
    last_job_at: Optional[str] = Field(None, description="Timestamp of last job")
    
    @validator('status')
    def validate_status(cls, v):
        """Ensure status is valid."""
        valid_statuses = ['idle', 'processing', 'error', 'stopped']
        if v not in valid_statuses:
            raise ValueError(f'status must be one of {valid_statuses}')
        return v
