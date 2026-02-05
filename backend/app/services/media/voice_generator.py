"""Voice report generator — ElevenLabs TTS integration.

Converts report markdown into a concise speech script and generates audio via ElevenLabs API.
Uploads the resulting .ogg file to S3.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.s3_storage import S3Storage

logger = logging.getLogger(__name__)

settings = get_settings()

ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"

# Maximum characters per TTS request (ElevenLabs limit is ~5000)
MAX_SCRIPT_CHARS = 4500


class VoiceGenerator:
    """Generate voice audio from report content using ElevenLabs TTS."""

    def __init__(self) -> None:
        self.s3 = S3Storage()
        self.voice_id = settings.elevenlabs_voice_id or "21m00Tcm4TlvDq8ikWAM"  # Rachel default

    async def generate_voice_report(
        self,
        report_content: dict[str, Any],
        report_markdown: str | None = None,
        title: str = "",
    ) -> dict[str, str]:
        """Generate a voice report from report data.

        Flow:
        1. Build speech script from report data
        2. Call ElevenLabs TTS API
        3. Upload .ogg to S3
        4. Return S3 key and presigned URL

        Returns:
            {"s3_key": "...", "url": "...", "duration_estimate": "..."}
        """
        # Build speech script
        script = self._build_speech_script(report_content, report_markdown, title)
        logger.info("Speech script: %d chars", len(script))

        # Generate audio via ElevenLabs
        audio_bytes = await self._call_elevenlabs_tts(script)

        # Upload to S3
        s3_key = S3Storage.generate_key("reports/voice", "ogg")
        await self.s3.ensure_bucket()
        await self.s3.upload_bytes(audio_bytes, s3_key, content_type="audio/ogg")

        # Generate presigned URL
        url = await self.s3.get_presigned_url(s3_key, expires_in=86400)  # 24h

        # Rough duration estimate (~150 words per minute, ~5 chars per word)
        word_count = len(script.split())
        duration_min = round(word_count / 150, 1)

        return {
            "s3_key": s3_key,
            "url": url,
            "duration_estimate": f"~{duration_min} мин",
            "script_length": len(script),
        }

    async def _call_elevenlabs_tts(self, text: str) -> bytes:
        """Call ElevenLabs text-to-speech API."""
        url = f"{ELEVENLABS_API_BASE}/text-to-speech/{self.voice_id}"
        headers = {
            "xi-api-key": settings.elevenlabs_api_key,
            "Content-Type": "application/json",
            "Accept": "audio/ogg",
        }
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.3,
                "use_speaker_boost": True,
            },
            "output_format": "ogg_opus",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            audio_data = resp.content

        logger.info("ElevenLabs TTS: received %d bytes", len(audio_data))
        return audio_data

    def _build_speech_script(
        self,
        report_content: dict[str, Any],
        report_markdown: str | None,
        title: str,
    ) -> str:
        """Convert report data into a natural speech script.

        Keeps it concise — no tables, markdown, or special formatting.
        """
        parts: list[str] = []

        # Intro
        period_days = report_content.get("period_days", 7)
        competitors_count = report_content.get("competitors_analyzed", 0)
        total_posts = report_content.get("total_posts", 0)

        parts.append(
            f"Привет! Это ваш еженедельный дайджест конкурентной разведки. "
            f"За последние {period_days} дней мы проанализировали "
            f"{competitors_count} конкурентов и {total_posts} публикаций."
        )

        # Key stats
        stats = report_content.get("stats", {})
        if stats:
            top_by_posts = max(stats.values(), key=lambda s: s.get("post_count", 0))
            top_by_likes = max(stats.values(), key=lambda s: s.get("total_likes", 0))

            parts.append(
                f"Самый активный конкурент — {top_by_posts['name']} "
                f"с {top_by_posts.get('post_count', 0)} публикациями. "
                f"Больше всего лайков набрал {top_by_likes['name']} — "
                f"{top_by_likes.get('total_likes', 0)} за период."
            )

        # AI insights (extract key points from analysis)
        ai_analysis = report_content.get("ai_analysis", "")
        if ai_analysis:
            clean = self._clean_for_speech(ai_analysis)
            # Take first ~2000 chars of analysis
            if len(clean) > 2000:
                # Cut at sentence boundary
                cut = clean[:2000]
                last_period = cut.rfind(".")
                if last_period > 1500:
                    clean = cut[:last_period + 1]
                else:
                    clean = cut
            parts.append("Вот ключевые выводы нашего AI-анализа.")
            parts.append(clean)

        # Outro
        parts.append(
            "Это был ваш дайджест. Для подробностей откройте полный отчёт в приложении. "
            "До новых встреч!"
        )

        script = " ".join(parts)

        # Enforce max length
        if len(script) > MAX_SCRIPT_CHARS:
            script = script[:MAX_SCRIPT_CHARS - 3]
            last_period = script.rfind(".")
            if last_period > MAX_SCRIPT_CHARS * 0.7:
                script = script[:last_period + 1]
            else:
                script += "..."

        return script

    @staticmethod
    def _clean_for_speech(text: str) -> str:
        """Remove markdown formatting and make text speech-friendly."""
        # Remove markdown headers
        text = re.sub(r"#{1,6}\s*", "", text)
        # Remove bold/italic markers
        text = re.sub(r"\*{1,2}(.*?)\*{1,2}", r"\1", text)
        text = re.sub(r"_{1,2}(.*?)_{1,2}", r"\1", text)
        # Remove bullet points
        text = re.sub(r"^[\s]*[-*•]\s*", "", text, flags=re.MULTILINE)
        # Remove code blocks
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        # Remove URLs
        text = re.sub(r"https?://\S+", "", text)
        # Remove table formatting
        text = re.sub(r"\|.*?\|", "", text)
        text = re.sub(r"-{3,}", "", text)
        # Clean up whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()
