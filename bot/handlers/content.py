from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("plan"))
async def cmd_plan(message: Message) -> None:
    # TODO: check Creator+ plan, trigger plan generation via Celery
    await message.answer(
        "<b>Generating your weekly content plan...</b>\n\n"
        "AI is analyzing competitor insights and your brand profile to create a tailored plan."
    )


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    # TODO: fetch tasks from API
    await message.answer(
        "<b>Content Pipeline Status</b>\n\n"
        "Your content tasks will be displayed here:\n"
        "- Pending\n"
        "- In Draft\n"
        "- In Review\n"
        "- Approved\n"
        "- Published"
    )


@router.message(Command("approve"))
async def cmd_approve(message: Message) -> None:
    # TODO: list tasks in review, allow selection
    await message.answer(
        "<b>Content Approval</b>\n\n"
        "Tasks awaiting your review will be listed here."
    )


@router.message(Command("queue"))
async def cmd_queue(message: Message) -> None:
    # TODO: check Autopilot+ plan, list scheduled publications
    await message.answer(
        "<b>Publication Queue</b>\n\n"
        "Scheduled publications will be displayed here. Requires Autopilot plan."
    )


@router.message(Command("billing"))
async def cmd_billing(message: Message) -> None:
    # TODO: fetch subscription info, provide Stripe portal link
    await message.answer(
        "<b>Billing & Subscription</b>\n\n"
        "Current plan: —\n"
        "Status: —\n\n"
        "Manage your subscription via the link below."
    )
