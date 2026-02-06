"""Gamification bot handlers: challenges, streaks, levels, coins.

Commands:
  /challenge  — View today's daily challenge
  /level      — View level, XP, coins, streak
  /shop       — Browse and buy shop items
"""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.api_client import APIClient

logger = logging.getLogger(__name__)
router = Router()

LEVEL_ICONS = {
    "trainee": "🌱",
    "junior": "⭐",
    "senior": "🏆",
    "expert": "💎",
    "master": "👑",
}


@router.message(Command("level"))
async def cmd_level(message: Message, api: APIClient = None, **kwargs) -> None:
    """Show gamification profile."""
    if not api:
        await message.answer("Ошибка подключения.")
        return

    try:
        profile = await api.get_gamification_profile()
    except Exception:
        logger.exception("Failed to fetch gamification profile")
        await message.answer("Не удалось загрузить профиль.")
        return

    icon = LEVEL_ICONS.get(profile.get("level", ""), "🌱")
    level = profile.get("level", "trainee").capitalize()
    xp = profile.get("xp", 0)
    coins = profile.get("coins", 0)
    streak = profile.get("current_streak", 0)
    longest = profile.get("longest_streak", 0)

    lines = [
        f"<b>{icon} Ваш профиль</b>\n",
        f"Уровень: <b>{level}</b>",
        f"XP: <b>{xp}</b>",
        f"Монеты: <b>{coins}</b> 🪙",
        f"Серия дней: <b>{streak}</b> 🔥",
        f"Лучшая серия: <b>{longest}</b>",
    ]

    builder = InlineKeyboardBuilder()
    builder.button(text="🎯 Челленджи", callback_data="action_challenges")
    builder.button(text="🛍 Магазин", callback_data="action_shop")
    builder.adjust(2)

    await message.answer("\n".join(lines), reply_markup=builder.as_markup())


@router.message(Command("challenge"))
async def cmd_challenge(message: Message, api: APIClient = None, **kwargs) -> None:
    """Show today's challenges."""
    if not api:
        await message.answer("Ошибка подключения.")
        return

    try:
        challenges = await api.get_daily_challenges()
    except Exception:
        logger.exception("Failed to fetch challenges")
        await message.answer("Не удалось загрузить челленджи.")
        return

    if not challenges:
        await message.answer("Сегодня нет активных челленджей.")
        return

    lines = ["<b>🎯 Дневные челленджи</b>\n"]
    for c in challenges:
        status = "✅" if c.get("is_completed") else "⬜"
        progress = c.get("progress", 0)
        target = c.get("target", 1)
        reward = c.get("reward_coins", 0)
        lines.append(f"{status} {c.get('label', '?')}")
        lines.append(f"   Прогресс: {progress}/{target} | Награда: {reward} 🪙")

    await message.answer("\n".join(lines))


@router.message(Command("shop"))
async def cmd_shop(message: Message, api: APIClient = None, **kwargs) -> None:
    """Show shop items."""
    if not api:
        await message.answer("Ошибка подключения.")
        return

    try:
        items = await api.get_shop_items()
        profile = await api.get_gamification_profile()
    except Exception:
        logger.exception("Failed to fetch shop")
        await message.answer("Не удалось загрузить магазин.")
        return

    coins = profile.get("coins", 0)
    lines = [f"<b>🛍 Магазин</b>\nВаши монеты: <b>{coins}</b> 🪙\n"]

    builder = InlineKeyboardBuilder()
    for item in items:
        price = item.get("price", 0)
        name = item.get("name", "?")
        lines.append(f"• {name} — {price} 🪙")
        builder.button(
            text=f"{name} ({price})",
            callback_data=f"shop_buy_{item['id']}",
        )
    builder.adjust(1)

    await message.answer("\n".join(lines), reply_markup=builder.as_markup())


@router.callback_query(lambda c: c.data and c.data.startswith("shop_buy_"))
async def cb_shop_buy(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    """Purchase a shop item."""
    if not api:
        await callback.answer("Ошибка")
        return

    item_id = callback.data.replace("shop_buy_", "")
    try:
        result = await api.purchase_shop_item(item_id)
    except Exception:
        logger.exception("Failed to purchase item")
        await callback.answer("Ошибка покупки")
        return

    if "error" in result:
        await callback.answer(result["error"])
    else:
        item_name = result.get("item", {}).get("name", "предмет")
        await callback.answer(f"Куплено: {item_name}!")
        await callback.message.answer(f"✅ Вы купили <b>{item_name}</b>!")


@router.callback_query(lambda c: c.data == "action_challenges")
async def cb_challenges(callback: CallbackQuery, **kwargs) -> None:
    await callback.answer()
    await cmd_challenge(callback.message, **kwargs)


@router.callback_query(lambda c: c.data == "action_shop")
async def cb_shop(callback: CallbackQuery, **kwargs) -> None:
    await callback.answer()
    await cmd_shop(callback.message, **kwargs)
