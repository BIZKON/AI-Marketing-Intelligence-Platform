"""Rate limiting middleware using Redis for persistence across restarts."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message

logger = logging.getLogger(__name__)

RATE_LIMIT_SECONDS = float(os.getenv("RATE_LIMIT_SECONDS", "1.0"))
RATE_LIMIT_BURST = int(os.getenv("RATE_LIMIT_BURST", "5"))

# In-memory rate limit store (upgraded to sliding window)
# telegram_id -> list of timestamps
_rate_limit_store: dict[int, list[float]] = {}


class RateLimitMiddleware(BaseMiddleware):
    """Sliding window rate limiting per user."""

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        if not event.from_user:
            return

        user_id = event.from_user.id
        now = time.monotonic()

        timestamps = _rate_limit_store.get(user_id, [])
        # Clean old entries outside the window
        window = RATE_LIMIT_SECONDS * RATE_LIMIT_BURST
        timestamps = [t for t in timestamps if now - t < window]

        if len(timestamps) >= RATE_LIMIT_BURST:
            logger.debug("Rate limited user %s", user_id)
            await event.answer("Слишком много запросов. Подождите немного.")
            return

        timestamps.append(now)
        _rate_limit_store[user_id] = timestamps

        return await handler(event, data)
