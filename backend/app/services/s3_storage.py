"""S3/MinIO storage service for media files (audio, video, PDF, images).

Provides async upload, download, presigned URL generation, and deletion.
"""

from __future__ import annotations

import io
import logging
import uuid
from typing import BinaryIO

import aioboto3
from botocore.config import Config as BotoConfig

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


class S3Storage:
    """Async S3-compatible object storage client."""

    def __init__(self) -> None:
        self._session = aioboto3.Session()
        self._config = BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        )

    def _client_kwargs(self) -> dict:
        return {
            "service_name": "s3",
            "endpoint_url": settings.s3_endpoint_url,
            "aws_access_key_id": settings.s3_access_key,
            "aws_secret_access_key": settings.s3_secret_key,
            "region_name": settings.s3_region,
            "config": self._config,
        }

    async def ensure_bucket(self) -> None:
        """Create the bucket if it doesn't exist."""
        async with self._session.client(**self._client_kwargs()) as s3:
            try:
                await s3.head_bucket(Bucket=settings.s3_bucket_name)
            except Exception:
                await s3.create_bucket(Bucket=settings.s3_bucket_name)
                logger.info("Created S3 bucket: %s", settings.s3_bucket_name)

    async def upload_bytes(
        self,
        data: bytes,
        key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload raw bytes and return the object key."""
        async with self._session.client(**self._client_kwargs()) as s3:
            await s3.put_object(
                Bucket=settings.s3_bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        logger.info("Uploaded %d bytes to s3://%s/%s", len(data), settings.s3_bucket_name, key)
        return key

    async def upload_fileobj(
        self,
        fileobj: BinaryIO,
        key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload a file-like object and return the object key."""
        async with self._session.client(**self._client_kwargs()) as s3:
            await s3.upload_fileobj(
                fileobj,
                settings.s3_bucket_name,
                key,
                ExtraArgs={"ContentType": content_type},
            )
        logger.info("Uploaded file to s3://%s/%s", settings.s3_bucket_name, key)
        return key

    async def download_bytes(self, key: str) -> bytes:
        """Download an object and return its bytes."""
        async with self._session.client(**self._client_kwargs()) as s3:
            resp = await s3.get_object(Bucket=settings.s3_bucket_name, Key=key)
            data = await resp["Body"].read()
        return data

    async def get_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned URL for temporary access."""
        async with self._session.client(**self._client_kwargs()) as s3:
            url = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.s3_bucket_name, "Key": key},
                ExpiresIn=expires_in,
            )
        return url

    async def delete(self, key: str) -> None:
        """Delete an object from the bucket."""
        async with self._session.client(**self._client_kwargs()) as s3:
            await s3.delete_object(Bucket=settings.s3_bucket_name, Key=key)
        logger.info("Deleted s3://%s/%s", settings.s3_bucket_name, key)

    @staticmethod
    def generate_key(prefix: str, extension: str) -> str:
        """Generate a unique object key with prefix and extension.

        Example: reports/voice/a3b4c5d6.ogg
        """
        return f"{prefix}/{uuid.uuid4().hex[:16]}.{extension}"
