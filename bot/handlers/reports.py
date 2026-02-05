from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("digest"))
async def cmd_digest(message: Message) -> None:
    # TODO: trigger digest generation via API/Celery
    await message.answer(
        "<b>Generating weekly digest...</b>\n\n"
        "This may take a moment. You'll receive the report shortly."
    )


@router.message(Command("report"))
async def cmd_report(message: Message) -> None:
    # TODO: trigger daily report
    await message.answer(
        "<b>Generating competitor report...</b>\n\n"
        "Analyzing latest competitor activity..."
    )


@router.message(Command("voice"))
async def cmd_voice(message: Message) -> None:
    # TODO: check Creator+ plan, trigger voice generation
    await message.answer(
        "<b>Generating voice report...</b>\n\n"
        "Converting your latest digest to audio. This feature requires Creator plan or higher."
    )


@router.message(Command("video"))
async def cmd_video(message: Message) -> None:
    # TODO: check Autopilot+ plan, trigger video generation
    await message.answer(
        "<b>Generating video report...</b>\n\n"
        "Creating a video summary with AI avatar. This feature requires Autopilot plan or higher."
    )
