import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import (
    admin, common, competitors, content, gamification,
    multiplayer_handler, onboarding, reports, training,
)
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.rate_limit import RateLimitMiddleware
from bot.middlewares.subscription import SubscriptionMiddleware
from bot.services.api_client import close_client

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)


def _get_bot_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    return token


def _get_fsm_storage():
    """Get FSM storage — Redis if available, otherwise memory (#067)."""
    redis_url = os.getenv("REDIS_URL", "")
    if redis_url:
        try:
            from aiogram.fsm.storage.redis import RedisStorage
            logger.info("Using Redis FSM storage: %s", redis_url.split("@")[-1])
            return RedisStorage.from_url(redis_url)
        except ImportError:
            logger.warning("aioredis not installed, falling back to MemoryStorage")
        except Exception:
            logger.exception("Failed to init Redis FSM storage, falling back to MemoryStorage")
    return MemoryStorage()


async def main() -> None:
    bot = Bot(
        token=_get_bot_token(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = _get_fsm_storage()
    dp = Dispatcher(storage=storage)

    # Register middlewares for messages
    dp.message.middleware(RateLimitMiddleware())
    dp.message.middleware(AuthMiddleware())
    dp.message.middleware(SubscriptionMiddleware())

    # Register middlewares for callback queries (#066: rate limit included)
    dp.callback_query.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())

    # Register routers (order matters: common first for /start and /help)
    dp.include_router(common.router)
    dp.include_router(onboarding.router)
    dp.include_router(competitors.router)
    dp.include_router(reports.router)
    dp.include_router(content.router)
    dp.include_router(training.router)
    dp.include_router(gamification.router)
    dp.include_router(multiplayer_handler.router)
    dp.include_router(admin.router)

    logger.info("Starting bot...")
    try:
        await dp.start_polling(bot)
    finally:
        await close_client()
        if hasattr(storage, "close"):
            await storage.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
