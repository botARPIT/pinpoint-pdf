# Pydantic Validation Schema Documentation

## Overview

This document describes the comprehensive Pydantic validation schemas added throughout the Pinpoint PDF RAG Chatbot system. All schemas enforce strict type safety, data validation, and provide automatic API documentation.

## Schema Modules

### 1. API Schemas (`backend/api/schemas.py`)

#### Authentication

Authentication uses Supabase magic-link access tokens.  
Backend auth endpoints currently expose user identity via `/auth/me`.

**UserResponse**
- `user_id`: str
- `email`: str
- `created_at`: Optional[datetime]

#### Upload

**UploadResponse**
- `doc_id`: str (document UUID)
- `filename`: str
- `status`: str (validated: processing/pending/ready/failed)
- `file_size_mb`: Optional[float]
- Validators: Status must be in allowed list

#### Chat

**ChatRequest**
- `doc_id`: Optional[UUID] (optional focus document)
- `question`: str (3-1000 chars, auto-stripped)
- `session_id`: Optional[UUID]
- `top_k`: int (1-50, default: 10)
- `top_n`: int (1-20, default: 5)
- Validators: Question cannot be empty after stripping

**Source**
- `chunk_id`: str
- `doc_id`: Optional[str]
- `page`: int (≥0, 0-indexed)
- `section`: str
- `relevance_score`: Optional[float] (0.0-1.0)

**ChatResponse**
- `answer`: str (min 1 char)
- `sources`: List[Source]
- `session_id`: str
- `latency_ms`: int (≥0)
- `model_used`: Optional[str]

#### Document Status

**DocumentStatus**
- `doc_id`: str
- `filename`: str
- `status`: str (validated: pending/preprocessing/preprocessed/chunked/ready/failed)
- `uploaded_at`: datetime
- `ready_at`: Optional[datetime]
- `error_message`: Optional[str]

**HealthResponse**
- `status`: str (default: "ok")
- `env`: str
- `version`: str
- `timestamp`: Optional[datetime]

---

### 2. Chunking Schemas (`backend/chunking/schemas.py`)

**TextBlock**
- `page`: int (≥0)
- `text`: str (min 1 char)
- `bbox`: tuple[float, float, float, float] (x0, y0, x1, y1)
- `is_heading`: bool
- `font_size`: float (>0)
- `section_path`: str
- Validators: Bbox coordinates must be valid (x1>x0, y1>y0)

**Table**
- `page`: int (≥0)
- `headers`: Optional[List[str]]
- `rows`: List[List[str]]
- `bbox`: tuple[float, float, float, float]
- Validators: All rows must match header length

**StructuredDoc**
- `structured_text`: List[dict]
- `layout_map`: dict
- `tables`: List[dict]
- `page_metadata`: dict
- Validators: Metadata must contain total_pages, total_text_blocks, total_tables

**Chunk**
- `chunk_id`: str (min 1 char)
- `doc_id`: str (min 1 char)
- `section_path`: str
- `section_level`: int (0-10)
- `page_start`: int (≥0)
- `page_end`: int (≥0, must be ≥ page_start)
- `chunk_type`: str (paragraph/table/figure)
- `token_count`: int (≥0)
- `text`: str (min 1 char)
- `table_id`: Optional[str] (required if chunk_type=table)
- `figure_id`: Optional[str]
- Validators: 
  - chunk_type must be valid
  - page_end ≥ page_start
  - table_id required for table chunks

**Summary**
- `chunk_id`: str (min 1 char)
- `summary_text`: str (10-500 chars, auto-stripped)
- Validators: Summary cannot be empty

**Embedding**
- `chunk_id`: str (min 1 char)
- `vector`: List[float] (1-2048 items, all finite)
- `model`: Optional[str]
- Validators: All vector values must be finite (no NaN/Inf)

---

### 3. RAG Schemas (`backend/rag/schemas.py`)

**RetrievedChunk**
- `chunk_id`: str (min 1 char)
- `score`: float (0.0-1.0)
- `doc_id`: str
- `section_path`: str
- `page_start`: int (≥0)
- `page_end`: int (≥0)
- `chunk_type`: str (validated)

**QueryExpansion**
- `original_query`: str (min 1 char)
- `expanded_queries`: List[str] (1-10 items, unique)
- Validators: All queries must be non-empty and unique

**RerankResult**
- `chunk_id`: str
- `rerank_score`: float
- `original_score`: Optional[float]

**RAGContext**
- `chunks`: List[str] (1-20 items)
- `metadata`: List[dict] (must match chunks length)
- Validators: Metadata length must equal chunks length

**RAGResponse**
- `answer`: str (min 1 char)
- `sources`: List[dict] (must have chunk_id, page, section)
- `latency_ms`: int (≥0)
- `num_chunks_retrieved`: int (≥0)
- `num_chunks_reranked`: int (≥0)
- `model_used`: Optional[str]
- Validators: All sources must have required fields

---

### 4. Worker Schemas (`backend/workers/schemas.py`)

**PreprocessJob**
- `doc_id`: str (min 1 char, valid UUID)
- `retry_count`: int (0-3)
- Validators: doc_id must be valid UUID format

**ChunkSummarizeJob**
- `doc_id`: str (min 1 char)
- `retry_count`: int (0-3)

**IndexStoreJob**
- `doc_id`: str (min 1 char)
- `chunks`: List[dict] (min 1 item, validated structure)
- `summaries`: List[dict] (min 1 item, must match chunks length)
- `retry_count`: int (0-3)
- Validators:
  - Summaries length must match chunks length
  - All chunks must have required fields (chunk_id, doc_id, text, section_path, page_start, page_end, chunk_type, token_count)

**WorkerStatus**
- `worker_name`: str
- `status`: str (idle/processing/error/stopped)
- `jobs_processed`: int (≥0)
- `jobs_failed`: int (≥0)
- `uptime_seconds`: int (≥0)
- `last_job_at`: Optional[str]

---

## Validation Benefits

1. **Type Safety**: All fields have strict type annotations
2. **Automatic Validation**: Invalid data raises clear errors before processing
3. **API Documentation**: FastAPI auto-generates OpenAPI docs from schemas
4. **Data Integrity**: Validators ensure business logic constraints (e.g., page_end ≥ page_start)
5. **Security**: UUID/shape validation on inputs and strict response schemas
6. **Consistency**: Standardized error messages across the system

## Usage Examples

### API Request Validation

```python
# Automatic validation on request
@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    # request.question is guaranteed to be 3-1000 chars, stripped
    # request.top_k is guaranteed to be 1-50
    ...
```

### Worker Job Validation

```python
from workers.schemas import IndexStoreJob

# Validate job payload before processing
job_data = json.loads(message)
job = IndexStoreJob(**job_data)  # Raises ValidationError if invalid

# job.chunks and job.summaries are guaranteed to have matching lengths
# All chunks are guaranteed to have required fields
```

### Chunk Creation Validation

```python
from chunking.schemas import Chunk

chunk = Chunk(
    chunk_id="doc123_section1_chunk1",
    doc_id="doc123",
    section_path="Introduction",
    section_level=1,
    page_start=1,
    page_end=2,
    chunk_type="paragraph",
    token_count=350,
    text="..."
)
# Raises ValidationError if:
# - chunk_type not in [paragraph, table, figure]
# - page_end < page_start
# - chunk_type=table but table_id is None
```

## Error Handling

All validation errors return HTTP 422 with detailed error messages:

```json
{
  "detail": [
    {
      "loc": ["body", "question"],
      "msg": "String should have at least 3 characters",
      "type": "string_too_short"
    }
  ]
}
```
