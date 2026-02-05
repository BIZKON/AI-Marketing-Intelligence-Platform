"""YouTube parser using YouTube Data API v3."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

from app.services.parsers.base import BaseParser, ParsedPost

logger = logging.getLogger(__name__)

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeParser(BaseParser):
    """Parser for YouTube channels using the Data API v3."""

    @property
    def platform_name(self) -> str:
        return "youtube"

    async def fetch_posts(
        self,
        tracking_config: dict,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[ParsedPost]:
        channel_id = tracking_config.get("channel_id", "")
        if not channel_id:
            # Try to resolve from handle/username
            handle = tracking_config.get("handle", "")
            if handle:
                channel_id = await self._resolve_channel_id(handle)
            if not channel_id:
                logger.warning("No channel_id or handle in YouTube tracking config")
                return []

        return await self._fetch_channel_videos(channel_id, since, limit)

    async def _resolve_channel_id(self, handle: str) -> str | None:
        """Resolve a YouTube handle (@name) or username to channel ID."""
        if not YOUTUBE_API_KEY:
            return None

        handle = handle.lstrip("@")
        params = {
            "part": "id",
            "forHandle": handle,
            "key": YOUTUBE_API_KEY,
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{YOUTUBE_API_BASE}/channels", params=params)
                resp.raise_for_status()
                data = resp.json()
                items = data.get("items", [])
                if items:
                    return items[0]["id"]
        except Exception:
            logger.exception("Failed to resolve YouTube handle: %s", handle)
        return None

    async def _fetch_channel_videos(
        self, channel_id: str, since: datetime | None, limit: int
    ) -> list[ParsedPost]:
        if not YOUTUBE_API_KEY:
            logger.warning("YOUTUBE_API_KEY not set, skipping YouTube parsing")
            return []

        posts = []
        params: dict = {
            "part": "snippet",
            "channelId": channel_id,
            "maxResults": min(limit, 50),
            "order": "date",
            "type": "video",
            "key": YOUTUBE_API_KEY,
        }

        if since:
            params["publishedAfter"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # 1. Search for recent videos
                resp = await client.get(f"{YOUTUBE_API_BASE}/search", params=params)
                resp.raise_for_status()
                search_data = resp.json()
                items = search_data.get("items", [])

                if not items:
                    return []

                # 2. Get detailed video stats
                video_ids = [item["id"]["videoId"] for item in items if item["id"].get("videoId")]
                stats_resp = await client.get(
                    f"{YOUTUBE_API_BASE}/videos",
                    params={
                        "part": "statistics,snippet,contentDetails",
                        "id": ",".join(video_ids),
                        "key": YOUTUBE_API_KEY,
                    },
                )
                stats_resp.raise_for_status()
                stats_data = stats_resp.json()

                for video in stats_data.get("items", []):
                    snippet = video.get("snippet", {})
                    stats = video.get("statistics", {})
                    video_id = video["id"]

                    published_at = None
                    if snippet.get("publishedAt"):
                        try:
                            published_at = datetime.fromisoformat(
                                snippet["publishedAt"].replace("Z", "+00:00")
                            )
                        except ValueError:
                            pass

                    # Thumbnail
                    thumbnails = snippet.get("thumbnails", {})
                    thumb_url = (
                        thumbnails.get("high", {}).get("url")
                        or thumbnails.get("medium", {}).get("url")
                        or thumbnails.get("default", {}).get("url")
                        or ""
                    )

                    posts.append(ParsedPost(
                        external_id=f"yt_{video_id}",
                        platform="youtube",
                        title=snippet.get("title", ""),
                        text_content=snippet.get("description", ""),
                        url=f"https://www.youtube.com/watch?v={video_id}",
                        media_urls=[thumb_url] if thumb_url else [],
                        views=int(stats.get("viewCount", 0)),
                        likes=int(stats.get("likeCount", 0)),
                        comments=int(stats.get("commentCount", 0)),
                        published_at=published_at,
                        raw_data={
                            "channel_id": channel_id,
                            "video_id": video_id,
                            "duration": video.get("contentDetails", {}).get("duration"),
                            "tags": snippet.get("tags", []),
                            "category_id": snippet.get("categoryId"),
                        },
                    ))

            logger.info("YouTube: fetched %d videos from channel %s", len(posts), channel_id)

        except Exception:
            logger.exception("Failed to fetch YouTube videos for channel %s", channel_id)

        return posts
