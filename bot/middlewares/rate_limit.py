"""Sliding window rate limiting middleware for Telegram bot.

Uses in-memory store with periodic cleanup to prevent unbounded growth (#064, #065).
Applied to both messages and callback queries (#066).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, Union

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

logger = logging.getLogger(__name__)

RATE_LIMIT_SECONDS = 1.0
RATE_LIMIT_BURST = 5

# In-memory sliding window: telegram_id -> list of timestamps
_rate_limit_store: dict[int, list[float]] = {}
_last_cleanup = 0.0
_CLEANUP_INTERVAL = 60.0  # run cleanup every 60s (#065)


def _cleanup_store(now: float) -> None:
    """Remove stale users from the store to prevent memory leak (#065)."""
    global _last_cleanup
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    window = RATE_LIMIT_SECONDS * RATE_LIMIT_BURST
    stale_keys = [
        uid for uid, ts in _rate_limit_store.items()
        if not ts or (now - ts[-1]) > window
    ]
    for key in stale_keys:
        del _rate_limit_store[key]


class RateLimitMiddleware(BaseMiddleware):
    """Sliding window rate limiting per user.

    Works for both Message and CallbackQuery events (#066).
    """

    async def __call__(
        self,
        handler: Callable[[Union[Message, CallbackQuery], dict[str, Any]], Awaitable[Any]],
        event: Union[Message, CallbackQuery],
        data: dict[str, Any],
    ) -> Any:
        if not event.from_user:
            return

        user_id = event.from_user.id
        now = time.monotonic()

        # Periodic cleanup (#065)
        _cleanup_store(now)

        timestamps = _rate_limit_store.get(user_id, [])
        window = RATE_LIMIT_SECONDS * RATE_LIMIT_BURST
        timestamps = [t for t in timestamps if now - t < window]

        if len(timestamps) >= RATE_LIMIT_BURST:
            logger.debug("Rate limited user %s", user_id)
            if isinstance(event, Message):
                await event.answer("\u0421\u043b\u0438\u0448\u043a\u043e\u043c \u043c\u043d\u043e\u0433\u043e \u0437\u0430\u043f\u0440\u043e\u0441\u043e\u0432. \u041f\u043e\u0434\u043e\u0436\u0434\u0438\u0442\u0435 \u043d\u0435\u043c\u043d\u043e\u0433\u043e.")
            elif isinstance(event, CallbackQuery):
                await event.answer("\u0421\u043b\u0438\u0448\u043a\u043e\u043c \u0447\u0430\u0441\u0442\u043e. \u041f\u043e\u0434\u043e\u0436\u0434\u0438\u0442\u0435.", show_alert=True)
            return

        timestamps.append(now)
        _rate_limit_store[user_id] = timestamps

        return await handler(event, data)
