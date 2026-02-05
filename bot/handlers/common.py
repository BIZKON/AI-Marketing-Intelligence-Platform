from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "<b>AI Marketing Intelligence Platform</b>\n\n"
        "Competitive intelligence & content automation for marketers.\n\n"
        "Use /setup to configure your account.\n"
        "Use /help to see all available commands."
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>Available commands:</b>\n\n"
        "/start — Welcome message\n"
        "/setup — Initial setup and onboarding\n"
        "/competitors — Manage tracked competitors\n"
        "/digest — Request weekly digest\n"
        "/report — Get daily competitor report\n"
        "/plan — Generate content plan (Creator+)\n"
        "/status — Content pipeline status (Creator+)\n"
        "/approve — Approve content for publishing (Creator+)\n"
        "/voice — Request voice report (Creator+)\n"
        "/video — Request video report (Autopilot+)\n"
        "/queue — View publication queue (Autopilot+)\n"
        "/billing — Subscription & billing info\n"
        "/help — This help message"
    )
