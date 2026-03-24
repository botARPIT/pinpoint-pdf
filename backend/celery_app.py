"""
Celery application configuration.
Uses Redis as both broker and result backend.
"""
import os
import sys
from celery import Celery

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import settings


celery_app = Celery(
    "pinpoint_pdf",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "workers.worker_a_preprocess.tasks",
        "workers.worker_b_chunk_summarize.tasks",
        "workers.worker_c_index_store.tasks",
    ],
)

# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # Timezone
    timezone="UTC",
    enable_utc=True,
    
    # Retry
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Concurrency
    worker_prefetch_multiplier=1,
    worker_concurrency=2,
    
    # Result expiry (24 hours)
    result_expires=86400,
    
    # Task routes — each worker type has its own queue
    task_routes={
        "workers.worker_a_preprocess.tasks.*": {"queue": "preprocess"},
        "workers.worker_b_chunk_summarize.tasks.*": {"queue": "chunk_summarize"},
        "workers.worker_c_index_store.tasks.*": {"queue": "index_store"},
    },
    
    # Default retry policy
    task_default_retry_delay=5,
    task_max_retries=3,
)
