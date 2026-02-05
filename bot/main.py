import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.handlers import common, competitors, content, onboarding, reports
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.rate_limit import RateLimitMiddleware
from bot.middlewares.subscription import SubscriptionMiddleware

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)


def _get_bot_token() -> str:
    import os

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    return token


async def main() -> None:
    bot = Bot(
        token=_get_bot_token(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Register middlewares
    dp.message.middleware(RateLimitMiddleware())
    dp.message.middleware(AuthMiddleware())
    dp.message.middleware(SubscriptionMiddleware())

    # Register routers
    dp.include_router(common.router)
    dp.include_router(onboarding.router)
    dp.include_router(competitors.router)
    dp.include_router(reports.router)
    dp.include_router(content.router)

    logger.info("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
