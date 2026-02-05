import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message

# In-memory rate limit store; replace with Redis in production
_rate_limit_store: dict[int, float] = {}
RATE_LIMIT_SECONDS = 1.0


class RateLimitMiddleware(BaseMiddleware):
    """Simple per-user rate limiting to prevent abuse."""

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
        last_request = _rate_limit_store.get(user_id, 0)

        if now - last_request < RATE_LIMIT_SECONDS:
            return  # silently drop

        _rate_limit_store[user_id] = now
        return await handler(event, data)
