"""Media processor — download Telegram media and upload to S3.

Handles photo, voice, video_note, and document media types with
rate limiting between downloads to avoid Telegram flood bans.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from typing import Any

from telethon import TelegramClient
from telethon.tl.types import (
    Document,
    MessageMediaDocument,
    MessageMediaPhoto,
)

from app.services.s3_storage import S3Storage

logger = logging.getLogger(__name__)

# Rate-limiting between media downloads
_DOWNLOAD_SLEEP_SECONDS = 1.0

# Content type mapping for S3 uploads
_MEDIA_CONTENT_TYPES: dict[str, str] = {
    "photo": "image/jpeg",
    "voice": "audio/ogg",
    "video_note": "video/mp4",
    "video": "video/mp4",
    "audio": "audio/mpeg",
    "document": "application/octet-stream",
}


class MediaProcessor:
    """Download media from Telegram messages and upload to S3 storage."""

    def __init__(self, s3_storage: S3Storage) -> None:
        self._s3 = s3_storage

    async def download_media(
        self,
        client: TelegramClient,
        message: Any,
        export_id: str,
    ) -> dict[str, Any] | None:
        """Download media from a Telethon message and upload to S3.

        Parameters
        ----------
        client:
            Connected Telethon client for downloading.
        message:
            The Telethon ``Message`` object containing media.
        export_id:
            Export job identifier used as S3 key prefix.

        Returns
        -------
        dict or None
            On success: ``s3_key``, ``media_type``, ``file_size``, ``duration``.
            Returns ``None`` if the message has no downloadable media.
        """
        media = message.media
        if media is None:
            return None

        media_type = _classify_media(media)
        if media_type is None:
            logger.debug("Unsupported media type on message %d", message.id)
            return None

        duration = _extract_duration(media)
        extension = _get_extension(media, media_type)

        # Download to a temporary file
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{extension}")
        try:
            os.close(tmp_fd)

            downloaded_path = await client.download_media(
                message,
                file=tmp_path,
            )
            if downloaded_path is None:
                logger.warning(
                    "Failed to download media for message %d",
                    message.id,
                )
                return None

            file_size = os.path.getsize(downloaded_path)
            if file_size == 0:
                logger.warning(
                    "Downloaded empty file for message %d",
                    message.id,
                )
                return None

            # Read file content for S3 upload
            with open(downloaded_path, "rb") as f:
                file_data = f.read()

            # Build S3 key: exports/<export_id>/<media_type>/<msg_id>.<ext>
            s3_key = (
                f"exports/{export_id}/{media_type}/{message.id}.{extension}"
            )
            content_type = _MEDIA_CONTENT_TYPES.get(
                media_type,
                "application/octet-stream",
            )

            await self._s3.upload_bytes(
                data=file_data,
                key=s3_key,
                content_type=content_type,
            )

            logger.info(
                "Uploaded media for message %d: %s (%d bytes)",
                message.id,
                s3_key,
                file_size,
            )

            # Rate-limit between downloads
            await asyncio.sleep(_DOWNLOAD_SLEEP_SECONDS)

            return {
                "s3_key": s3_key,
                "media_type": media_type,
                "file_size": file_size,
                "duration": duration,
            }

        except Exception:
            logger.exception(
                "Error downloading media for message %d",
                message.id,
            )
            return None

        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    async def get_media_url(self, s3_key: str) -> str:
        """Generate a presigned URL for accessing media from S3.

        Parameters
        ----------
        s3_key:
            The S3 object key for the media file.

        Returns
        -------
        str
            A presigned URL valid for 1 hour.
        """
        return await self._s3.get_presigned_url(s3_key, expires_in=3600)


# ── Module-level helpers ──────────────────────────────────────────────────


def _classify_media(media: Any) -> str | None:
    """Classify Telegram media into a type string."""
    if isinstance(media, MessageMediaPhoto):
        return "photo"

    if isinstance(media, MessageMediaDocument):
        doc = media.document
        if not isinstance(doc, Document):
            return None

        for attr in doc.attributes:
            attr_name = type(attr).__name__
            if attr_name == "DocumentAttributeAudio":
                return "voice" if getattr(attr, "voice", False) else "audio"
            if attr_name == "DocumentAttributeVideo":
                return (
                    "video_note"
                    if getattr(attr, "round_message", False)
                    else "video"
                )

        return "document"

    return None


def _extract_duration(media: Any) -> float | None:
    """Extract duration in seconds from audio/video media, if available."""
    if not isinstance(media, MessageMediaDocument):
        return None

    doc = media.document
    if not isinstance(doc, Document):
        return None

    for attr in doc.attributes:
        attr_name = type(attr).__name__
        if attr_name in ("DocumentAttributeAudio", "DocumentAttributeVideo"):
            duration = getattr(attr, "duration", None)
            if duration is not None:
                return float(duration)

    return None


def _get_extension(media: Any, media_type: str) -> str:
    """Determine the file extension based on media type and MIME type."""
    # Default extensions by media type
    defaults: dict[str, str] = {
        "photo": "jpg",
        "voice": "ogg",
        "video_note": "mp4",
        "video": "mp4",
        "audio": "mp3",
        "document": "bin",
    }

    if isinstance(media, MessageMediaDocument):
        doc = media.document
        if isinstance(doc, Document) and doc.mime_type:
            mime = doc.mime_type
            # Common MIME-to-extension mappings
            mime_map: dict[str, str] = {
                "audio/ogg": "ogg",
                "audio/mpeg": "mp3",
                "audio/mp4": "m4a",
                "video/mp4": "mp4",
                "image/jpeg": "jpg",
                "image/png": "png",
                "application/pdf": "pdf",
            }
            ext = mime_map.get(mime)
            if ext:
                return ext

            # Try to get extension from filename attribute
            for attr in doc.attributes:
                file_name = getattr(attr, "file_name", None)
                if file_name and "." in file_name:
                    return file_name.rsplit(".", 1)[-1].lower()

    return defaults.get(media_type, "bin")
