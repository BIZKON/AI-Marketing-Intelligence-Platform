from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message


class AuthMiddleware(BaseMiddleware):
    """Ensures user exists in the database. Creates if not found."""

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        if not event.from_user:
            return

        telegram_id = event.from_user.id
        # TODO: look up or create user via API/DB
        # For now, pass telegram_id in data for handlers
        data["telegram_id"] = telegram_id
        data["telegram_username"] = event.from_user.username

        return await handler(event, data)
