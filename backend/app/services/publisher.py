"""Publishing service — publish content to Telegram and VK platforms.

Handles the actual API calls to push approved content to target channels.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.models.content_task import ContentTask

logger = logging.getLogger(__name__)

_settings = get_settings()
TELEGRAM_BOT_TOKEN = _settings.telegram_bot_token
TELEGRAM_API_BASE = "https://api.telegram.org/bot"

VK_ACCESS_TOKEN = _settings.vk_access_token
VK_API_VERSION = "5.199"
VK_API_BASE = "https://api.vk.com/method"


class PublisherService:
    """Publish content tasks to external platforms."""

    async def publish(
        self,
        task: ContentTask,
        target_channel: str | None = None,
    ) -> dict[str, Any]:
        """Route publishing to the correct platform handler."""
        platform = task.platform
        text = task.body or ""

        if not text.strip():
            return {"status": "error", "message": "Task has no content to publish"}

        if platform == "telegram":
            return await self._publish_telegram(text, task, target_channel)
        elif platform == "vk":
            return await self._publish_vk(text, task, target_channel)
        else:
            return {
                "status": "unsupported",
                "message": f"Auto-publishing for {platform} is not yet supported. "
                           "Content is ready for manual publishing.",
            }

    # ── Telegram ─────────────────────────────────────────────────────────────

    async def _publish_telegram(
        self,
        text: str,
        task: ContentTask,
        target_channel: str | None,
    ) -> dict[str, Any]:
        """Publish a post to a Telegram channel via Bot API."""
        if not TELEGRAM_BOT_TOKEN:
            return {"status": "error", "message": "TELEGRAM_BOT_TOKEN not configured"}

        metadata = task.metadata_json or {}
        chat_id = target_channel or metadata.get("telegram_channel")
        if not chat_id:
            return {
                "status": "error",
                "message": "No target Telegram channel specified. "
                           "Set target_channel or add telegram_channel to task metadata.",
            }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": False,
                    },
                )
                data = resp.json()

            if not data.get("ok"):
                error_desc = data.get("description", "Unknown error")
                logger.error("Telegram publish failed: %s", error_desc)
                return {"status": "error", "message": f"Telegram: {error_desc}"}

            msg = data.get("result", {})
            message_id = msg.get("message_id", "")
            chat = msg.get("chat", {})
            chat_username = chat.get("username", "")

            url = ""
            if chat_username and message_id:
                url = f"https://t.me/{chat_username}/{message_id}"

            logger.info("Published to Telegram: %s/%s", chat_id, message_id)
            return {
                "status": "ok",
                "result": "published",
                "url": url,
                "message": "Successfully published to Telegram",
                "message_id": message_id,
            }

        except Exception:
            logger.exception("Failed to publish to Telegram")
            return {"status": "error", "message": "Telegram API request failed"}

    # ── VK ───────────────────────────────────────────────────────────────────

    async def _publish_vk(
        self,
        text: str,
        task: ContentTask,
        target_channel: str | None,
    ) -> dict[str, Any]:
        """Publish a post to a VK community wall."""
        if not VK_ACCESS_TOKEN:
            return {"status": "error", "message": "VK_ACCESS_TOKEN not configured"}

        metadata = task.metadata_json or {}
        # Owner ID should be negative for communities
        owner_id = target_channel or metadata.get("vk_owner_id")
        if not owner_id:
            return {
                "status": "error",
                "message": "No target VK community specified. "
                           "Set target_channel or add vk_owner_id to task metadata.",
            }

        try:
            params = {
                "access_token": VK_ACCESS_TOKEN,
                "v": VK_API_VERSION,
                "owner_id": owner_id,
                "message": text,
                "from_group": 1,
            }

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{VK_API_BASE}/wall.post",
                    data=params,
                )
                data = resp.json()

            if "error" in data:
                error_msg = data["error"].get("error_msg", "Unknown error")
                logger.error("VK publish failed: %s", error_msg)
                return {"status": "error", "message": f"VK: {error_msg}"}

            post_id = data.get("response", {}).get("post_id", "")
            url = f"https://vk.com/wall{owner_id}_{post_id}" if post_id else ""

            logger.info("Published to VK: %s_%s", owner_id, post_id)
            return {
                "status": "ok",
                "result": "published",
                "url": url,
                "message": "Successfully published to VK",
                "post_id": post_id,
            }

        except Exception:
            logger.exception("Failed to publish to VK")
            return {"status": "error", "message": "VK API request failed"}
