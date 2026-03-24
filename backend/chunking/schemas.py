"""
Pydantic schemas for chunking and document processing.
"""
from typing import List, Optional
from pydantic import BaseModel, Field, validator


class TextBlock(BaseModel):
    """Parsed text block from PDF."""
    page: int = Field(..., ge=0, description="Page number (0-indexed)")
    text: str = Field(..., min_length=1, description="Text content")
    bbox: tuple[float, float, float, float] = Field(..., description="Bounding box (x0, y0, x1, y1)")
    is_heading: bool = Field(default=False, description="Whether this is a heading")
    font_size: float = Field(..., gt=0, description="Font size in points")
    section_path: str = Field(default="", description="Hierarchical section path")
    
    @validator('bbox')
    def validate_bbox(cls, v):
        """Ensure bbox has valid coordinates."""
        x0, y0, x1, y1 = v
        if x1 <= x0 or y1 <= y0:
            raise ValueError('Invalid bounding box: x1 must be > x0 and y1 must be > y0')
        return v


class Table(BaseModel):
    """Extracted table from PDF."""
    page: int = Field(..., ge=0, description="Page number")
    headers: Optional[List[str]] = Field(None, description="Table headers")
    rows: List[List[str]] = Field(default_factory=list, description="Table rows")
    bbox: tuple[float, float, float, float] = Field(..., description="Bounding box")
    
    @validator('rows')
    def validate_rows(cls, v, values):
        """Ensure all rows have same length as headers if headers exist."""
        if 'headers' in values and values['headers']:
            header_len = len(values['headers'])
            for i, row in enumerate(v):
                if len(row) != header_len:
                    raise ValueError(f'Row {i} length ({len(row)}) does not match headers length ({header_len})')
        return v


class StructuredDoc(BaseModel):
    """Complete structured document representation."""
    structured_text: List[dict] = Field(default_factory=list, description="Ordered text blocks")
    layout_map: dict = Field(default_factory=dict, description="Page-level layout info")
    tables: List[dict] = Field(default_factory=list, description="Extracted tables")
    page_metadata: dict = Field(default_factory=dict, description="Document metadata")
    
    @validator('page_metadata')
    def validate_metadata(cls, v):
        """Ensure required metadata fields exist."""
        required_fields = ['total_pages', 'total_text_blocks', 'total_tables']
        for field in required_fields:
            if field not in v:
                raise ValueError(f'Missing required metadata field: {field}')
        return v


class Chunk(BaseModel):
    """Enhanced chunk with detailed metadata."""
    chunk_id: str = Field(..., min_length=1, description="Unique chunk identifier")
    doc_id: str = Field(..., min_length=1, description="Parent document ID")
    section_path: str = Field(..., description="Hierarchical section path")
    section_level: int = Field(..., ge=0, le=10, description="Section nesting level")
    page_start: int = Field(..., ge=0, description="Starting page number")
    page_end: int = Field(..., ge=0, description="Ending page number")
    chunk_type: str = Field(..., description="Chunk type: paragraph, table, or figure")
    token_count: int = Field(..., ge=0, description="Estimated token count")
    text: str = Field(..., min_length=1, description="Chunk text content")
    table_id: Optional[str] = Field(None, description="Table ID if chunk_type=table")
    figure_id: Optional[str] = Field(None, description="Figure ID if chunk_type=figure")
    
    @validator('chunk_type')
    def validate_chunk_type(cls, v):
        """Ensure chunk type is valid."""
        valid_types = ['paragraph', 'table', 'figure']
        if v not in valid_types:
            raise ValueError(f'chunk_type must be one of {valid_types}')
        return v
    
    @validator('page_end')
    def validate_page_range(cls, v, values):
        """Ensure page_end >= page_start."""
        if 'page_start' in values and v < values['page_start']:
            raise ValueError('page_end must be >= page_start')
        return v
    
    @validator('table_id')
    def validate_table_id(cls, v, values):
        """Ensure table_id is set if chunk_type is table."""
        if 'chunk_type' in values and values['chunk_type'] == 'table' and not v:
            raise ValueError('table_id must be set when chunk_type is table')
        return v


class Summary(BaseModel):
    """Chunk summary."""
    chunk_id: str = Field(..., min_length=1)
    summary_text: str = Field(..., min_length=10, max_length=500, description="Summary (10-500 chars)")
    
    @validator('summary_text')
    def clean_summary(cls, v):
        """Strip whitespace and validate."""
        v = v.strip()
        if not v:
            raise ValueError('Summary cannot be empty')
        return v


class Embedding(BaseModel):
    """Embedding vector."""
    chunk_id: str = Field(..., min_length=1)
    vector: List[float] = Field(..., min_items=1, max_items=2048, description="Embedding vector")
    model: Optional[str] = Field(None, description="Embedding model used")
    
    @validator('vector')
    def validate_vector(cls, v):
        """Ensure all values are finite."""
        import math
        for i, val in enumerate(v):
            if not math.isfinite(val):
                raise ValueError(f'Vector contains non-finite value at index {i}')
        return v
