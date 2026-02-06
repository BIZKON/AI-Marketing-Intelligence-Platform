from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.api_client import APIClient

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, api: APIClient = None, user_data: dict = None, **kwargs) -> None:
    is_new = not user_data or not user_data.get("brand_name")

    text = (
        "<b>AI Marketing Intelligence Platform</b>\n\n"
        "Платформа конкурентной разведки и контент-автоматизации.\n\n"
    )

    if is_new:
        text += (
            "Добро пожаловать! Для начала работы:\n\n"
            "1. /setup — настройте профиль бренда\n"
            "2. /competitors — добавьте конкурентов\n"
            "3. /billing — выберите тарифный план\n"
            "4. /help — все доступные команды"
        )
    else:
        brand = user_data.get("brand_name", "")
        text += (
            f"С возвращением, <b>{brand}</b>!\n\n"
            "/digest — запросить дайджест\n"
            "/competitors — управление конкурентами\n"
            "/plan — контент-план (Creator+)\n"
            "/billing — подписка и оплата\n"
            "/help — все команды"
        )

    builder = InlineKeyboardBuilder()
    if is_new:
        builder.button(text="Настроить профиль", callback_data="action_setup")
    builder.button(text="Конкуренты", callback_data="comp_list")
    builder.button(text="Подписка", callback_data="action_billing")
    builder.adjust(1 if is_new else 2)

    await message.answer(text, reply_markup=builder.as_markup())


@router.message(Command("help"))
async def cmd_help(message: Message, user_plan: str = "monitor", **kwargs) -> None:
    commands = [
        ("/start", "Приветствие"),
        ("/setup", "Настройка профиля бренда"),
        ("/competitors", "Управление конкурентами"),
        ("/digest", "Запросить еженедельный дайджест"),
        ("/report", "Отчёт по конкурентам"),
    ]

    if user_plan in ("creator", "autopilot", "enterprise"):
        commands.extend([
            ("/plan", "Генерация контент-плана"),
            ("/status", "Статус контент-пайплайна"),
            ("/approve", "Утверждение контента"),
            ("/voice", "Голосовой отчёт"),
        ])

    if user_plan in ("autopilot", "enterprise"):
        commands.extend([
            ("/video", "Видеоотчёт с AI-аватаром"),
            ("/queue", "Очередь публикаций"),
        ])

    commands.extend([
        ("/train", "Тренажёр продаж (AI-клиент)"),
        ("/mystats", "Статистика тренировок"),
        ("/usage", "Использование лимитов"),
        ("/billing", "Подписка и биллинг"),
        ("/help", "Эта справка"),
    ])

    lines = ["<b>Доступные команды:</b>\n"]
    for cmd, desc in commands:
        lines.append(f"{cmd} — {desc}")

    await message.answer("\n".join(lines))


@router.message(Command("usage"))
async def cmd_usage(message: Message, api: APIClient = None, user_plan: str = "monitor", **kwargs) -> None:
    """Show current resource usage against plan limits."""
    if not api:
        await message.answer("Не удалось получить данные. Попробуйте позже.")
        return

    try:
        usage = await api.get_usage_summary()
    except Exception:
        await message.answer("Не удалось загрузить данные об использовании.")
        return

    lines = [
        f"<b>Использование ({user_plan.capitalize()})</b>\n",
        f"Конкуренты: {usage['competitors']}/{usage['competitors_limit']}",
    ]
    if usage["tasks_limit"] > 0:
        lines.append(f"Задачи (мес): {usage['tasks_this_month']}/{usage['tasks_limit']}")
    if usage["voice_limit"] > 0:
        lines.append(f"Голосовые (нед): {usage['voice_this_week']}/{usage['voice_limit']}")
    if usage["video_limit"] > 0:
        lines.append(f"Видео (нед): {usage['video_this_week']}/{usage['video_limit']}")

    await message.answer("\n".join(lines))


@router.callback_query(lambda c: c.data == "action_setup")
async def cb_action_setup(callback, **kwargs) -> None:
    """Directly trigger onboarding setup flow (#085)."""
    from bot.handlers.onboarding import cmd_setup
    await callback.answer()
    await cmd_setup(callback.message, **kwargs)


@router.callback_query(lambda c: c.data == "action_billing")
async def cb_action_billing(callback, api=None, **kwargs) -> None:
    """Directly show billing info (#085)."""
    await callback.answer()
    if api:
        try:
            sub = await api.get_subscription()
            plan = sub["plan"] if sub else "monitor"
            status = sub["status"] if sub else "none"
            await callback.message.answer(
                f"<b>Подписка</b>\n\n"
                f"Тариф: <b>{plan.capitalize()}</b>\n"
                f"Статус: {status}\n\n"
                "Для изменения тарифа используйте /billing."
            )
        except Exception:
            await callback.message.answer("Используйте /billing для управления подпиской.")
    else:
        await callback.message.answer("Используйте /billing для управления подпиской.")
