"""Video avatar service — generate talking head videos via Atlas Cloud.

Replaces direct D-ID integration with Atlas Cloud's video generation endpoints.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.atlas_cloud import get_atlas_client

logger = logging.getLogger(__name__)


class VideoAvatarService:
    """Generate video avatars with lip-synced speech via Atlas Cloud."""

    def __init__(self) -> None:
        self.atlas = get_atlas_client()

    async def create_talk(
        self, image_url: str, audio_url: str | None = None,
        text: str | None = None, voice_id: str = "ru-RU-DmitryNeural",
    ) -> dict[str, Any]:
        """Create a talking avatar video via Atlas Cloud video generation."""
        if not text and not audio_url:
            return {"error": "Either audio_url or text must be provided"}

        prompt = f"Talking head video of a person speaking: {text}" if text else "Talking head video"
        result = await self.atlas.generate_video(prompt=prompt, image_url=image_url)

        if result.get("error"):
            return result
        return {
            "id": result.get("id") or result.get("task_id", ""),
            "status": "processing",
            "result": result,
        }

    async def get_talk_status(self, talk_id: str) -> dict[str, Any]:
        """Check the status of a video generation task."""
        return await self.atlas.get_video_status(talk_id)

    async def wait_for_video(self, talk_id: str, timeout: int = 120) -> str | None:
        """Poll until the video is ready, then return the URL."""
        return await self.atlas.wait_for_video(talk_id, timeout)
