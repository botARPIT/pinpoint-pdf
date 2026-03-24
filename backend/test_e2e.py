"""
End-to-End Test Script for Pinpoint PDF API.

Requires a valid JWT access token from local login/register.
"""
import os
import sys
import time

import requests

BASE_URL = "http://localhost:8000"
PDF_PATH = "sample.pdf"  # Ensure this file exists
TOKEN = os.getenv("SUPABASE_ACCESS_TOKEN") or os.getenv("TOKEN")

def print_step(msg):
    print(f"\n[STEP] {msg}")

def check_status(response, expected_code=200):
    if response.status_code != expected_code:
        print(f"FAILED: Expected {expected_code}, got {response.status_code}")
        print(response.text)
        sys.exit(1)
    return response.json()

def main():
    if not TOKEN:
        print("FAILED: Set TOKEN (or SUPABASE_ACCESS_TOKEN for backward compatibility) before running this script.")
        sys.exit(1)

    # 1. Health Check
    print_step("Checking API Health")
    resp = requests.get(f"{BASE_URL}/health")
    data = check_status(resp)
    print(f"Status: {data['status']}")

    # 2. Validate token
    print_step("Validating access token")
    headers = {"Authorization": f"Bearer {TOKEN}"}
    resp = requests.get(f"{BASE_URL}/auth/me", headers=headers)
    data = check_status(resp)
    print(f"Authenticated as {data['email']}")

    # 3. Upload PDF
    print_step("Uploading PDF")
    if not os.path.exists(PDF_PATH):
        # Create a dummy PDF if strictly needed, or failing
        print(f"Error: {PDF_PATH} not found. Please place a sample PDF in the current directory.")
        sys.exit(1)
        
    files = {"file": open(PDF_PATH, "rb")}
    resp = requests.post(f"{BASE_URL}/api/upload", headers=headers, files=files)
    data = check_status(resp, 202)
    doc_id = data["doc_id"]
    print(f"Uploaded {data['filename']} (ID: {doc_id})")

    # 4. Wait for Processing (Simulation)
    print_step("Waiting for Workers (15s)...")
    time.sleep(15)

    # 5. Chat
    print_step("Querying RAG Pipeline")
    question = "What is the summary of this document?"
    payload = {
        "doc_id": doc_id,
        "question": question
    }
    resp = requests.post(f"{BASE_URL}/api/chat", headers=headers, json=payload)
    
    # Note: If database is not updated yet (workers slow), this might fail with 409
    if resp.status_code == 409:
        print("Document not ready yet. Workers are still processing.")
    else:
        data = check_status(resp)
        print(f"Question: {question}")
        print(f"Answer: {data['answer']}")
        print(f"Sources: {len(data['sources'])}")

if __name__ == "__main__":
    main()
