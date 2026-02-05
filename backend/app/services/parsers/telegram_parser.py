"""Telegram channel parser using Telethon for reading public channel messages."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from app.services.parsers.base import BaseParser, ParsedPost

logger = logging.getLogger(__name__)

# Telethon API credentials (optional — can also use web scraping fallback)
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")


class TelegramParser(BaseParser):
    """Parser for public Telegram channels.

    Uses Telethon when API credentials are available,
    falls back to web scraping via t.me/s/ preview.
    """

    @property
    def platform_name(self) -> str:
        return "telegram"

    async def fetch_posts(
        self,
        tracking_config: dict,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[ParsedPost]:
        channel = tracking_config.get("channel", "")
        if not channel:
            logger.warning("No channel specified in tracking config")
            return []

        # Strip @ prefix for consistency
        channel = channel.lstrip("@")

        if TELEGRAM_API_ID and TELEGRAM_API_HASH:
            return await self._fetch_via_telethon(channel, since, limit)
        return await self._fetch_via_web(channel, since, limit)

    async def _fetch_via_telethon(
        self, channel: str, since: datetime | None, limit: int
    ) -> list[ParsedPost]:
        """Fetch using Telethon (full API access, better quality data)."""
        try:
            from telethon import TelegramClient
            from telethon.tl.functions.messages import GetHistoryRequest

            client = TelegramClient("parser_session", int(TELEGRAM_API_ID), TELEGRAM_API_HASH)
            await client.start()

            entity = await client.get_entity(channel)
            messages = await client(GetHistoryRequest(
                peer=entity,
                limit=limit,
                offset_date=since,
                offset_id=0,
                max_id=0,
                min_id=0,
                add_offset=0,
                hash=0,
            ))

            posts = []
            for msg in messages.messages:
                if not msg.message and not getattr(msg, "media", None):
                    continue

                post = ParsedPost(
                    external_id=f"tg_{channel}_{msg.id}",
                    platform="telegram",
                    text_content=msg.message or "",
                    url=f"https://t.me/{channel}/{msg.id}",
                    views=getattr(msg, "views", 0) or 0,
                    shares=getattr(msg, "forwards", 0) or 0,
                    published_at=msg.date.replace(tzinfo=timezone.utc) if msg.date else None,
                    raw_data={"message_id": msg.id, "channel": channel},
                )

                # Extract reactions as likes
                if hasattr(msg, "reactions") and msg.reactions:
                    total_reactions = sum(
                        r.count for r in msg.reactions.results
                    ) if msg.reactions.results else 0
                    post.likes = total_reactions

                posts.append(post)

            await client.disconnect()
            logger.info("Telethon: fetched %d posts from @%s", len(posts), channel)
            return posts

        except ImportError:
            logger.warning("Telethon not installed, falling back to web scraping")
            return await self._fetch_via_web(channel, since, limit)
        except Exception:
            logger.exception("Telethon error fetching @%s", channel)
            return await self._fetch_via_web(channel, since, limit)

    async def _fetch_via_web(
        self, channel: str, since: datetime | None, limit: int
    ) -> list[ParsedPost]:
        """Fallback: scrape t.me/s/ public preview page."""
        import httpx
        from bs4 import BeautifulSoup

        url = f"https://t.me/s/{channel}"
        posts = []

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            message_divs = soup.select(".tgme_widget_message_wrap")

            for div in message_divs[-limit:]:
                msg_div = div.select_one(".tgme_widget_message")
                if not msg_div:
                    continue

                # Extract message ID from data-post attribute
                data_post = msg_div.get("data-post", "")
                msg_id = data_post.split("/")[-1] if "/" in data_post else ""

                # Extract text
                text_div = msg_div.select_one(".tgme_widget_message_text")
                text = text_div.get_text(separator="\n", strip=True) if text_div else ""

                # Extract views
                views_span = msg_div.select_one(".tgme_widget_message_views")
                views_text = views_span.get_text(strip=True) if views_span else "0"
                views = self._parse_count(views_text)

                # Extract datetime
                time_el = msg_div.select_one("time[datetime]")
                published_at = None
                if time_el and time_el.get("datetime"):
                    try:
                        published_at = datetime.fromisoformat(time_el["datetime"])
                    except ValueError:
                        pass

                if since and published_at and published_at < since:
                    continue

                if not text and not msg_id:
                    continue

                # Extract media
                media_urls = []
                for img in msg_div.select(".tgme_widget_message_photo_wrap"):
                    style = img.get("style", "")
                    if "background-image" in style:
                        url_start = style.find("url('") + 5
                        url_end = style.find("')", url_start)
                        if url_start > 4 and url_end > url_start:
                            media_urls.append(style[url_start:url_end])

                posts.append(ParsedPost(
                    external_id=f"tg_{channel}_{msg_id}",
                    platform="telegram",
                    text_content=text,
                    url=f"https://t.me/{channel}/{msg_id}",
                    media_urls=media_urls,
                    views=views,
                    published_at=published_at,
                    raw_data={"channel": channel, "message_id": msg_id},
                ))

            logger.info("Web scraping: fetched %d posts from @%s", len(posts), channel)

        except Exception:
            logger.exception("Failed to scrape @%s", channel)

        return posts

    @staticmethod
    def _parse_count(text: str) -> int:
        """Parse abbreviated counts like '1.2K', '5M'."""
        text = text.strip().upper().replace(" ", "")
        if not text:
            return 0
        try:
            if text.endswith("K"):
                return int(float(text[:-1]) * 1_000)
            if text.endswith("M"):
                return int(float(text[:-1]) * 1_000_000)
            return int(text)
        except (ValueError, TypeError):
            return 0
