"""VK (VKontakte) parser using VK API."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

from app.services.parsers.base import BaseParser, ParsedPost

logger = logging.getLogger(__name__)

VK_ACCESS_TOKEN = os.getenv("VK_ACCESS_TOKEN", "")
VK_API_VERSION = "5.199"
VK_API_BASE = "https://api.vk.com/method"


class VKParser(BaseParser):
    """Parser for VK communities using VK API."""

    @property
    def platform_name(self) -> str:
        return "vk"

    async def fetch_posts(
        self,
        tracking_config: dict,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[ParsedPost]:
        # Accept community ID (negative) or screen name
        owner_id = tracking_config.get("owner_id")
        domain = tracking_config.get("domain", "")

        if not owner_id and not domain:
            logger.warning("No owner_id or domain in VK tracking config")
            return []

        if not VK_ACCESS_TOKEN:
            logger.warning("VK_ACCESS_TOKEN not set, skipping VK parsing")
            return []

        return await self._fetch_wall_posts(owner_id, domain, since, limit)

    async def _fetch_wall_posts(
        self,
        owner_id: int | None,
        domain: str,
        since: datetime | None,
        limit: int,
    ) -> list[ParsedPost]:
        posts = []
        params: dict = {
            "access_token": VK_ACCESS_TOKEN,
            "v": VK_API_VERSION,
            "count": min(limit, 100),
            "filter": "owner",
        }

        if owner_id:
            params["owner_id"] = owner_id
        elif domain:
            params["domain"] = domain

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{VK_API_BASE}/wall.get", params=params)
                resp.raise_for_status()
                data = resp.json()

            if "error" in data:
                logger.error("VK API error: %s", data["error"])
                return []

            items = data.get("response", {}).get("items", [])

            for item in items:
                post_date = datetime.fromtimestamp(item.get("date", 0), tz=timezone.utc)

                if since and post_date < since:
                    continue

                post_id = item.get("id", 0)
                post_owner_id = item.get("owner_id", owner_id or 0)
                text = item.get("text", "")

                # Extract media
                media_urls = []
                for attachment in item.get("attachments", []):
                    if attachment["type"] == "photo":
                        sizes = attachment.get("photo", {}).get("sizes", [])
                        if sizes:
                            # Get the largest image
                            largest = max(sizes, key=lambda s: s.get("width", 0))
                            media_urls.append(largest.get("url", ""))
                    elif attachment["type"] == "video":
                        video = attachment.get("video", {})
                        thumb = video.get("image", [{}])[-1].get("url", "") if video.get("image") else ""
                        if thumb:
                            media_urls.append(thumb)

                posts.append(ParsedPost(
                    external_id=f"vk_{post_owner_id}_{post_id}",
                    platform="vk",
                    text_content=text,
                    url=f"https://vk.com/wall{post_owner_id}_{post_id}",
                    media_urls=media_urls,
                    views=item.get("views", {}).get("count", 0),
                    likes=item.get("likes", {}).get("count", 0),
                    comments=item.get("comments", {}).get("count", 0),
                    shares=item.get("reposts", {}).get("count", 0),
                    published_at=post_date,
                    raw_data={
                        "owner_id": post_owner_id,
                        "post_id": post_id,
                        "post_type": item.get("post_type"),
                        "marked_as_ads": item.get("marked_as_ads", 0),
                    },
                ))

            logger.info("VK: fetched %d posts from %s", len(posts), domain or owner_id)

        except Exception:
            logger.exception("Failed to fetch VK posts for %s", domain or owner_id)

        return posts
