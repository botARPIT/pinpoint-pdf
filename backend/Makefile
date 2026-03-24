.PHONY: help dev test lint format migrate clean install worker-all worker-a worker-b worker-c audit-upload

help:
	@echo "Available commands:"
	@echo "  make install      - Install dependencies"
	@echo "  make dev          - Start dev environment (docker-compose)"
	@echo "  make test         - Run tests"
	@echo "  make lint         - Run linter (ruff)"
	@echo "  make format       - Format code (ruff)"
	@echo "  make migrate      - Run database migrations"
	@echo "  make clean        - Clean up containers and volumes"
	@echo "  make worker-all   - Start all Celery workers"
	@echo "  make worker-a     - Start Worker A (preprocessing)"
	@echo "  make worker-b     - Start Worker B (chunking)"
	@echo "  make worker-c     - Start Worker C (indexing)"
	@echo "  make audit-upload - Benchmark upload latency vs PDF size"

install:
	pip install -e ".[dev]"

dev:
	docker-compose -f infra/docker/docker-compose.yml up -d

test:
	pytest tests/ -v --tb=short

lint:
	ruff check .

format:
	ruff format .

migrate:
	python -c "import asyncio; from db import init_all_dbs; asyncio.run(init_all_dbs())"

clean:
	docker-compose -f infra/docker/docker-compose.yml down -v

# Celery workers
worker-all:
	celery -A celery_app worker --loglevel=info -Q preprocess,chunk_summarize,index_store

worker-a:
	celery -A celery_app worker --loglevel=info -Q preprocess -n worker_a@%h

worker-b:
	celery -A celery_app worker --loglevel=info -Q chunk_summarize -n worker_b@%h

worker-c:
	celery -A celery_app worker --loglevel=info -Q index_store -n worker_c@%h

audit-upload:
	python3 scripts/upload_size_audit.py
