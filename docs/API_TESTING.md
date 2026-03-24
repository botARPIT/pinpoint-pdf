# API Testing Guide

This guide describes how to test the Pinpoint PDF RAG Chatbot API using `curl` commands.

## Prerequisites

- API running on `http://localhost:8000`
- Database and Workers running
- `jq` installed (optional, for pretty-printing JSON)

## 1. Health Check

Verify the API is up and running.

```bash
curl -s http://localhost:8000/health | jq
```

**Expected Output:**
```json
{
  "status": "ok",
  "env": "dev",
  "version": "0.1.0"
}
```

## 2. Authentication (Local JWT)

Create an account and log in to get an access token:

```bash
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"your-password"}' | jq

curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"your-password"}' | jq
```

Export the returned token:

```bash
export TOKEN="<your_access_token>"
```

### Verify Token / Identity

```bash
curl -s http://localhost:8000/auth/me \
  -H "Authorization: Bearer $TOKEN" | jq
```

## 3. Upload Document

Upload a PDF file to the system.

```bash
# Verify you have a PDF named 'sample.pdf' in the current directory
curl -X POST http://localhost:8000/api/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@sample.pdf" | jq
```

Duplicate uploads from the same user are deduplicated by file content and return the existing `doc_id`.  
Use `?force_reprocess=true` on `/api/upload` to re-run processing for the same file.

**Expected Output:**
```json
{
  "doc_id": "uuid-string",
  "filename": "sample.pdf",
  "status": "processing"
}
```

**Export the `doc_id`:**

```bash
export DOC_ID="<returned_doc_id>"
```

### Wait for Processing

The system processes the PDF asynchronously:
1. **Worker A**: Parses PDF → Structured JSON (S3)
2. **Worker B**: Chunks & Summarizes → Writes chunk payload
3. **Worker C**: Embeds + Indexes in Vector Store (Pinecone) & Metadata DB

This typically takes 10-30 seconds depending on file size.

## 4. Chat with Document

Ask questions about the uploaded document.
Retrieval runs across all ready documents owned by the authenticated user.

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "doc_id": "'"$DOC_ID"'",
    "question": "What is the main topic of this document?"
  }' | jq
```

**Expected Output:**
```json
{
  "answer": "The document discusses...",
  "sources": [
    {
      "chunk_id": "...",
      "doc_id": "uuid-string",
      "page": 1,
      "section": "1. Introduction"
    }
  ],
  "session_id": "...",
  "latency_ms": 1234
}
```

## 5. End-to-End Python Script

You can also use the provided `test_e2e.py` script for automated testing:

```bash
# Install requests if needed
pip install requests

# Run script
python3 backend/test_e2e.py
```
