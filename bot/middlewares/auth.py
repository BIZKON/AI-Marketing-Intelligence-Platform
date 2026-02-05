"""Auth middleware: authenticates Telegram users against the backend API.

On every incoming message, this middleware:
1. Calls the backend /auth/telegram endpoint
2. Stores the user data and API token in handler data
3. Creates the user if they don't exist yet
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message

from bot.services.api_client import APIClient

logger = logging.getLogger(__name__)

# In-memory cache: telegram_id -> (token, user_dict)
_auth_cache: dict[int, tuple[str, dict]] = {}


class AuthMiddleware(BaseMiddleware):
    """Authenticates user via backend API and injects user data + api client into handler context."""

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        if not event.from_user:
            return

        telegram_id = event.from_user.id
        telegram_username = event.from_user.username
        full_name = event.from_user.full_name

        # Try cache first
        cached = _auth_cache.get(telegram_id)
        if cached:
            token, user_data = cached
            api = APIClient(token=token)
        else:
            api = APIClient()
            try:
                auth_response = await api.auth_telegram(
                    telegram_id=telegram_id,
                    username=telegram_username,
                    full_name=full_name,
                )
                user_data = auth_response["user"]
                _auth_cache[telegram_id] = (auth_response["access_token"], user_data)
            except Exception:
                logger.exception("Failed to authenticate user tg_id=%s", telegram_id)
                await event.answer("Произошла ошибка аутентификации. Попробуйте позже.")
                return

        data["api"] = api
        data["user_data"] = user_data
        data["telegram_id"] = telegram_id
        data["telegram_username"] = telegram_username

        return await handler(event, data)


def invalidate_cache(telegram_id: int) -> None:
    """Remove user from auth cache (e.g., after profile update)."""
    _auth_cache.pop(telegram_id, None)
