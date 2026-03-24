"""
End-to-end performance benchmark for the Pinpoint PDF pipeline.

Measures:
  1. Upload latency (API → S3)
  2. Ingestion time (Workers A → B → C until status=ready)
  3. Chat/RAG query latency (with per-step breakdown from response)

Usage:
  python scripts/benchmark.py <path-to-pdf> [--question "your question"]
  python scripts/benchmark.py sample.pdf --question "Summarize the key findings"

Requires: requests (pip install requests)
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

import requests

BASE_URL = os.getenv("API_URL", "http://localhost:8000")
EMAIL = os.getenv("BENCH_EMAIL", "bench@test.com")
PASSWORD = os.getenv("BENCH_PASSWORD", "benchmark123")
POLL_INTERVAL = 2  # seconds between status polls
MAX_WAIT = 300  # max seconds to wait for processing


# ── Helpers ──────────────────────────────────────────────────────────

class Timer:
    """Simple context-manager timer."""
    def __init__(self, label: str):
        self.label = label
        self.elapsed_ms = 0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed_ms = int((time.perf_counter() - self._start) * 1000)


def fail(msg: str):
    print(f"\n❌ FAILED: {msg}")
    sys.exit(1)


def get_token() -> str:
    """Register or login to get a JWT token."""
    # Try register first
    resp = requests.post(f"{BASE_URL}/auth/register", json={"email": EMAIL, "password": PASSWORD})
    if resp.status_code in (200, 201):
        return resp.json()["access_token"]

    # Already exists → login
    resp = requests.post(f"{BASE_URL}/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if resp.status_code == 200:
        return resp.json()["access_token"]

    fail(f"Auth failed: {resp.status_code} — {resp.text}")


def poll_until_ready(doc_id: str, headers: dict) -> tuple[str, int]:
    """Poll document status until ready/failed. Returns (status, poll_time_ms)."""
    start = time.perf_counter()
    last_status = "unknown"

    while (time.perf_counter() - start) < MAX_WAIT:
        resp = requests.get(f"{BASE_URL}/api/documents", headers=headers)
        if resp.status_code != 200:
            time.sleep(POLL_INTERVAL)
            continue

        docs = resp.json().get("documents", [])
        target = next((d for d in docs if d["doc_id"] == doc_id), None)

        if target:
            last_status = target["status"]
            status_icon = {
                "pending": "⏳", "preprocessing": "🔄", "preprocessed": "📄",
                "chunked": "✂️", "ready": "✅", "failed": "❌"
            }.get(last_status, "❓")
            elapsed = int((time.perf_counter() - start) * 1000)
            print(f"  {status_icon} {last_status:>15s}  ({elapsed:,}ms)", end="\r")

            if last_status == "ready":
                print()  # newline after carriage return
                return "ready", int((time.perf_counter() - start) * 1000)
            if last_status == "failed":
                print()
                return "failed", int((time.perf_counter() - start) * 1000)

        time.sleep(POLL_INTERVAL)

    print()
    return last_status, int((time.perf_counter() - start) * 1000)


# ── Main Benchmark ───────────────────────────────────────────────────

def run_benchmark(pdf_path: str, question: str):
    print("=" * 60)
    print("  PINPOINT PDF — END-TO-END PERFORMANCE BENCHMARK")
    print("=" * 60)
    print(f"  PDF:      {os.path.basename(pdf_path)} ({os.path.getsize(pdf_path) / 1024 / 1024:.1f} MB)")
    print(f"  Question: {question}")
    print(f"  API:      {BASE_URL}")
    print(f"  Time:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    results = {}

    # ── Step 0: Health Check ──────────────────────────────────────────
    print("\n[0/4] Health check...")
    resp = requests.get(f"{BASE_URL}/health")
    if resp.status_code != 200:
        fail(f"API not reachable at {BASE_URL}")
    print(f"  ✅ API is healthy (env={resp.json().get('env')})")

    # ── Step 1: Auth ──────────────────────────────────────────────────
    print("\n[1/4] Authenticating...")
    with Timer("auth") as t:
        token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    results["auth_ms"] = t.elapsed_ms
    print(f"  ✅ Authenticated in {t.elapsed_ms}ms")

    # ── Step 2: Upload ────────────────────────────────────────────────
    print("\n[2/4] Uploading PDF...")
    with Timer("upload") as t:
        with open(pdf_path, "rb") as f:
            resp = requests.post(
                f"{BASE_URL}/api/upload",
                headers=headers,
                files={"file": (os.path.basename(pdf_path), f, "application/pdf")},
            )
    if resp.status_code not in (200, 201, 202):
        fail(f"Upload failed: {resp.status_code} — {resp.text}")

    upload_data = resp.json()
    doc_id = upload_data["doc_id"]
    results["upload_ms"] = t.elapsed_ms
    results["upload_status"] = upload_data.get("status")
    print(f"  ✅ Uploaded in {t.elapsed_ms}ms  (doc_id={doc_id})")

    # If the doc was already processed (duplicate), skip polling
    if upload_data.get("status") == "ready":
        print("  ℹ️  Document already processed (duplicate detected)")
        results["processing_ms"] = 0
    else:
        # ── Step 3: Wait for Processing ───────────────────────────────
        print("\n[3/4] Waiting for ingestion pipeline...")
        print(f"  Polling every {POLL_INTERVAL}s (max {MAX_WAIT}s):")
        status, processing_ms = poll_until_ready(doc_id, headers)
        results["processing_ms"] = processing_ms

        if status == "ready":
            print(f"  ✅ Processing complete in {processing_ms:,}ms ({processing_ms / 1000:.1f}s)")
        elif status == "failed":
            fail(f"Processing failed after {processing_ms:,}ms")
        else:
            fail(f"Processing timed out after {MAX_WAIT}s (last status: {status})")

    # ── Step 4: Chat / RAG Query ─────────────────────────────────────
    print("\n[4/4] Querying RAG pipeline...")
    payload = {"doc_id": doc_id, "question": question}
    with Timer("chat") as t:
        resp = requests.post(f"{BASE_URL}/api/chat", headers=headers, json=payload)

    if resp.status_code != 200:
        fail(f"Chat failed: {resp.status_code} — {resp.text}")

    chat_data = resp.json()
    results["chat_total_ms"] = t.elapsed_ms
    results["chat_server_ms"] = chat_data.get("latency_ms", 0)
    results["chat_network_overhead_ms"] = t.elapsed_ms - chat_data.get("latency_ms", 0)
    results["num_sources"] = len(chat_data.get("sources", []))
    results["answer_length"] = len(chat_data.get("answer", ""))
    results["model_used"] = chat_data.get("model_used", "unknown")

    print(f"  ✅ Answer received in {t.elapsed_ms:,}ms")
    print(f"     Server-side:     {results['chat_server_ms']:,}ms")
    print(f"     Network overhead: {results['chat_network_overhead_ms']:,}ms")
    print(f"     Sources cited:    {results['num_sources']}")
    print(f"     Answer length:    {results['answer_length']} chars")

    # ── Summary ──────────────────────────────────────────────────────
    total = results["upload_ms"] + results["processing_ms"] + results["chat_total_ms"]

    print("\n" + "=" * 60)
    print("  BENCHMARK RESULTS")
    print("=" * 60)
    print(f"  {'Upload (API → S3):':<30} {results['upload_ms']:>8,}ms")
    print(f"  {'Ingestion (Workers A→B→C):':<30} {results['processing_ms']:>8,}ms")
    print(f"  {'RAG Query (total):':<30} {results['chat_total_ms']:>8,}ms")
    print(f"    {'├─ Server-side pipeline:':<30} {results['chat_server_ms']:>8,}ms")
    print(f"    {'└─ Network overhead:':<30} {results['chat_network_overhead_ms']:>8,}ms")
    print(f"  {'─' * 40}")
    print(f"  {'TOTAL END-TO-END:':<30} {total:>8,}ms  ({total / 1000:.1f}s)")
    print(f"  {'Model:':<30} {results['model_used']}")
    print("=" * 60)

    # ── Print answer preview ─────────────────────────────────────────
    answer = chat_data.get("answer", "")
    print(f"\n📝 Answer preview:\n{answer[:500]}{'...' if len(answer) > 500 else ''}\n")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pinpoint PDF E2E Performance Benchmark")
    parser.add_argument("pdf", help="Path to the PDF file to test")
    parser.add_argument("--question", "-q", default="What are the main topics covered in this document?",
                        help="Question to ask the RAG pipeline")
    parser.add_argument("--api-url", default=None, help="API base URL (default: http://localhost:8000)")
    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        fail(f"File not found: {args.pdf}")

    if args.api_url:
        BASE_URL = args.api_url

    run_benchmark(args.pdf, args.question)
