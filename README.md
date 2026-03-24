# Pinpoint PDF - RAG Chatbot

Layout-aware PDF RAG chatbot with async ingestion, summary-first indexing, retrieval over all ready documents owned by the user, and local JWT auth.

## Architecture

- **3 Postgres databases**: user profile mapping (`5432`), document/chunk metadata (`5433`), chat history (`5434`)
- **Redis + Celery**: async ingestion pipeline orchestration
- **S3/MinIO**: raw PDFs, structured outputs, and chunk payload storage
- **GCS (S3-compatible mode)**: supported via HMAC keys for raw/processed buckets
- **Pinecone**: vector store (namespace per document)
- **Google Gemini**: chat + embedding models
- **Sentence Transformers**: local cross-encoder reranking
- **Local Auth**: email/password login + JWT authorization

## Quick Start

### 1. Prerequisites

- Python `3.10+`
- Node.js `18+` and npm
- Docker & Docker Compose
- Google AI API key
- Pinecone API key

### 2. Backend Setup

```bash
cd backend

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Edit backend/.env.dev and set:
# - GOOGLE_API_KEY
# - PINECONE_API_KEY
# - STORAGE_PROVIDER (s3 or gcs)
# - RAW_BUCKET / PROCESSED_BUCKET
# - GOOGLE_STORAGE_AUTH_MODE (adc or hmac)
# - GOOGLE_CLOUD_PROJECT (optional for adc)
# - GOOGLE_STORAGE_ACCESS_KEY / GOOGLE_STORAGE_ACCESS_SECRET (for hmac mode)
# - GOOGLE_GENAI_AUTH_MODE (auto, api_key, or adc)
# - JWT_SECRET
# - JWT_ALGORITHM (default HS256)
# - JWT_EXPIRY_HOURS (default 24)
```

### 3. Start Infrastructure

```bash
cd backend
make dev
make migrate
```

### 4. Run Backend Services

Run each command in a separate terminal from `backend/`:

```bash
# API
uvicorn api.main:app --reload

# Celery workers
make worker-a
make worker-b
make worker-c
```

### 5. Run Frontend

```bash
cd frontend
npm install
npm run dev
```

### 6. API Smoke Test

```bash
# Upload a PDF
curl -X POST http://localhost:8000/api/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@sample.pdf"

# Chat across all ready documents owned by the authenticated user.
# Optional: include doc_id to set session metadata focus.
curl -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"doc_id":"<doc_id>","question":"What is this document about?"}'
```

Duplicate uploads by the same user are deduplicated by content hash and return the existing `doc_id` unless `force_reprocess=true` is provided.

`<token>` must be a JWT access token returned by `POST /auth/login` or `POST /auth/register`.

## Development

From `backend/`:

```bash
make test
make lint
make format
```

From `frontend/`:

```bash
npm run lint
npm run build
```

## Project Structure

```text
pinpoint-pdf/
├── backend/              # FastAPI API, workers, RAG, DB models, infra
├── frontend/             # React + Vite UI
├── docs/                 # Project docs
└── README.md
```

## License

MIT
