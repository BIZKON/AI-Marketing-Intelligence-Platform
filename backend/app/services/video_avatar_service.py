"""D-ID video avatar service — generate talking head videos for AI client."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class VideoAvatarService:
    """Generate video avatars with lip-synced speech using D-ID API."""

    def __init__(self) -> None:
        self.api_key = settings.heygen_api_key  # reusing heygen key slot for D-ID
        self.base_url = "https://api.d-id.com"

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Basic {self.api_key}",
            "Content-Type": "application/json",
        }

    async def create_talk(
        self, image_url: str, audio_url: str | None = None,
        text: str | None = None, voice_id: str = "ru-RU-DmitryNeural",
    ) -> dict[str, Any]:
        """Create a talking avatar video.

        Either provide audio_url (pre-generated TTS) or text (D-ID will do TTS).
        """
        if not self.api_key:
            return {"error": "D-ID API key not configured"}

        script: dict[str, Any]
        if audio_url:
            script = {"type": "audio", "audio_url": audio_url}
        elif text:
            script = {
                "type": "text",
                "input": text,
                "provider": {"type": "microsoft", "voice_id": voice_id},
            }
        else:
            return {"error": "Either audio_url or text must be provided"}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.base_url}/talks",
                    headers=self._headers,
                    json={
                        "source_url": image_url,
                        "script": script,
                        "config": {"fluent": True, "pad_audio": 0},
                    },
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            logger.exception("Failed to create D-ID talk")
            return {"error": "Video creation failed"}

    async def get_talk_status(self, talk_id: str) -> dict[str, Any]:
        """Check the status of a talk video generation."""
        if not self.api_key:
            return {"error": "D-ID API key not configured"}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{self.base_url}/talks/{talk_id}",
                    headers=self._headers,
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            logger.exception("Failed to get D-ID talk status")
            return {"error": "Status check failed"}

    async def wait_for_video(self, talk_id: str, timeout: int = 120) -> str | None:
        """Poll until the video is ready, then return the URL."""
        for _ in range(timeout // 3):
            status = await self.get_talk_status(talk_id)
            if status.get("status") == "done":
                return status.get("result_url")
            if status.get("status") == "error":
                logger.error("D-ID video generation error: %s", status)
                return None
            await asyncio.sleep(3)
        return None
