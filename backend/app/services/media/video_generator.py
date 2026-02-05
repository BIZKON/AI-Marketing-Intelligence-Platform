"""Video report generator — HeyGen avatar video with chart overlays.

Flow:
1. Extract key insights and build speech script
2. Pre-render chart images from report data
3. Submit video generation job to HeyGen API
4. Poll for completion
5. Download result and upload to S3
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.media.chart_renderer import (
    render_engagement_bar_chart,
    render_posts_comparison_chart,
)
from app.services.media.voice_generator import VoiceGenerator
from app.services.s3_storage import S3Storage

logger = logging.getLogger(__name__)

settings = get_settings()

HEYGEN_API_BASE = "https://api.heygen.com/v2"
MAX_POLL_ATTEMPTS = 60  # 60 * 10s = 10 minutes max wait
POLL_INTERVAL = 10  # seconds


class VideoGenerator:
    """Generate video reports with HeyGen AI avatar and chart overlays."""

    def __init__(self) -> None:
        self.s3 = S3Storage()
        self.voice_gen = VoiceGenerator()

    async def generate_video_report(
        self,
        report_content: dict[str, Any],
        report_markdown: str | None = None,
        title: str = "",
    ) -> dict[str, str]:
        """Generate a full video report.

        Returns:
            {"s3_key": "...", "url": "...", "heygen_video_id": "..."}
        """
        # Build speech script (reuse voice generator logic)
        script = self.voice_gen._build_speech_script(report_content, report_markdown, title)

        # Pre-render chart images for slides
        chart_images = self._render_chart_slides(report_content)

        # Upload chart images to S3 for HeyGen to access
        chart_urls = []
        await self.s3.ensure_bucket()
        for i, chart_png in enumerate(chart_images):
            key = S3Storage.generate_key("reports/video/charts", "png")
            await self.s3.upload_bytes(chart_png, key, content_type="image/png")
            url = await self.s3.get_presigned_url(key, expires_in=3600)
            chart_urls.append(url)

        # Submit HeyGen video generation
        video_id = await self._create_heygen_video(script, chart_urls, title)

        # Poll for completion
        video_url = await self._poll_video_status(video_id)

        # Download video and re-upload to our S3
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(video_url)
            resp.raise_for_status()
            video_bytes = resp.content

        s3_key = S3Storage.generate_key("reports/video", "mp4")
        await self.s3.upload_bytes(video_bytes, s3_key, content_type="video/mp4")
        presigned_url = await self.s3.get_presigned_url(s3_key, expires_in=86400)

        logger.info("Video report generated: %s (%d bytes)", s3_key, len(video_bytes))

        return {
            "s3_key": s3_key,
            "url": presigned_url,
            "heygen_video_id": video_id,
            "video_size": len(video_bytes),
        }

    async def _create_heygen_video(
        self,
        script: str,
        chart_urls: list[str],
        title: str,
    ) -> str:
        """Submit a video generation request to HeyGen API.

        Creates a talking avatar video with optional background slides.
        Returns the video_id for polling.
        """
        headers = {
            "X-Api-Key": settings.heygen_api_key,
            "Content-Type": "application/json",
        }

        # Build video scenes
        scenes = []

        # Intro scene with avatar
        intro_length = min(len(script), 500)
        intro_text = script[:intro_length]
        last_period = intro_text.rfind(".")
        if last_period > 300:
            intro_text = intro_text[:last_period + 1]

        scenes.append({
            "script": {
                "type": "text",
                "input": intro_text,
            },
            "avatar": {
                "avatar_id": "default",
                "scale": 1.0,
                "position": {"x": 0.5, "y": 0.5},
            },
            "background": {
                "type": "color",
                "value": "#1e1b4b",
            },
        })

        # Chart scenes — avatar with chart background
        remaining_script = script[len(intro_text):].strip()
        chunk_size = max(200, len(remaining_script) // max(len(chart_urls), 1))

        for i, chart_url in enumerate(chart_urls):
            start = i * chunk_size
            end = min((i + 1) * chunk_size, len(remaining_script))
            chunk = remaining_script[start:end]

            if not chunk:
                break

            # End chunk at sentence boundary
            if end < len(remaining_script):
                last_period = chunk.rfind(".")
                if last_period > len(chunk) * 0.5:
                    chunk = chunk[:last_period + 1]

            scenes.append({
                "script": {
                    "type": "text",
                    "input": chunk,
                },
                "avatar": {
                    "avatar_id": "default",
                    "scale": 0.4,
                    "position": {"x": 0.15, "y": 0.75},
                },
                "background": {
                    "type": "image",
                    "url": chart_url,
                    "fit": "contain",
                },
            })

        # Outro
        outro_start = min(len(remaining_script), len(chart_urls) * chunk_size)
        outro_text = remaining_script[outro_start:].strip()
        if outro_text:
            scenes.append({
                "script": {
                    "type": "text",
                    "input": outro_text,
                },
                "avatar": {
                    "avatar_id": "default",
                    "scale": 1.0,
                    "position": {"x": 0.5, "y": 0.5},
                },
                "background": {
                    "type": "color",
                    "value": "#1e1b4b",
                },
            })

        payload = {
            "title": title or "AI Marketing Report",
            "video_inputs": scenes,
            "dimension": {"width": 1920, "height": 1080},
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{HEYGEN_API_BASE}/video/generate",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        video_id = data.get("data", {}).get("video_id", "")
        if not video_id:
            raise ValueError(f"HeyGen did not return video_id: {data}")

        logger.info("HeyGen video submitted: %s", video_id)
        return video_id

    async def _poll_video_status(self, video_id: str) -> str:
        """Poll HeyGen API until video is ready, return download URL."""
        headers = {"X-Api-Key": settings.heygen_api_key}

        for attempt in range(MAX_POLL_ATTEMPTS):
            await asyncio.sleep(POLL_INTERVAL)

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{HEYGEN_API_BASE}/video_status.get",
                    params={"video_id": video_id},
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

            status = data.get("data", {}).get("status", "")
            logger.debug("HeyGen poll #%d: status=%s", attempt + 1, status)

            if status == "completed":
                video_url = data["data"].get("video_url", "")
                if video_url:
                    return video_url
                raise ValueError("HeyGen returned completed but no video_url")

            if status == "failed":
                error = data.get("data", {}).get("error", "Unknown error")
                raise RuntimeError(f"HeyGen video generation failed: {error}")

        raise TimeoutError(f"HeyGen video {video_id} did not complete within timeout")

    @staticmethod
    def _render_chart_slides(report_content: dict[str, Any]) -> list[bytes]:
        """Render chart images for video background slides."""
        stats = report_content.get("stats", {})
        charts: list[bytes] = []

        if not stats:
            return charts

        try:
            charts.append(render_engagement_bar_chart(stats))
        except Exception:
            logger.exception("Failed to render engagement chart for video")

        try:
            charts.append(render_posts_comparison_chart(stats))
        except Exception:
            logger.exception("Failed to render posts chart for video")

        return charts
