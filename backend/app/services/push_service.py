"""Push notification service — Web Push (VAPID) and Telegram push delivery."""

from __future__ import annotations

import json
import logging
import uuid

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.push_subscription import PushSubscription

logger = logging.getLogger(__name__)
settings = get_settings()


class PushService:
    """Delivers push notifications via Web Push (VAPID) and Telegram."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Web Push Subscriptions ────────────────────────────────────────────────

    async def subscribe(
        self, user_id: uuid.UUID, endpoint: str, p256dh_key: str, auth_key: str,
    ) -> PushSubscription:
        """Register a Web Push subscription for a user."""
        existing = await self.db.execute(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
        sub = existing.scalar_one_or_none()
        if sub:
            sub.user_id = user_id
            sub.p256dh_key = p256dh_key
            sub.auth_key = auth_key
        else:
            sub = PushSubscription(
                user_id=user_id,
                endpoint=endpoint,
                p256dh_key=p256dh_key,
                auth_key=auth_key,
            )
            self.db.add(sub)
        await self.db.flush()
        await self.db.refresh(sub)
        return sub

    async def unsubscribe(self, user_id: uuid.UUID, endpoint: str) -> bool:
        """Remove a Web Push subscription."""
        result = await self.db.execute(
            delete(PushSubscription).where(
                PushSubscription.user_id == user_id,
                PushSubscription.endpoint == endpoint,
            )
        )
        return result.rowcount > 0

    async def get_user_subscriptions(self, user_id: uuid.UUID) -> list[PushSubscription]:
        result = await self.db.execute(
            select(PushSubscription).where(PushSubscription.user_id == user_id)
        )
        return list(result.scalars().all())

    # ── Web Push Delivery ─────────────────────────────────────────────────────

    async def send_web_push(self, user_id: uuid.UUID, title: str, body: str, url: str | None = None) -> int:
        """Send Web Push notification to all user's subscriptions. Returns count of sent."""
        subscriptions = await self.get_user_subscriptions(user_id)
        if not subscriptions:
            return 0

        payload = json.dumps({
            "title": title,
            "body": body,
            "icon": "/icon-192.png",
            "badge": "/icon-192.png",
            "url": url or "/training/analytics",
        })

        sent = 0
        stale_endpoints: list[str] = []

        async with httpx.AsyncClient(timeout=10) as client:
            for sub in subscriptions:
                try:
                    # Simplified push — in production use pywebpush with VAPID
                    headers = {
                        "Content-Type": "application/json",
                        "TTL": "86400",
                    }
                    if settings.vapid_private_key:
                        headers["Authorization"] = f"vapid t={settings.vapid_private_key}"

                    resp = await client.post(
                        sub.endpoint,
                        content=payload,
                        headers=headers,
                    )
                    if resp.status_code in (201, 200):
                        sent += 1
                    elif resp.status_code in (404, 410):
                        stale_endpoints.append(sub.endpoint)
                except Exception:
                    logger.warning("Failed to push to endpoint %s", sub.endpoint[:50])

        # Clean up stale subscriptions
        if stale_endpoints:
            await self.db.execute(
                delete(PushSubscription).where(PushSubscription.endpoint.in_(stale_endpoints))
            )

        return sent

    # ── Telegram Push Delivery ────────────────────────────────────────────────

    async def send_telegram_push(self, telegram_id: int, text: str) -> bool:
        """Send push notification via Telegram bot."""
        if not settings.telegram_bot_token or not telegram_id:
            return False

        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": telegram_id,
            "text": text,
            "parse_mode": "HTML",
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                return resp.status_code == 200
        except Exception:
            logger.warning("Failed to send Telegram push to %s", telegram_id)
            return False

    # ── Combined Push (Web + Telegram) ────────────────────────────────────────

    async def notify_evaluation_complete(
        self,
        user_id: uuid.UUID,
        telegram_id: int | None,
        overall_score: int,
        session_id: uuid.UUID,
    ) -> dict[str, int | bool]:
        """Send push when training evaluation is complete — both Web and Telegram."""
        title = "Training Complete!"
        body = f"Your score: {overall_score}/100. View detailed feedback."
        url = f"/training/session/{session_id}"

        web_sent = await self.send_web_push(user_id, title, body, url)

        tg_sent = False
        if telegram_id:
            tg_text = (
                f"<b>Тренировка завершена!</b>\n\n"
                f"Ваш балл: <b>{overall_score}/100</b>\n"
                f"Подробный разбор доступен в приложении."
            )
            tg_sent = await self.send_telegram_push(telegram_id, tg_text)

        return {"web_push_sent": web_sent, "telegram_sent": tg_sent}
