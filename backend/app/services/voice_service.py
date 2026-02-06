"""Voice training service — OpenAI Realtime API integration for voice mode.

Handles WebSocket session management, audio streaming, and transcription
for voice-based sales training sessions.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime"
PROXY_REALTIME_URL = "wss://proxy.alchemya-trainer.ru/realtime"


class VoiceService:
    """Manages voice training sessions via OpenAI Realtime API."""

    def __init__(self) -> None:
        self.api_key = settings.openai_api_key

    def get_realtime_config(self, scenario_system_prompt: str, voice: str = "alloy") -> dict[str, Any]:
        """Build configuration for an OpenAI Realtime session.

        Returns config dict to be sent as session.update event.
        """
        return {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "voice": voice,
                "instructions": scenario_system_prompt,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": "whisper-1",
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                },
                "temperature": 0.8,
                "max_response_output_tokens": 500,
            },
        }

    def get_websocket_headers(self) -> dict[str, str]:
        """Return headers needed for the OpenAI Realtime WebSocket connection."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

    def get_proxy_url(self) -> str:
        """Return the proxy WebSocket URL for Realtime API."""
        return PROXY_REALTIME_URL

    async def transcribe_audio(self, audio_data: bytes, filename: str = "audio.webm") -> dict[str, Any]:
        """Transcribe audio using OpenAI Whisper API.

        Returns dict with transcript text and segments.
        """
        if not self.api_key:
            return {"text": "", "error": "OpenAI API key not configured"}

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files={"file": (filename, audio_data, "audio/webm")},
                    data={
                        "model": "whisper-1",
                        "response_format": "verbose_json",
                        "timestamp_granularities[]": "segment",
                        "language": "ru",
                    },
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            logger.exception("Whisper transcription failed")
            return {"text": "", "error": "Transcription failed"}

    @staticmethod
    def detect_speakers(segments: list[dict]) -> list[dict]:
        """Simple speaker diarization based on pause detection.

        Alternates between 'Admin' and 'Client' on significant pauses.
        """
        if not segments:
            return []

        current_speaker = "Admin"
        last_end = 0.0
        result = []

        for seg in segments:
            start = seg.get("start", 0.0)
            if start - last_end > 1.5:
                current_speaker = "Client" if current_speaker == "Admin" else "Admin"
            last_end = seg.get("end", start)
            result.append({
                **seg,
                "speaker": current_speaker,
            })

        return result

    @staticmethod
    def format_transcript(speaker_segments: list[dict]) -> str:
        """Format speaker-labeled segments into a readable transcript."""
        lines = []
        current_speaker = None

        for seg in speaker_segments:
            speaker = seg.get("speaker", "Unknown")
            text = seg.get("text", "").strip()
            if not text:
                continue

            if speaker != current_speaker:
                current_speaker = speaker
                lines.append(f"\n{speaker}: {text}")
            else:
                lines[-1] += f" {text}" if lines else f"{speaker}: {text}"

        return "\n".join(lines).strip()
