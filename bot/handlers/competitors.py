from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.states.competitors import AddCompetitorStates

router = Router()


@router.message(Command("competitors"))
async def cmd_competitors(message: Message) -> None:
    builder = InlineKeyboardBuilder()
    builder.button(text="Add competitor", callback_data="comp_add")
    builder.button(text="List competitors", callback_data="comp_list")
    builder.adjust(2)

    await message.answer(
        "<b>Competitor Management</b>\n\n"
        "Track your competitors across platforms.",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(lambda c: c.data == "comp_add")
async def cb_add_competitor(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddCompetitorStates.waiting_name)
    await callback.message.answer("Enter the competitor's name:")
    await callback.answer()


@router.message(AddCompetitorStates.waiting_name)
async def process_competitor_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text)
    await state.set_state(AddCompetitorStates.waiting_url)
    await message.answer("Enter the competitor's website URL (or skip with /skip):")


@router.message(AddCompetitorStates.waiting_url)
async def process_competitor_url(message: Message, state: FSMContext) -> None:
    url = None if message.text == "/skip" else message.text
    await state.update_data(url=url)
    await state.set_state(AddCompetitorStates.waiting_platforms)

    builder = InlineKeyboardBuilder()
    builder.button(text="Telegram", callback_data="plat_telegram")
    builder.button(text="YouTube", callback_data="plat_youtube")
    builder.button(text="VK", callback_data="plat_vk")
    builder.button(text="Website/Blog", callback_data="plat_website")
    builder.button(text="Done", callback_data="plat_done")
    builder.adjust(2, 2, 1)

    await message.answer(
        "Select platforms to track (tap to toggle, then Done):",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("plat_") and c.data != "plat_done")
async def cb_toggle_platform(callback: CallbackQuery, state: FSMContext) -> None:
    platform = callback.data.replace("plat_", "")
    data = await state.get_data()
    platforms = data.get("platforms", [])

    if platform in platforms:
        platforms.remove(platform)
    else:
        platforms.append(platform)

    await state.update_data(platforms=platforms)
    await callback.answer(f"Selected: {', '.join(platforms) or 'none'}")


@router.callback_query(lambda c: c.data == "plat_done")
async def cb_platforms_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    # TODO: save competitor via API
    await state.clear()
    await callback.message.answer(
        f"<b>Competitor added!</b>\n\n"
        f"Name: {data.get('name')}\n"
        f"URL: {data.get('url', 'N/A')}\n"
        f"Platforms: {', '.join(data.get('platforms', []))}"
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "comp_list")
async def cb_list_competitors(callback: CallbackQuery) -> None:
    # TODO: fetch from API
    await callback.message.answer("Your competitors will be listed here.")
    await callback.answer()
