"""Voice clone service — TTS via Atlas Cloud unified API.

Replaces direct ElevenLabs integration with Atlas Cloud's TTS endpoints.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.atlas_cloud import get_atlas_client

logger = logging.getLogger(__name__)


class VoiceCloneService:
    """Manage voice generation for AI client voices via Atlas Cloud."""

    def __init__(self) -> None:
        self.atlas = get_atlas_client()

    async def list_voices(self) -> list[dict[str, Any]]:
        """List available TTS voices (OpenAI-compatible via Atlas Cloud)."""
        return [
            {"voice_id": "alloy", "name": "Alloy", "language": "multilingual"},
            {"voice_id": "echo", "name": "Echo", "language": "multilingual"},
            {"voice_id": "fable", "name": "Fable", "language": "multilingual"},
            {"voice_id": "onyx", "name": "Onyx", "language": "multilingual"},
            {"voice_id": "nova", "name": "Nova", "language": "multilingual"},
            {"voice_id": "shimmer", "name": "Shimmer", "language": "multilingual"},
        ]

    async def generate_speech(self, text: str, voice_id: str = "nova") -> bytes | None:
        """Generate speech audio from text using specified voice."""
        return await self.atlas.text_to_speech(text, voice=voice_id)

    async def create_voice(self, name: str, audio_data: bytes, filename: str = "sample.mp3") -> dict:
        """Create a custom voice. Falls back to preset voices via Atlas Cloud."""
        logger.info("Custom voice creation requested: %s (via Atlas Cloud)", name)
        return {
            "voice_id": "nova",
            "name": name,
            "status": "preset_fallback",
            "message": "Custom cloning uses preset voice via Atlas Cloud TTS",
        }

    async def delete_voice(self, voice_id: str) -> bool:
        """Delete a custom voice."""
        logger.info("Voice deletion requested: %s", voice_id)
        return True
