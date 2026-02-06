"""ElevenLabs voice cloning service — create custom voices for training."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class VoiceCloneService:
    """Manage ElevenLabs voice cloning for AI client voices."""

    def __init__(self) -> None:
        self.api_key = settings.elevenlabs_api_key
        self.base_url = "https://api.elevenlabs.io/v1"

    @property
    def _headers(self) -> dict[str, str]:
        return {"xi-api-key": self.api_key}

    async def list_voices(self) -> list[dict[str, Any]]:
        """List available voices."""
        if not self.api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{self.base_url}/voices",
                    headers=self._headers,
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("voices", [])
        except Exception:
            logger.exception("Failed to list ElevenLabs voices")
            return []

    async def create_voice(self, name: str, audio_data: bytes, filename: str = "sample.mp3") -> dict:
        """Create a cloned voice from an audio sample.

        Requires at least 1 minute of clear audio.
        """
        if not self.api_key:
            return {"error": "ElevenLabs API key not configured"}

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{self.base_url}/voices/add",
                    headers=self._headers,
                    files={"files": (filename, audio_data, "audio/mpeg")},
                    data={"name": name},
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            logger.exception("Failed to create voice clone")
            return {"error": "Voice clone creation failed"}

    async def generate_speech(
        self, text: str, voice_id: str | None = None,
        stability: float = 0.5, similarity_boost: float = 0.75,
    ) -> bytes | None:
        """Generate speech audio from text using specified voice."""
        if not self.api_key:
            return None

        vid = voice_id or settings.elevenlabs_voice_id
        if not vid:
            return None

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.base_url}/text-to-speech/{vid}",
                    headers={**self._headers, "Content-Type": "application/json"},
                    json={
                        "text": text,
                        "model_id": "eleven_multilingual_v2",
                        "voice_settings": {
                            "stability": stability,
                            "similarity_boost": similarity_boost,
                        },
                    },
                )
                resp.raise_for_status()
                return resp.content
        except Exception:
            logger.exception("Failed to generate speech")
            return None

    async def delete_voice(self, voice_id: str) -> bool:
        """Delete a cloned voice."""
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.delete(
                    f"{self.base_url}/voices/{voice_id}",
                    headers=self._headers,
                )
                return resp.status_code == 200
        except Exception:
            logger.exception("Failed to delete voice")
            return False
