from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message


class SubscriptionMiddleware(BaseMiddleware):
    """Checks user's subscription plan before processing commands."""

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        # TODO: fetch user subscription from DB
        # Check if the command requires a specific plan level
        # Block execution and send upsell message if plan is insufficient
        data["user_plan"] = None  # Will be set after DB lookup

        return await handler(event, data)
