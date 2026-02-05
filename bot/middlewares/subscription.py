"""Subscription middleware: fetches user's plan and injects it into handler context.

Also blocks commands that require a higher plan with an upsell message.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message

from bot.services.api_client import APIClient

logger = logging.getLogger(__name__)

# Commands that require specific plan levels
PLAN_REQUIREMENTS: dict[str, str] = {
    "/plan": "creator",
    "/status": "creator",
    "/approve": "creator",
    "/voice": "creator",
    "/video": "autopilot",
    "/queue": "autopilot",
}

PLAN_ORDER = {"monitor": 0, "creator": 1, "autopilot": 2, "enterprise": 3}

PLAN_NAMES = {
    "creator": "Creator ($499/мес)",
    "autopilot": "Autopilot ($999/мес)",
    "enterprise": "Enterprise ($2500+/мес)",
}


class SubscriptionMiddleware(BaseMiddleware):
    """Checks user's subscription plan before processing commands."""

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        api: APIClient | None = data.get("api")
        if not api:
            return await handler(event, data)

        # Fetch subscription
        try:
            sub = await api.get_subscription()
        except Exception:
            logger.exception("Failed to fetch subscription")
            sub = None

        user_plan = sub["plan"] if sub else "monitor"
        data["user_plan"] = user_plan
        data["subscription"] = sub

        # Check if the command requires a higher plan
        if event.text:
            command = event.text.split()[0].split("@")[0].lower()
            required_plan = PLAN_REQUIREMENTS.get(command)

            if required_plan:
                user_level = PLAN_ORDER.get(user_plan, 0)
                required_level = PLAN_ORDER.get(required_plan, 0)

                if user_level < required_level:
                    plan_name = PLAN_NAMES.get(required_plan, required_plan)
                    await event.answer(
                        f"Эта команда доступна начиная с тарифа "
                        f"<b>{plan_name}</b>.\n\n"
                        f"Ваш текущий тариф: <b>{user_plan.capitalize()}</b>\n\n"
                        "Используйте /billing для апгрейда."
                    )
                    return

        return await handler(event, data)
