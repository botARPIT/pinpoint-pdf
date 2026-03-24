"""
Pydantic schemas for RAG pipeline components.
"""
from typing import List, Optional
from pydantic import BaseModel, Field, validator


class RetrievedChunk(BaseModel):
    """Retrieved chunk with similarity score."""
    chunk_id: str = Field(..., min_length=1)
    score: float = Field(..., ge=0.0, le=1.0, description="Similarity score (0-1)")
    doc_id: str
    section_path: str
    page_start: int = Field(..., ge=0)
    page_end: int = Field(..., ge=0)
    chunk_type: str
    
    @validator('chunk_type')
    def validate_chunk_type(cls, v):
        """Ensure chunk type is valid."""
        valid_types = ['paragraph', 'table', 'figure']
        if v not in valid_types:
            raise ValueError(f'chunk_type must be one of {valid_types}')
        return v


class QueryExpansion(BaseModel):
    """Multi-query expansion result."""
    original_query: str = Field(..., min_length=1)
    expanded_queries: List[str] = Field(..., min_items=1, max_items=10)
    
    @validator('expanded_queries')
    def validate_queries(cls, v):
        """Ensure all queries are non-empty and unique."""
        cleaned = [q.strip() for q in v if q.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError('Expanded queries must be unique')
        return cleaned


class RerankResult(BaseModel):
    """Reranking result with score."""
    chunk_id: str
    rerank_score: float = Field(..., description="Reranking score")
    original_score: Optional[float] = Field(None, description="Original retrieval score")


class RAGContext(BaseModel):
    """Context for RAG generation."""
    chunks: List[str] = Field(..., min_items=1, max_items=20, description="Chunk texts")
    metadata: List[dict] = Field(..., min_items=1, description="Chunk metadata")
    
    @validator('metadata')
    def validate_metadata_length(cls, v, values):
        """Ensure metadata length matches chunks length."""
        if 'chunks' in values and len(v) != len(values['chunks']):
            raise ValueError('metadata length must match chunks length')
        return v


class RAGResponse(BaseModel):
    """Complete RAG pipeline response."""
    answer: str = Field(..., min_length=1)
    sources: List[dict] = Field(default_factory=list)
    latency_ms: int = Field(..., ge=0)
    num_chunks_retrieved: int = Field(..., ge=0)
    num_chunks_reranked: int = Field(..., ge=0)
    model_used: Optional[str] = None
    
    @validator('sources')
    def validate_sources(cls, v):
        """Ensure all sources have required fields."""
        required_fields = {'chunk_id', 'page', 'section'}
        for i, source in enumerate(v):
            missing = required_fields - set(source.keys())
            if missing:
                raise ValueError(f'Source {i} missing required fields: {missing}')
        return v
