"""Competitor management handler: add, list, delete competitors via API."""

import logging
from urllib.parse import urlparse

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.api_client import APIClient
from bot.states.competitors import AddCompetitorStates

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("competitors"))
async def cmd_competitors(message: Message, **kwargs) -> None:
    builder = InlineKeyboardBuilder()
    builder.button(text="Добавить конкурента", callback_data="comp_add")
    builder.button(text="Список конкурентов", callback_data="comp_list")
    builder.adjust(2)

    await message.answer(
        "<b>Управление конкурентами</b>\n\n"
        "Отслеживайте конкурентов на разных платформах.",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(lambda c: c.data == "comp_add")
async def cb_add_competitor(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddCompetitorStates.waiting_name)
    await callback.message.answer("Введите название конкурента:")
    await callback.answer()


@router.message(AddCompetitorStates.waiting_name)
async def process_competitor_name(message: Message, state: FSMContext) -> None:
    if not message.text or len(message.text.strip()) < 2:
        await message.answer("Название должно содержать минимум 2 символа:")
        return

    await state.update_data(name=message.text.strip())
    await state.set_state(AddCompetitorStates.waiting_url)
    await message.answer("Введите URL сайта конкурента (или /skip чтобы пропустить):")


@router.message(AddCompetitorStates.waiting_url)
async def process_competitor_url(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    url = None
    if raw and raw != "/skip":
        # Validate URL format (#083)
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        if parsed.scheme in ("http", "https") and parsed.netloc:
            url = parsed.geturl()
        else:
            await message.answer("Некорректный URL. Введите правильный адрес или /skip:")
            return
    await state.update_data(url=url)
    await state.set_state(AddCompetitorStates.waiting_platforms)

    builder = InlineKeyboardBuilder()
    builder.button(text="Telegram", callback_data="plat_telegram")
    builder.button(text="YouTube", callback_data="plat_youtube")
    builder.button(text="VK", callback_data="plat_vk")
    builder.button(text="Сайт/Блог", callback_data="plat_website")
    builder.button(text="Готово", callback_data="plat_done")
    builder.adjust(2, 2, 1)

    await message.answer(
        "Выберите платформы для отслеживания (нажмите для выбора, затем Готово):",
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

    # Show current selection with checkmarks
    platform_names = {"telegram": "Telegram", "youtube": "YouTube", "vk": "VK", "website": "Сайт/Блог"}
    selected = [f"✓ {platform_names.get(p, p)}" for p in platforms]
    await callback.answer(f"Выбрано: {', '.join(selected) or 'ничего'}")


@router.callback_query(lambda c: c.data == "plat_done")
async def cb_platforms_done(
    callback: CallbackQuery,
    state: FSMContext,
    api: APIClient = None,
    **kwargs,
) -> None:
    data = await state.get_data()
    name = data.get("name", "")
    url = data.get("url")
    platforms = data.get("platforms", [])

    await state.clear()

    if not api:
        await callback.message.answer("Ошибка: не удалось сохранить. Попробуйте позже.")
        await callback.answer()
        return

    try:
        result = await api.create_competitor(name=name, url=url, platforms=platforms)
    except Exception as e:
        error_text = str(e)
        if "403" in error_text:
            await callback.message.answer(
                "Достигнут лимит конкурентов для вашего тарифа.\n\n"
                "Используйте /billing для апгрейда."
            )
        else:
            logger.exception("Failed to create competitor")
            await callback.message.answer("Ошибка при добавлении конкурента. Попробуйте позже.")
        await callback.answer()
        return

    platform_names = {"telegram": "Telegram", "youtube": "YouTube", "vk": "VK", "website": "Сайт/Блог"}
    platforms_str = ", ".join(platform_names.get(p, p) for p in platforms) or "не выбраны"

    text = (
        f"<b>Конкурент добавлен!</b>\n\n"
        f"Название: {result.get('name', name)}\n"
        f"URL: {result.get('url') or 'N/A'}\n"
        f"Платформы: {platforms_str}"
    )

    warning = result.get("limit_warning")
    if warning:
        text += f"\n\n{warning}"

    await callback.message.answer(text)
    await callback.answer()


@router.callback_query(lambda c: c.data == "comp_list")
async def cb_list_competitors(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    if not api:
        await callback.message.answer("Ошибка загрузки. Попробуйте позже.")
        await callback.answer()
        return

    try:
        competitors = await api.list_competitors()
    except Exception:
        logger.exception("Failed to list competitors")
        await callback.message.answer("Не удалось загрузить список конкурентов.")
        await callback.answer()
        return

    if not competitors:
        await callback.message.answer(
            "У вас пока нет отслеживаемых конкурентов.\n\n"
            "Используйте /competitors → «Добавить конкурента» чтобы начать."
        )
        await callback.answer()
        return

    lines = ["<b>Ваши конкуренты:</b>\n"]
    for i, comp in enumerate(competitors, 1):
        platforms = ", ".join(comp.get("platforms", [])) or "—"
        status = "✅" if comp.get("is_active") else "⏸"
        lines.append(f"{i}. {status} <b>{comp['name']}</b> ({platforms})")
        if comp.get("url"):
            lines.append(f"   {comp['url']}")

    builder = InlineKeyboardBuilder()
    builder.button(text="Добавить ещё", callback_data="comp_add")

    # Add delete buttons for each competitor
    for comp in competitors[:5]:
        builder.button(
            text=f"🗑 {comp['name'][:20]}",
            callback_data=f"comp_del_{comp['id'][:8]}",
        )
    builder.adjust(1)

    await callback.message.answer("\n".join(lines), reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("comp_del_"))
async def cb_delete_competitor(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    if not api:
        await callback.answer("Ошибка")
        return

    # Find full competitor ID by prefix
    prefix = callback.data.replace("comp_del_", "")
    try:
        competitors = await api.list_competitors()
        target = next((c for c in competitors if c["id"].startswith(prefix)), None)
        if target:
            await api.delete_competitor(target["id"])
            await callback.message.answer(f"Конкурент <b>{target['name']}</b> удалён.")
        else:
            await callback.message.answer("Конкурент не найден.")
    except Exception:
        logger.exception("Failed to delete competitor")
        await callback.message.answer("Ошибка при удалении.")
    await callback.answer()
