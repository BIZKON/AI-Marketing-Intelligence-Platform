"""Unified Atlas Cloud AI client — single API gateway for all AI services.

Atlas Cloud (atlascloud.ai) provides OpenAI-compatible endpoints for 300+ models:
  - LLM (chat completions): Claude, GPT, DeepSeek, Qwen, Gemini
  - Audio (Whisper transcription, TTS)
  - Image generation (FLUX, Stable Diffusion)
  - Video generation (Seedance, Wan, Veo, Sora)

All services use a single API key and base URL.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

ATLAS_BASE_URL = settings.atlas_cloud_base_url
ATLAS_API_KEY = settings.atlas_cloud_api_key

# Default models — can be overridden per-service
DEFAULT_CHAT_MODEL = "anthropic/claude-sonnet-4-20250514"
DEFAULT_WHISPER_MODEL = "openai/whisper-1"
DEFAULT_TTS_MODEL = "openai/tts-1"
DEFAULT_IMAGE_MODEL = "black-forest-labs/flux-2-dev/text-to-image"
DEFAULT_VIDEO_MODEL = "bytedance/seedance-v1.5-pro/text-to-video"

# Circuit breaker
_circuit_state: dict[str, dict] = {}
CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_RECOVERY_TIMEOUT = 60


def _check_circuit(service: str) -> bool:
    state = _circuit_state.get(service)
    if not state:
        return True
    if state["failures"] < CIRCUIT_FAILURE_THRESHOLD:
        return True
    if time.monotonic() - state["last_failure"] > CIRCUIT_RECOVERY_TIMEOUT:
        state["failures"] = 0
        return True
    return False


def _record_failure(service: str) -> None:
    state = _circuit_state.setdefault(service, {"failures": 0, "last_failure": 0.0})
    state["failures"] += 1
    state["last_failure"] = time.monotonic()


def _record_success(service: str) -> None:
    _circuit_state.pop(service, None)


class AtlasCloudClient:
    """Unified client for Atlas Cloud API — replaces direct Anthropic/OpenAI/ElevenLabs/D-ID calls."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key or ATLAS_API_KEY
        self.base_url = (base_url or ATLAS_BASE_URL).rstrip("/")

    @property
    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # ── Chat Completions (LLM) ────────────────────────────────────────────

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str = DEFAULT_CHAT_MODEL,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        stream: bool = False,
    ) -> dict[str, Any]:
        """OpenAI-compatible chat completions via Atlas Cloud.

        Returns dict with 'content' (text), 'tokens' (usage), 'model'.
        """
        if not self.api_key:
            logger.warning("ATLAS_CLOUD_API_KEY not set")
            return {"content": "[AI недоступен: API ключ не настроен]", "tokens": 0}

        if not _check_circuit("atlas_chat"):
            return {"content": "[AI временно недоступен. Сервис восстановится автоматически.]", "tokens": 0}

        # Build messages list with optional system prompt
        all_messages = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._auth_headers,
                    json={
                        "model": model,
                        "messages": all_messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "stream": stream,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            _record_success("atlas_chat")

            # Parse OpenAI-format response
            choices = data.get("choices", [])
            content = choices[0]["message"]["content"] if choices else ""
            usage = data.get("usage", {})
            tokens = usage.get("total_tokens", 0)

            return {"content": content, "tokens": tokens, "model": data.get("model", model)}

        except Exception:
            _record_failure("atlas_chat")
            logger.exception("Atlas Cloud chat call failed")
            return {"content": "[Ошибка при вызове AI. Попробуйте позже.]", "tokens": 0}

    # ── Audio Transcription (Whisper) ─────────────────────────────────────

    async def transcribe(
        self,
        audio_data: bytes,
        filename: str = "audio.webm",
        model: str = DEFAULT_WHISPER_MODEL,
        language: str = "ru",
    ) -> dict[str, Any]:
        """Transcribe audio via Atlas Cloud's Whisper-compatible endpoint."""
        if not self.api_key:
            return {"text": "", "error": "API key not configured"}

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{self.base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files={"file": (filename, audio_data, "audio/webm")},
                    data={
                        "model": model,
                        "response_format": "verbose_json",
                        "language": language,
                    },
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            logger.exception("Atlas Cloud transcription failed")
            return {"text": "", "error": "Transcription failed"}

    # ── Text-to-Speech ────────────────────────────────────────────────────

    async def text_to_speech(
        self,
        text: str,
        model: str = DEFAULT_TTS_MODEL,
        voice: str = "alloy",
    ) -> bytes | None:
        """Generate speech audio from text."""
        if not self.api_key:
            return None

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.base_url}/audio/speech",
                    headers=self._auth_headers,
                    json={
                        "model": model,
                        "input": text,
                        "voice": voice,
                    },
                )
                resp.raise_for_status()
                return resp.content
        except Exception:
            logger.exception("Atlas Cloud TTS failed")
            return None

    # ── Image Generation ──────────────────────────────────────────────────

    async def generate_image(
        self,
        prompt: str,
        model: str = DEFAULT_IMAGE_MODEL,
        size: str = "1024x1024",
        n: int = 1,
    ) -> dict[str, Any]:
        """Generate image from text prompt."""
        if not self.api_key:
            return {"error": "API key not configured"}

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{self.base_url}/images/generations",
                    headers=self._auth_headers,
                    json={
                        "model": model,
                        "prompt": prompt,
                        "size": size,
                        "n": n,
                    },
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            logger.exception("Atlas Cloud image generation failed")
            return {"error": "Image generation failed"}

    # ── Video Generation ──────────────────────────────────────────────────

    async def generate_video(
        self,
        prompt: str | None = None,
        image_url: str | None = None,
        model: str = DEFAULT_VIDEO_MODEL,
    ) -> dict[str, Any]:
        """Generate video from text or image."""
        if not self.api_key:
            return {"error": "API key not configured"}

        payload: dict[str, Any] = {"model": model}
        if prompt:
            payload["prompt"] = prompt
        if image_url:
            payload["image"] = image_url

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{self.base_url}/model/generateVideo",
                    headers=self._auth_headers,
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            logger.exception("Atlas Cloud video generation failed")
            return {"error": "Video generation failed"}

    async def get_video_status(self, task_id: str) -> dict[str, Any]:
        """Check video generation task status."""
        if not self.api_key:
            return {"error": "API key not configured"}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{self.base_url}/model/generateVideo/{task_id}",
                    headers=self._auth_headers,
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            logger.exception("Atlas Cloud video status check failed")
            return {"error": "Status check failed"}

    async def wait_for_video(self, task_id: str, timeout: int = 120) -> str | None:
        """Poll until video is ready, return URL."""
        for _ in range(timeout // 3):
            status = await self.get_video_status(task_id)
            if status.get("status") == "done":
                return status.get("result_url") or status.get("url")
            if status.get("status") in ("error", "failed"):
                logger.error("Video generation error: %s", status)
                return None
            await asyncio.sleep(3)
        return None


# Singleton — reusable across the application
_client: AtlasCloudClient | None = None


def get_atlas_client() -> AtlasCloudClient:
    """Get or create the global Atlas Cloud client instance."""
    global _client
    if _client is None:
        _client = AtlasCloudClient()
    return _client
