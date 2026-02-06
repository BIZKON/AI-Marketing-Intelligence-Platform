"""Voice training service — Atlas Cloud integration for transcription and voice.

Handles audio transcription via Atlas Cloud (Whisper-compatible),
speaker diarization, and real-time voice session config.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.atlas_cloud import get_atlas_client

logger = logging.getLogger(__name__)


class VoiceService:
    """Manages voice training sessions via Atlas Cloud unified API."""

    def __init__(self) -> None:
        self.atlas = get_atlas_client()

    def get_realtime_config(self, scenario_system_prompt: str = "", voice: str = "alloy") -> dict[str, Any]:
        """Build configuration for a voice session."""
        return {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "voice": voice,
                "instructions": scenario_system_prompt,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "whisper-1"},
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

    async def transcribe_audio(self, audio_data: bytes, filename: str = "audio.webm") -> dict[str, Any]:
        """Transcribe audio using Atlas Cloud's Whisper-compatible endpoint."""
        return await self.atlas.transcribe(audio_data, filename)

    async def generate_speech(self, text: str, voice: str = "alloy") -> bytes | None:
        """Generate speech audio from text via Atlas Cloud TTS."""
        return await self.atlas.text_to_speech(text, voice=voice)

    @staticmethod
    def detect_speakers(segments: list[dict]) -> list[dict]:
        """Simple speaker diarization based on pause detection."""
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
            result.append({**seg, "speaker": current_speaker})
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
