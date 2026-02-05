"""Content management handler: plans, tasks, drafts, approvals, publishing, billing."""

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
    """Generate a content plan (Creator+)."""
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
        "AI анализирует конкурентов и генерирует стратегию. Подождите."
    )

    try:
        plan = await api.create_plan(period=period)
        plan_id = plan["id"]

        builder = InlineKeyboardBuilder()
        builder.button(text="📝 Сгенерировать драфты", callback_data=f"gendrafts_{plan_id[:8]}")
        builder.button(text="📋 Посмотреть задачи", callback_data=f"plantasks_{plan_id[:8]}")
        builder.adjust(1)

        await callback.message.answer(
            "<b>Контент-план создан!</b>\n\n"
            f"Период: {period}\n"
            f"ID: <code>{plan_id[:8]}...</code>\n\n"
            "Теперь можно сгенерировать AI-драфты для всех задач плана "
            "или посмотреть список задач.",
            reply_markup=builder.as_markup(),
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


@router.callback_query(lambda c: c.data and c.data.startswith("gendrafts_"))
async def cb_generate_plan_drafts(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    """Generate AI drafts for all pending tasks in a plan."""
    prefix = callback.data.replace("gendrafts_", "")

    if not api:
        await callback.answer("Ошибка")
        return

    await callback.message.answer("⏳ <b>Генерирую AI-драфты...</b>\nЭто может занять некоторое время.")

    try:
        # Find the plan by prefix
        plans = await api.list_plans()
        target_plan = next((p for p in plans if p["id"].startswith(prefix)), None)
        if not target_plan:
            await callback.message.answer("План не найден.")
            await callback.answer()
            return

        result = await api.generate_plan_drafts(target_plan["id"])
        await callback.message.answer(
            f"<b>Драфты сгенерированы!</b>\n\n"
            f"Создано: {result.get('generated_count', 0)} из {result.get('total_pending', 0)}\n\n"
            "Используйте /approve для ревью и утверждения."
        )
    except Exception:
        logger.exception("Failed to generate plan drafts")
        await callback.message.answer("Ошибка при генерации драфтов.")
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("plantasks_"))
async def cb_show_plan_tasks(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    """Show tasks for a specific plan."""
    prefix = callback.data.replace("plantasks_", "")

    if not api:
        await callback.answer("Ошибка")
        return

    try:
        plans = await api.list_plans()
        target_plan = next((p for p in plans if p["id"].startswith(prefix)), None)
        if not target_plan:
            await callback.message.answer("План не найден.")
            await callback.answer()
            return

        tasks = await api.list_tasks(plan_id=target_plan["id"])
        if not tasks:
            await callback.message.answer("В плане пока нет задач.")
            await callback.answer()
            return

        lines = [f"<b>Задачи плана ({len(tasks)}):</b>\n"]
        for i, task in enumerate(tasks[:15], 1):
            status_icon = STATUS_LABELS.get(task.get("status", "pending"), task.get("status", ""))
            platform = task.get("platform", "")
            lines.append(f"{i}. {status_icon} <b>{task['title']}</b> [{platform}]")

        await callback.message.answer("\n".join(lines))
    except Exception:
        logger.exception("Failed to show plan tasks")
        await callback.message.answer("Ошибка загрузки задач.")
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

    # Quick actions
    builder = InlineKeyboardBuilder()
    if by_status.get("pending"):
        builder.button(text="📝 Сгенерировать драфты", callback_data="gen_pending")
    if by_status.get("in_review"):
        builder.button(text="👀 Ревью задач", callback_data="go_approve")
    if by_status.get("approved"):
        builder.button(text="📢 Очередь публикаций", callback_data="go_queue")
    builder.adjust(1)

    await message.answer("\n".join(lines), reply_markup=builder.as_markup() if builder.export() else None)


@router.callback_query(lambda c: c.data == "go_approve")
async def cb_go_approve(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    await callback.answer()
    await cmd_approve(callback.message, api=api)


@router.callback_query(lambda c: c.data == "go_queue")
async def cb_go_queue(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    await callback.answer()
    await cmd_queue(callback.message, api=api)


# ── Draft Preview ────────────────────────────────────────────────────────────


@router.message(Command("draft"))
async def cmd_draft(message: Message, api: APIClient = None, **kwargs) -> None:
    """Show drafts awaiting review with full preview."""
    if not api:
        await message.answer("Ошибка подключения. Попробуйте позже.")
        return

    try:
        tasks = await api.list_tasks(task_status="in_review")
    except Exception:
        logger.exception("Failed to fetch draft tasks")
        await message.answer("Не удалось загрузить драфты.")
        return

    if not tasks:
        await message.answer(
            "<b>Нет драфтов для просмотра.</b>\n\n"
            "Используйте /plan → генерация драфтов для создания контента."
        )
        return

    # Show first draft in detail
    task = tasks[0]
    body = task.get("body") or "(пустой драфт)"
    body_preview = body[:800] + ("..." if len(body) > 800 else "")

    builder = InlineKeyboardBuilder()
    tid = task["id"][:8]
    builder.button(text="✅ Утвердить", callback_data=f"approve_{tid}")
    builder.button(text="🔄 Перегенерировать", callback_data=f"regen_{tid}")
    builder.button(text="❌ Отклонить", callback_data=f"reject_{tid}")
    if len(tasks) > 1:
        builder.button(text=f"⏭ Следующий ({len(tasks) - 1} ещё)", callback_data="draft_next_0")
    builder.adjust(2)

    await message.answer(
        f"<b>Драфт #{1}/{len(tasks)}</b>\n\n"
        f"<b>{task['title']}</b> [{task.get('platform', '')}]\n"
        f"Тип: {task.get('content_type', 'text')}\n\n"
        f"<pre>{body_preview}</pre>",
        reply_markup=builder.as_markup(),
    )


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
        body_preview = (task.get("body") or "")[:80]
        lines.append(
            f"• <b>{task['title']}</b> [{task.get('platform', '')}]\n"
            f"  {body_preview}{'...' if len(body_preview) == 80 else ''}"
        )
        tid = task["id"][:8]
        builder.button(text=f"✅ {task['title'][:25]}", callback_data=f"approve_{tid}")
        builder.button(text=f"👁 Превью", callback_data=f"preview_{tid}")

    builder.adjust(2)
    await message.answer("\n".join(lines), reply_markup=builder.as_markup())


@router.callback_query(lambda c: c.data and c.data.startswith("preview_"))
async def cb_preview_task(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    """Show full preview of a task's content."""
    prefix = callback.data.replace("preview_", "")

    if not api:
        await callback.answer("Ошибка")
        return

    try:
        tasks = await api.list_tasks()
        target = next((t for t in tasks if t["id"].startswith(prefix)), None)
        if not target:
            await callback.message.answer("Задача не найдена.")
            await callback.answer()
            return

        body = target.get("body") or "(нет контента)"
        body_preview = body[:1500] + ("..." if len(body) > 1500 else "")

        builder = InlineKeyboardBuilder()
        tid = target["id"][:8]
        builder.button(text="✅ Утвердить", callback_data=f"approve_{tid}")
        builder.button(text="🔄 Перегенерировать", callback_data=f"regen_{tid}")
        builder.button(text="❌ Отклонить", callback_data=f"reject_{tid}")
        builder.adjust(3)

        await callback.message.answer(
            f"<b>{target['title']}</b> [{target.get('platform', '')}]\n"
            f"Статус: {STATUS_LABELS.get(target.get('status', ''), target.get('status', ''))}\n\n"
            f"<pre>{body_preview}</pre>",
            reply_markup=builder.as_markup(),
        )
    except Exception:
        logger.exception("Failed to preview task")
        await callback.message.answer("Ошибка при загрузке превью.")
    await callback.answer()


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

            builder = InlineKeyboardBuilder()
            builder.button(text="📢 Опубликовать", callback_data=f"pub_{target['id'][:8]}")
            builder.adjust(1)

            await callback.message.answer(
                f"✅ Задача <b>{target['title']}</b> утверждена!\n\n"
                "Можете опубликовать сейчас или задача будет опубликована по расписанию.",
                reply_markup=builder.as_markup(),
            )
        else:
            await callback.message.answer("Задача не найдена или уже утверждена.")
    except Exception:
        logger.exception("Failed to approve task")
        await callback.message.answer("Ошибка при утверждении задачи.")
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("reject_"))
async def cb_reject_task(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    prefix = callback.data.replace("reject_", "")

    if not api:
        await callback.answer("Ошибка")
        return

    try:
        tasks = await api.list_tasks()
        target = next((t for t in tasks if t["id"].startswith(prefix)), None)
        if target:
            await api.reject_task(target["id"])
            await callback.message.answer(
                f"↩️ Задача <b>{target['title']}</b> отклонена и возвращена в черновик."
            )
        else:
            await callback.message.answer("Задача не найдена.")
    except Exception:
        logger.exception("Failed to reject task")
        await callback.message.answer("Ошибка при отклонении задачи.")
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("regen_"))
async def cb_regenerate_draft(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    """Regenerate a draft with AI."""
    prefix = callback.data.replace("regen_", "")

    if not api:
        await callback.answer("Ошибка")
        return

    await callback.message.answer("🔄 <b>Перегенерирую драфт...</b>")

    try:
        tasks = await api.list_tasks()
        target = next((t for t in tasks if t["id"].startswith(prefix)), None)
        if not target:
            await callback.message.answer("Задача не найдена.")
            await callback.answer()
            return

        result = await api.regenerate_draft(target["id"])
        body_preview = result.get("body_preview", "")[:500]

        builder = InlineKeyboardBuilder()
        tid = target["id"][:8]
        builder.button(text="✅ Утвердить", callback_data=f"approve_{tid}")
        builder.button(text="🔄 Ещё раз", callback_data=f"regen_{tid}")
        builder.adjust(2)

        await callback.message.answer(
            f"<b>Новый драфт для «{target['title']}»:</b>\n\n"
            f"<pre>{body_preview}{'...' if len(body_preview) == 500 else ''}</pre>",
            reply_markup=builder.as_markup(),
        )
    except Exception:
        logger.exception("Failed to regenerate draft")
        await callback.message.answer("Ошибка при перегенерации.")
    await callback.answer()


@router.callback_query(lambda c: c.data == "gen_pending")
async def cb_generate_pending(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    """Generate drafts for all pending tasks (picks the latest plan)."""
    if not api:
        await callback.answer("Ошибка")
        return

    await callback.message.answer("⏳ <b>Генерирую драфты для ожидающих задач...</b>")

    try:
        tasks = await api.list_tasks(task_status="pending")
        if not tasks:
            await callback.message.answer("Нет ожидающих задач.")
            await callback.answer()
            return

        generated = 0
        for task in tasks[:10]:
            try:
                await api.generate_draft(task["id"])
                generated += 1
            except Exception:
                logger.warning("Failed to generate draft for task %s", task["id"])

        await callback.message.answer(
            f"<b>Готово!</b> Сгенерировано {generated} из {len(tasks)} драфтов.\n\n"
            "Используйте /approve для ревью."
        )
    except Exception:
        logger.exception("Failed to generate pending drafts")
        await callback.message.answer("Ошибка при генерации.")
    await callback.answer()


# ── Publishing ───────────────────────────────────────────────────────────────


@router.callback_query(lambda c: c.data and c.data.startswith("pub_"))
async def cb_publish_task(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    """Publish an approved task immediately."""
    prefix = callback.data.replace("pub_", "")

    if not api:
        await callback.answer("Ошибка")
        return

    try:
        tasks = await api.list_tasks(task_status="approved")
        target = next((t for t in tasks if t["id"].startswith(prefix)), None)
        if not target:
            await callback.message.answer("Задача не найдена или уже опубликована.")
            await callback.answer()
            return

        await callback.message.answer(f"📤 Публикую <b>{target['title']}</b>...")

        result = await api.publish_task(target["id"])
        url = result.get("published_url", "")
        msg = result.get("message", "")

        if url:
            await callback.message.answer(
                f"📢 <b>Опубликовано!</b>\n\n"
                f"{target['title']}\n"
                f"Ссылка: {url}"
            )
        else:
            await callback.message.answer(
                f"📢 <b>Результат публикации:</b>\n{msg}"
            )
    except Exception as e:
        error_text = str(e)
        if "403" in error_text:
            await callback.message.answer(
                "Автопубликация доступна начиная с тарифа Autopilot.\n\n"
                "Используйте /billing для апгрейда."
            )
        else:
            logger.exception("Failed to publish task")
            await callback.message.answer("Ошибка при публикации.")
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
    builder = InlineKeyboardBuilder()

    for i, task in enumerate(tasks[:10], 1):
        scheduled = task.get("scheduled_at", "не запланировано")
        if isinstance(scheduled, str) and len(scheduled) > 10:
            scheduled = scheduled[:16].replace("T", " ")
        lines.append(
            f"{i}. <b>{task['title']}</b> [{task.get('platform', '')}]\n"
            f"   Запланировано: {scheduled}"
        )
        builder.button(
            text=f"📢 {task['title'][:20]}",
            callback_data=f"pub_{task['id'][:8]}",
        )

    builder.adjust(1)
    await message.answer("\n".join(lines), reply_markup=builder.as_markup())


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
