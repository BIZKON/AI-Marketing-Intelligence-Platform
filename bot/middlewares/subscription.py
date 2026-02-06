"""Subscription middleware: fetches user's plan and injects it into handler context.

Also blocks commands that require a higher plan with an upsell message.
Uses TTL cache to avoid hitting API on every message (#063).
"""

from __future__ import annotations

import logging
import time
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
    "creator": "Creator ($499/\u043c\u0435\u0441)",
    "autopilot": "Autopilot ($999/\u043c\u0435\u0441)",
    "enterprise": "Enterprise ($2500+/\u043c\u0435\u0441)",
}

# Subscription cache: telegram_user_id -> (subscription_data, timestamp) (#063)
_sub_cache: dict[int, tuple[dict | None, float]] = {}
_SUB_CACHE_TTL = 300  # 5 minutes


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

        user_id = event.from_user.id if event.from_user else 0

        # Check cache first (#063)
        cached = _sub_cache.get(user_id)
        if cached and (time.monotonic() - cached[1]) < _SUB_CACHE_TTL:
            sub = cached[0]
        else:
            try:
                sub = await api.get_subscription()
            except Exception:
                logger.exception("Failed to fetch subscription")
                sub = None
            _sub_cache[user_id] = (sub, time.monotonic())

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
                        f"\u042d\u0442\u0430 \u043a\u043e\u043c\u0430\u043d\u0434\u0430 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430 \u043d\u0430\u0447\u0438\u043d\u0430\u044f \u0441 \u0442\u0430\u0440\u0438\u0444\u0430 "
                        f"<b>{plan_name}</b>.\n\n"
                        f"\u0412\u0430\u0448 \u0442\u0435\u043a\u0443\u0449\u0438\u0439 \u0442\u0430\u0440\u0438\u0444: <b>{user_plan.capitalize()}</b>\n\n"
                        "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439\u0442\u0435 /billing \u0434\u043b\u044f \u0430\u043f\u0433\u0440\u0435\u0439\u0434\u0430."
                    )
                    return

        return await handler(event, data)
