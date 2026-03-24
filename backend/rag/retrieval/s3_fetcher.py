"""
S3 chunk fetcher — retrieves full chunk text by looking up the s3_path in the DB.
"""
import json
import uuid
from typing import Iterable

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from clients.s3 import get_s3_client, parse_object_uri
from db import Chunk as ChunkModel


logger = structlog.get_logger()
_batch_cache: dict[str, list[dict] | dict] = {}


def clear_batch_cache() -> None:
    """Clear in-process batch file cache."""
    _batch_cache.clear()


def _load_batch_data(bucket: str, key: str):
    """Load a batch payload from object storage with in-process cache."""
    cache_key = f"{bucket}/{key}"
    cached = _batch_cache.get(cache_key)
    if cached is not None:
        return cached

    s3 = get_s3_client()
    response = s3.get_object(Bucket=bucket, Key=key)
    batch_data = json.loads(response["Body"].read())
    _batch_cache[cache_key] = batch_data
    return batch_data


def _extract_text_from_batch(batch_data: list[dict] | dict, chunk_id: str, s3_path: str) -> str:
    """Extract chunk text from either batched or legacy single-chunk payload format."""
    if isinstance(batch_data, list):
        for chunk_data in batch_data:
            if chunk_data.get("chunk_id") == chunk_id:
                return chunk_data.get("text", "")
        logger.warning("Chunk not found in batch file", chunk_id=chunk_id, s3_path=s3_path)
        return ""
    if isinstance(batch_data, dict):
        return batch_data.get("text", "")
    return ""


async def fetch_chunks_from_s3(
    chunk_refs: Iterable[tuple[str, str]],
    db: AsyncSession,
) -> list[str]:
    """
    Fetch full chunk texts for multiple (chunk_id, doc_id) refs with one DB query.
    Returns texts in the same order as chunk_refs.
    """
    refs = list(chunk_refs)
    if not refs:
        return []

    normalized: list[tuple[str, str, uuid.UUID | None, uuid.UUID | None]] = []
    chunk_uuids: list[uuid.UUID] = []
    doc_uuids: list[uuid.UUID] = []

    for chunk_id, doc_id in refs:
        try:
            chunk_uuid = uuid.UUID(str(chunk_id))
            doc_uuid = uuid.UUID(str(doc_id))
            chunk_uuids.append(chunk_uuid)
            doc_uuids.append(doc_uuid)
            normalized.append((chunk_id, doc_id, chunk_uuid, doc_uuid))
        except ValueError:
            logger.warning("Invalid IDs for chunk fetch", chunk_id=chunk_id, doc_id=doc_id)
            normalized.append((chunk_id, doc_id, None, None))

    if not chunk_uuids or not doc_uuids:
        return ["" for _ in refs]

    result = await db.execute(
        select(ChunkModel).where(
            ChunkModel.chunk_id.in_(chunk_uuids),
            ChunkModel.doc_id.in_(doc_uuids),
        )
    )
    rows = result.scalars().all()
    row_map = {(str(row.chunk_id), str(row.doc_id)): row for row in rows}

    texts: list[str] = []
    for chunk_id, doc_id, chunk_uuid, doc_uuid in normalized:
        if chunk_uuid is None or doc_uuid is None:
            texts.append("")
            continue

        record = row_map.get((str(chunk_uuid), str(doc_uuid)))
        if record is None:
            logger.warning("Chunk not found in DB", chunk_id=chunk_id, doc_id=doc_id)
            texts.append("")
            continue

        try:
            bucket, key = parse_object_uri(record.s3_path)
            batch_data = _load_batch_data(bucket, key)
            texts.append(_extract_text_from_batch(batch_data, str(chunk_uuid), record.s3_path))
        except Exception as e:
            logger.error("Error fetching chunk from S3", chunk_id=chunk_id, doc_id=doc_id, error=str(e))
            texts.append("")

    return texts


async def fetch_chunk_from_s3(chunk_id: str, doc_id: str, db: AsyncSession) -> str:
    """
    Fetch full chunk text for a single chunk ref.
    Wrapper over fetch_chunks_from_s3 for backward compatibility.
    """
    texts = await fetch_chunks_from_s3([(chunk_id, doc_id)], db=db)
    return texts[0] if texts else ""
