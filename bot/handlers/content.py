"""Content management handler: plans, tasks, approvals, billing — with API integration."""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.api_client import APIClient

logger = logging.getLogger(__name__)
router = Router()


# ── Content Plan ─────────────────────────────────────────────────────────────


@router.message(Command("plan"))
async def cmd_plan(message: Message, api: APIClient = None, **kwargs) -> None:
    """Generate a content plan (Creator+). Plan check is in SubscriptionMiddleware."""
    if not api:
        await message.answer("Ошибка подключения. Попробуйте позже.")
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="Недельный план", callback_data="plan_weekly")
    builder.button(text="Месячный план", callback_data="plan_monthly")
    builder.adjust(2)

    await message.answer(
        "<b>Генерация контент-плана</b>\n\n"
        "AI проанализирует инсайты из мониторинга конкурентов "
        "и ваш профиль бренда для создания плана.\n\n"
        "Выберите период:",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("plan_"))
async def cb_create_plan(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    period = callback.data.replace("plan_", "")

    if not api:
        await callback.answer("Ошибка")
        return

    await callback.message.answer(
        f"<b>Создаю {period} контент-план...</b>\n\n"
        "Это может занять некоторое время."
    )

    try:
        plan = await api.create_plan(period=period)
        await callback.message.answer(
            "<b>Контент-план создан!</b>\n\n"
            f"Период: {period}\n"
            f"ID: <code>{plan['id'][:8]}...</code>\n\n"
            "Используйте /status для просмотра задач."
        )
    except Exception as e:
        error_text = str(e)
        if "403" in error_text:
            await callback.message.answer(
                "Контент-планы доступны начиная с тарифа Creator.\n\n"
                "Используйте /billing для апгрейда."
            )
        else:
            logger.exception("Failed to create content plan")
            await callback.message.answer("Ошибка при создании плана. Попробуйте позже.")
    await callback.answer()


# ── Content Status ───────────────────────────────────────────────────────────


STATUS_LABELS = {
    "pending": "⏳ Ожидает",
    "draft": "📝 Черновик",
    "in_review": "👀 На ревью",
    "approved": "✅ Утверждено",
    "published": "📢 Опубликовано",
}


@router.message(Command("status"))
async def cmd_status(message: Message, api: APIClient = None, **kwargs) -> None:
    """Show content pipeline status (Creator+)."""
    if not api:
        await message.answer("Ошибка подключения. Попробуйте позже.")
        return

    try:
        tasks = await api.list_tasks()
    except Exception:
        logger.exception("Failed to fetch tasks")
        await message.answer("Не удалось загрузить статус пайплайна.")
        return

    if not tasks:
        await message.answer(
            "<b>Контент-пайплайн пуст.</b>\n\n"
            "Используйте /plan чтобы сгенерировать контент-план."
        )
        return

    # Group by status
    by_status: dict[str, list] = {}
    for task in tasks:
        s = task.get("status", "pending")
        by_status.setdefault(s, []).append(task)

    lines = ["<b>Контент-пайплайн:</b>\n"]
    for status_key in ("pending", "draft", "in_review", "approved", "published"):
        group = by_status.get(status_key, [])
        if group:
            label = STATUS_LABELS.get(status_key, status_key)
            lines.append(f"\n{label} ({len(group)}):")
            for task in group[:3]:
                platform = task.get("platform", "")
                lines.append(f"  • {task['title']} [{platform}]")
            if len(group) > 3:
                lines.append(f"  ... и ещё {len(group) - 3}")

    await message.answer("\n".join(lines))


# ── Content Approval ─────────────────────────────────────────────────────────


@router.message(Command("approve"))
async def cmd_approve(message: Message, api: APIClient = None, **kwargs) -> None:
    """List tasks awaiting review and allow approval (Creator+)."""
    if not api:
        await message.answer("Ошибка подключения. Попробуйте позже.")
        return

    try:
        tasks = await api.list_tasks(task_status="in_review")
    except Exception:
        logger.exception("Failed to fetch review tasks")
        await message.answer("Не удалось загрузить задачи.")
        return

    if not tasks:
        await message.answer(
            "<b>Нет задач на ревью.</b>\n\n"
            "Задачи появятся здесь после генерации AI-контента."
        )
        return

    lines = ["<b>Задачи на утверждение:</b>\n"]
    builder = InlineKeyboardBuilder()

    for task in tasks[:10]:
        lines.append(
            f"• <b>{task['title']}</b> [{task.get('platform', '')}]\n"
            f"  {(task.get('body') or '')[:100]}..."
        )
        builder.button(
            text=f"✅ {task['title'][:25]}",
            callback_data=f"approve_{task['id'][:8]}",
        )

    builder.adjust(1)
    await message.answer("\n".join(lines), reply_markup=builder.as_markup())


@router.callback_query(lambda c: c.data and c.data.startswith("approve_"))
async def cb_approve_task(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    prefix = callback.data.replace("approve_", "")

    if not api:
        await callback.answer("Ошибка")
        return

    try:
        tasks = await api.list_tasks(task_status="in_review")
        target = next((t for t in tasks if t["id"].startswith(prefix)), None)
        if target:
            await api.approve_task(target["id"])
            await callback.message.answer(
                f"✅ Задача <b>{target['title']}</b> утверждена!"
            )
        else:
            await callback.message.answer("Задача не найдена или уже утверждена.")
    except Exception:
        logger.exception("Failed to approve task")
        await callback.message.answer("Ошибка при утверждении задачи.")
    await callback.answer()


# ── Publication Queue ────────────────────────────────────────────────────────


@router.message(Command("queue"))
async def cmd_queue(message: Message, api: APIClient = None, **kwargs) -> None:
    """Show publication queue (Autopilot+)."""
    if not api:
        await message.answer("Ошибка подключения. Попробуйте позже.")
        return

    try:
        tasks = await api.list_tasks(task_status="approved")
    except Exception:
        logger.exception("Failed to fetch queue")
        await message.answer("Не удалось загрузить очередь.")
        return

    if not tasks:
        await message.answer(
            "<b>Очередь публикаций пуста.</b>\n\n"
            "Утверждённые задачи появятся здесь автоматически."
        )
        return

    lines = ["<b>Очередь публикаций:</b>\n"]
    for i, task in enumerate(tasks, 1):
        scheduled = task.get("scheduled_at", "не запланировано")
        if isinstance(scheduled, str) and len(scheduled) > 10:
            scheduled = scheduled[:16].replace("T", " ")
        lines.append(
            f"{i}. <b>{task['title']}</b> [{task.get('platform', '')}]\n"
            f"   Запланировано: {scheduled}"
        )

    await message.answer("\n".join(lines))


# ── Billing ──────────────────────────────────────────────────────────────────


@router.message(Command("billing"))
async def cmd_billing(
    message: Message,
    api: APIClient = None,
    subscription: dict = None,
    user_plan: str = "monitor",
    **kwargs,
) -> None:
    """Show billing info and provide upgrade/portal links."""
    if not api:
        await message.answer("Ошибка подключения. Попробуйте позже.")
        return

    plan_display = "Monitor (бесплатно)"
    status_display = "Активна"
    can_upgrade = True

    if subscription:
        plan_display = subscription.get("plan_display", user_plan.capitalize())
        status_display = subscription.get("status", "active").replace("_", " ").capitalize()
        can_upgrade = subscription.get("can_upgrade", True)

    text = (
        "<b>Подписка и биллинг</b>\n\n"
        f"Тариф: <b>{plan_display}</b>\n"
        f"Статус: {status_display}\n"
    )

    builder = InlineKeyboardBuilder()

    if can_upgrade:
        text += "\nДоступные тарифы для апгрейда:"

        plans = [
            ("Creator — $499/мес", "checkout_creator"),
            ("Autopilot — $999/мес", "checkout_autopilot"),
            ("Enterprise — $2500+/мес", "checkout_enterprise"),
        ]

        plan_order = {"monitor": 0, "creator": 1, "autopilot": 2, "enterprise": 3}
        current_level = plan_order.get(user_plan, 0)

        for name, callback_data in plans:
            plan_key = callback_data.replace("checkout_", "")
            if plan_order.get(plan_key, 0) > current_level:
                builder.button(text=name, callback_data=callback_data)

    builder.button(text="Управление подпиской", callback_data="billing_portal")
    builder.adjust(1)

    await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(lambda c: c.data and c.data.startswith("checkout_"))
async def cb_checkout(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    plan = callback.data.replace("checkout_", "")

    if not api:
        await callback.answer("Ошибка")
        return

    try:
        result = await api.create_checkout(plan=plan)
        checkout_url = result.get("checkout_url", "")
        if checkout_url:
            await callback.message.answer(
                f"<b>Оплата тарифа {plan.capitalize()}</b>\n\n"
                f"Перейдите по ссылке для оформления:\n{checkout_url}"
            )
        else:
            await callback.message.answer("Не удалось создать ссылку на оплату.")
    except Exception:
        logger.exception("Failed to create checkout")
        await callback.message.answer("Ошибка при создании платёжной сессии. Попробуйте позже.")
    await callback.answer()


@router.callback_query(lambda c: c.data == "billing_portal")
async def cb_billing_portal(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    if not api:
        await callback.answer("Ошибка")
        return

    try:
        result = await api.create_portal()
        portal_url = result.get("portal_url", "")
        if portal_url:
            await callback.message.answer(
                "<b>Управление подпиской</b>\n\n"
                f"Перейдите по ссылке:\n{portal_url}"
            )
        else:
            await callback.message.answer("Не удалось создать ссылку на портал.")
    except Exception:
        logger.exception("Failed to create portal session")
        await callback.message.answer("Ошибка при создании портала. Попробуйте позже.")
    await callback.answer()
