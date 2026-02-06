"""Multiplayer bot handlers: create/join competitive sessions.

Commands:
  /battle    — Create or join a multiplayer session
"""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.api_client import APIClient

logger = logging.getLogger(__name__)
router = Router()


class MultiplayerStates(StatesGroup):
    entering_code = State()


@router.message(Command("battle"))
async def cmd_battle(message: Message, state: FSMContext, api: APIClient = None, **kwargs) -> None:
    """Show multiplayer options."""
    if not api:
        await message.answer("Ошибка подключения.")
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="🆕 Создать сессию", callback_data="mp_create")
    builder.button(text="🔑 Присоединиться", callback_data="mp_join")
    builder.button(text="🏆 Таблица лидеров", callback_data="mp_leaderboard")
    builder.adjust(1)

    await message.answer(
        "<b>Мультиплеер</b>\n\n"
        "Соревнуйтесь с коллегами в продажах!\n"
        "Создайте сессию или присоединитесь по коду.",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(lambda c: c.data == "mp_create")
async def cb_create(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    """Create a multiplayer session."""
    if not api:
        await callback.answer("Ошибка")
        return

    try:
        scenarios = await api.list_training_scenarios()
    except Exception:
        await callback.answer("Ошибка загрузки")
        return

    if not scenarios:
        await callback.answer("Нет сценариев")
        return

    builder = InlineKeyboardBuilder()
    for sc in scenarios[:6]:
        builder.button(
            text=sc["title"][:30],
            callback_data=f"mp_scenario_{sc['id'][:8]}",
        )
    builder.adjust(1)

    # Store scenario mapping
    scenario_map = {sc["id"][:8]: sc["id"] for sc in scenarios}
    from aiogram.fsm.context import FSMContext
    # Can't access state here directly, so we use a simpler approach
    await callback.message.answer(
        "Выберите сценарий для мультиплеера:",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "mp_join")
async def cb_join(callback: CallbackQuery, state: FSMContext, **kwargs) -> None:
    """Ask for session code."""
    await state.set_state(MultiplayerStates.entering_code)
    await callback.message.answer("Введите 6-символьный код сессии:")
    await callback.answer()


@router.message(MultiplayerStates.entering_code)
async def process_join_code(
    message: Message, state: FSMContext, api: APIClient = None, **kwargs
) -> None:
    """Process the multiplayer session code."""
    if not api or not message.text:
        return

    code = message.text.strip().upper()
    if len(code) != 6:
        await message.answer("Код должен быть 6 символов. Попробуйте снова:")
        return

    try:
        result = await api.join_multiplayer_session(code)
    except Exception:
        logger.exception("Failed to join session")
        await message.answer("Не удалось присоединиться. Проверьте код.")
        await state.clear()
        return

    await state.clear()
    session_id = result.get("session_id", "")
    await message.answer(
        f"✅ Вы присоединились к сессии!\n"
        f"ID: <code>{session_id[:8]}</code>\n\n"
        f"Ожидайте начала от организатора."
    )


@router.callback_query(lambda c: c.data == "mp_leaderboard")
async def cb_leaderboard(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    """Show multiplayer leaderboard."""
    if not api:
        await callback.answer("Ошибка")
        return

    try:
        lb = await api.get_multiplayer_leaderboard()
    except Exception:
        await callback.answer("Ошибка загрузки")
        return

    if not lb:
        await callback.message.answer("Таблица лидеров пока пуста.")
        await callback.answer()
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["<b>🏆 Таблица лидеров</b>\n"]
    for i, entry in enumerate(lb[:10]):
        icon = medals[i] if i < 3 else f"{i+1}."
        name = entry.get("user_name", "?")
        score = entry.get("avg_score", 0)
        lines.append(f"{icon} {name} — {score:.0f}")

    await callback.message.answer("\n".join(lines))
    await callback.answer()
