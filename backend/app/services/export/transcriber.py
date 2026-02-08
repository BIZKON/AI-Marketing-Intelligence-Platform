"""Whisper transcriber — transcribe audio via Atlas Cloud.

Wraps the AtlasCloudClient transcription endpoint and provides
convenience methods for transcribing from raw bytes or S3 keys.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.atlas_cloud import AtlasCloudClient, get_atlas_client
from app.services.s3_storage import S3Storage

logger = logging.getLogger(__name__)


class WhisperTranscriber:
    """Transcribe audio files using Atlas Cloud's Whisper-compatible API.

    Uses the project-wide :class:`AtlasCloudClient` singleton by default.
    """

    def __init__(
        self,
        atlas_client: AtlasCloudClient | None = None,
    ) -> None:
        self._atlas = atlas_client or get_atlas_client()

    async def transcribe_audio(
        self,
        audio_data: bytes,
        language: str = "ru",
    ) -> dict[str, Any]:
        """Transcribe raw audio bytes.

        Parameters
        ----------
        audio_data:
            Raw audio file content (OGG, MP3, M4A, etc.).
        language:
            ISO-639-1 language code for transcription hint.

        Returns
        -------
        dict
            Keys: ``text`` (transcribed string), ``language``, ``duration``.
            On error the ``text`` will be empty and an ``error`` key is present.
        """
        if not audio_data:
            logger.warning("Empty audio data provided for transcription")
            return {"text": "", "language": language, "duration": 0.0}

        logger.info(
            "Transcribing audio: %d bytes, language=%s",
            len(audio_data),
            language,
        )

        result = await self._atlas.transcribe(
            audio_data=audio_data,
            filename="audio.ogg",
            language=language,
        )

        if result.get("error"):
            logger.error("Transcription error: %s", result["error"])
            return {
                "text": "",
                "language": language,
                "duration": 0.0,
                "error": result["error"],
            }

        text = result.get("text", "").strip()
        duration = result.get("duration", 0.0)

        # verbose_json format may include duration at top level
        if not duration:
            segments = result.get("segments", [])
            if segments:
                last_segment = segments[-1]
                duration = last_segment.get("end", 0.0)

        logger.info(
            "Transcription complete: %d chars, %.1fs duration",
            len(text),
            duration or 0.0,
        )

        return {
            "text": text,
            "language": result.get("language", language),
            "duration": float(duration) if duration else 0.0,
        }

    async def transcribe_from_s3(
        self,
        s3_storage: S3Storage,
        s3_key: str,
        language: str = "ru",
    ) -> dict[str, Any]:
        """Download audio from S3 and transcribe it.

        Parameters
        ----------
        s3_storage:
            S3 storage client for downloading the file.
        s3_key:
            Object key of the audio file in S3.
        language:
            ISO-639-1 language code for transcription hint.

        Returns
        -------
        dict
            Same shape as :meth:`transcribe_audio`.
        """
        logger.info("Downloading audio from S3: %s", s3_key)

        try:
            audio_data = await s3_storage.download_bytes(s3_key)
        except Exception:
            logger.exception("Failed to download audio from S3: %s", s3_key)
            return {
                "text": "",
                "language": language,
                "duration": 0.0,
                "error": f"S3 download failed for key: {s3_key}",
            }

        return await self.transcribe_audio(audio_data, language=language)
