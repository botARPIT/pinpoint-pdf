"""
Centralized S3/MinIO client factory.
Replaces 5 duplicate boto3.client() calls across the codebase.
"""
import boto3
from functools import lru_cache
from io import BytesIO
from typing import Any
from urllib.parse import urlparse

from botocore.config import Config
from google.api_core.exceptions import NotFound

from config import settings


class GCSClientAdapter:
    """
    Adapter to expose a minimal S3-like interface over google-cloud-storage.
    Used when STORAGE_PROVIDER=gcs and GOOGLE_STORAGE_AUTH_MODE=adc.
    """

    def __init__(self, client):
        self._client = client

    def put_object(self, Bucket: str, Key: str, Body: Any, ContentType: str | None = None, **_: Any) -> dict:
        data = Body.read() if hasattr(Body, "read") else Body
        if isinstance(data, str):
            data = data.encode("utf-8")
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("Body must be bytes, bytearray, str, or a readable stream")

        blob = self._client.bucket(Bucket).blob(Key)
        blob.upload_from_string(bytes(data), content_type=ContentType)
        return {"ETag": blob.etag}

    def get_object(self, Bucket: str, Key: str, **_: Any) -> dict:
        blob = self._client.bucket(Bucket).blob(Key)
        data = blob.download_as_bytes()
        return {"Body": BytesIO(data)}

    def list_objects_v2(self, Bucket: str, Prefix: str = "", **_: Any) -> dict:
        blobs = self._client.list_blobs(Bucket, prefix=Prefix)
        contents = [{"Key": blob.name} for blob in blobs]
        return {"Contents": contents, "IsTruncated": False}

    def delete_objects(self, Bucket: str, Delete: dict, **_: Any) -> dict:
        deleted = []
        bucket = self._client.bucket(Bucket)
        objects = Delete.get("Objects", [])
        for obj in objects:
            key = obj.get("Key")
            if not key:
                continue
            try:
                # idempotent delete behavior like S3 batch delete
                bucket.blob(key).delete()
            except NotFound:
                pass
            deleted.append({"Key": key})
        return {"Deleted": deleted}


@lru_cache(maxsize=1)
def get_s3_client():
    """
    Get a singleton S3 client configured from settings.
    
    Returns:
        boto3 S3 client
    """
    if settings.STORAGE_PROVIDER.lower() == "gcs":
        auth_mode = settings.GOOGLE_STORAGE_AUTH_MODE.lower()
        if auth_mode == "adc":
            from google.cloud import storage

            gcs_client = storage.Client(project=settings.GOOGLE_CLOUD_PROJECT or None)
            return GCSClientAdapter(gcs_client)

        return boto3.client(
            "s3",
            endpoint_url=settings.GOOGLE_STORAGE_ENDPOINT,
            aws_access_key_id=settings.GOOGLE_STORAGE_ACCESS_KEY,
            aws_secret_access_key=settings.GOOGLE_STORAGE_ACCESS_SECRET,
            region_name="auto",
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
    )


def get_raw_bucket() -> str:
    """Return the configured raw-document bucket."""
    return settings.RAW_BUCKET or settings.S3_BUCKET


def get_processed_bucket() -> str:
    """Return the configured processed-artifacts bucket."""
    return settings.PROCESSED_BUCKET or settings.S3_BUCKET


def build_object_uri(bucket: str, key: str) -> str:
    """Build canonical object URI."""
    scheme = "gs" if settings.STORAGE_PROVIDER.lower() == "gcs" else "s3"
    return f"{scheme}://{bucket}/{key}"


def parse_object_uri(uri: str) -> tuple[str, str]:
    """Parse object URI into (bucket, key)."""
    parsed = urlparse(uri)
    if parsed.scheme not in {"s3", "gs"}:
        raise ValueError(f"Unsupported object URI scheme: {parsed.scheme}")
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    if not bucket or not key:
        raise ValueError(f"Invalid object URI: {uri}")
    return bucket, key


def delete_prefix(bucket: str, prefix: str) -> None:
    """Delete all objects under a prefix."""
    s3 = get_s3_client()
    continuation_token = None

    while True:
        list_kwargs = {"Bucket": bucket, "Prefix": prefix}
        if continuation_token:
            list_kwargs["ContinuationToken"] = continuation_token

        response = s3.list_objects_v2(**list_kwargs)
        contents = response.get("Contents", [])
        if contents:
            for i in range(0, len(contents), 1000):
                batch = contents[i : i + 1000]
                s3.delete_objects(
                    Bucket=bucket,
                    Delete={
                        "Objects": [{"Key": obj["Key"]} for obj in batch],
                        "Quiet": True,
                    },
                )

        if not response.get("IsTruncated"):
            break
        continuation_token = response.get("NextContinuationToken")
