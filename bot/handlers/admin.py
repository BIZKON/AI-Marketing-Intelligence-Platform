"""Admin handlers — platform stats, user management via Telegram."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.api_client import APIClient

logger = logging.getLogger(__name__)

router = Router()


def _is_admin(user_data: dict | None) -> bool:
    """Check if current user is a superuser."""
    return bool(user_data and user_data.get("is_superuser"))


# ── Platform Stats ────────────────────────────────────────────────────────────


@router.message(Command("admin"))
async def cmd_admin(message: Message, api: APIClient = None, user_data: dict = None, **kwargs) -> None:
    """Show admin panel with quick actions."""
    if not _is_admin(user_data):
        await message.answer("Доступ запрещён. Требуются права администратора.")
        return

    text = (
        "<b>Панель администратора</b>\n\n"
        "Используйте кнопки ниже или команды:\n\n"
        "/stats — статистика платформы\n"
        "/users — список пользователей\n"
        "/syshealth — состояние сервисов"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="Статистика", callback_data="adm_stats")
    builder.button(text="Пользователи", callback_data="adm_users")
    builder.button(text="Здоровье системы", callback_data="adm_health")
    builder.adjust(2, 1)

    await message.answer(text, reply_markup=builder.as_markup())


@router.message(Command("stats"))
async def cmd_stats(message: Message, api: APIClient = None, user_data: dict = None, **kwargs) -> None:
    """Show platform statistics."""
    if not _is_admin(user_data):
        await message.answer("Доступ запрещён.")
        return

    await _send_stats(message, api)


@router.callback_query(lambda c: c.data == "adm_stats")
async def cb_stats(callback: CallbackQuery, api: APIClient = None, user_data: dict = None, **kwargs) -> None:
    if not _is_admin(user_data):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    await _send_stats(callback.message, api)
    await callback.answer()


async def _send_stats(message: Message, api: APIClient | None) -> None:
    if not api:
        await message.answer("API недоступен.")
        return

    try:
        stats = await api.admin_stats()
    except Exception as e:
        logger.exception("Failed to fetch admin stats")
        await message.answer(f"Ошибка загрузки статистики: {e}")
        return

    users = stats.get("users", {})
    subs = stats.get("subscriptions", {})
    data = stats.get("data", {})
    activity = stats.get("activity_24h", {})

    plan_dist = subs.get("plan_distribution", {})
    plan_lines = []
    for plan, count in plan_dist.items():
        plan_lines.append(f"  {plan}: {count}")

    text = (
        "<b>Статистика платформы</b>\n\n"
        f"<b>Пользователи:</b> {users.get('total', 0)} всего, "
        f"{users.get('active', 0)} активных\n\n"
        f"<b>Подписки:</b> {subs.get('active', 0)} активных\n"
        + ("\n".join(plan_lines) + "\n" if plan_lines else "")
        + f"\n<b>Данные:</b>\n"
        f"  Конкуренты: {data.get('competitors', 0)}\n"
        f"  Посты: {data.get('posts', 0)}\n"
        f"  Отчёты: {data.get('reports', 0)}\n"
        f"  Контент-задачи: {data.get('content_tasks', 0)}\n"
        f"\n<b>Активность (24ч):</b>\n"
        f"  Новые посты: {activity.get('new_posts', 0)}\n"
        f"  Новые отчёты: {activity.get('new_reports', 0)}\n"
        f"  Новые задачи: {activity.get('new_tasks', 0)}"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="Обновить", callback_data="adm_stats")
    builder.button(text="Назад", callback_data="adm_back")
    builder.adjust(2)

    await message.answer(text, reply_markup=builder.as_markup())


# ── User Management ──────────────────────────────────────────────────────────


@router.message(Command("users"))
async def cmd_users(message: Message, api: APIClient = None, user_data: dict = None, **kwargs) -> None:
    """List platform users."""
    if not _is_admin(user_data):
        await message.answer("Доступ запрещён.")
        return

    await _send_users_list(message, api)


@router.callback_query(lambda c: c.data == "adm_users")
async def cb_users(callback: CallbackQuery, api: APIClient = None, user_data: dict = None, **kwargs) -> None:
    if not _is_admin(user_data):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    await _send_users_list(callback.message, api)
    await callback.answer()


async def _send_users_list(message: Message, api: APIClient | None, offset: int = 0) -> None:
    if not api:
        await message.answer("API недоступен.")
        return

    try:
        users = await api.admin_list_users(limit=10, offset=offset)
    except Exception as e:
        logger.exception("Failed to fetch users")
        await message.answer(f"Ошибка загрузки пользователей: {e}")
        return

    if not users:
        await message.answer("Пользователи не найдены.")
        return

    lines = ["<b>Пользователи платформы</b>\n"]
    builder = InlineKeyboardBuilder()

    for u in users:
        status_icon = "✅" if u.get("is_active") else "❌"
        admin_icon = " 👑" if u.get("is_superuser") else ""
        name = u.get("full_name") or u.get("telegram_username") or u.get("email") or "—"
        plan = u.get("plan") or "—"

        lines.append(
            f"{status_icon}{admin_icon} <b>{name}</b>\n"
            f"   План: {plan} | ID: <code>{u['id'][:8]}…</code>"
        )

        builder.button(
            text=f"{name[:20]}",
            callback_data=f"adm_user:{u['id'][:36]}",
        )

    builder.adjust(2)

    # Pagination
    nav = InlineKeyboardBuilder()
    if offset > 0:
        nav.button(text="⬅️ Назад", callback_data=f"adm_users_page:{max(0, offset - 10)}")
    if len(users) == 10:
        nav.button(text="Вперёд ➡️", callback_data=f"adm_users_page:{offset + 10}")
    nav.adjust(2)

    builder.attach(nav)
    builder.button(text="🔙 Админ-панель", callback_data="adm_back")

    await message.answer("\n".join(lines), reply_markup=builder.as_markup())


@router.callback_query(lambda c: c.data and c.data.startswith("adm_users_page:"))
async def cb_users_page(callback: CallbackQuery, api: APIClient = None, user_data: dict = None, **kwargs) -> None:
    if not _is_admin(user_data):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    offset = int(callback.data.split(":")[1])
    await _send_users_list(callback.message, api, offset=offset)
    await callback.answer()


# ── User Detail ──────────────────────────────────────────────────────────────


@router.callback_query(lambda c: c.data and c.data.startswith("adm_user:"))
async def cb_user_detail(callback: CallbackQuery, api: APIClient = None, user_data: dict = None, **kwargs) -> None:
    if not _is_admin(user_data):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    user_id = callback.data.split(":")[1]

    if not api:
        await callback.message.answer("API недоступен.")
        await callback.answer()
        return

    try:
        user = await api.admin_get_user(user_id)
    except Exception as e:
        logger.exception("Failed to fetch user detail")
        await callback.message.answer(f"Ошибка: {e}")
        await callback.answer()
        return

    usage = user.get("usage", {})
    status_icon = "✅" if user.get("is_active") else "❌"
    admin_icon = "👑 " if user.get("is_superuser") else ""

    text = (
        f"<b>{admin_icon}Пользователь</b>\n\n"
        f"<b>Имя:</b> {user.get('full_name') or '—'}\n"
        f"<b>Email:</b> {user.get('email') or '—'}\n"
        f"<b>Telegram:</b> @{user.get('telegram_username') or '—'}\n"
        f"<b>Статус:</b> {status_icon} {'Активен' if user.get('is_active') else 'Заблокирован'}\n"
        f"<b>План:</b> {user.get('plan') or 'Нет подписки'}\n"
        f"<b>Бренд:</b> {user.get('brand_name') or '—'}\n"
        f"<b>Индустрия:</b> {user.get('brand_industry') or '—'}\n\n"
        f"<b>Использование:</b>\n"
        f"  Конкуренты: {usage.get('competitors', 0)}\n"
        f"  Отчёты: {usage.get('reports', 0)}\n"
        f"  Задачи: {usage.get('content_tasks', 0)}\n\n"
        f"<b>ID:</b> <code>{user.get('id')}</code>\n"
        f"<b>Регистрация:</b> {user.get('created_at', '—')[:10]}"
    )

    builder = InlineKeyboardBuilder()

    # Toggle active status
    if user.get("is_active"):
        builder.button(text="🚫 Заблокировать", callback_data=f"adm_toggle_active:{user['id']}:false")
    else:
        builder.button(text="✅ Разблокировать", callback_data=f"adm_toggle_active:{user['id']}:true")

    # Toggle admin
    if user.get("is_superuser"):
        builder.button(text="👤 Убрать админ", callback_data=f"adm_toggle_admin:{user['id']}:false")
    else:
        builder.button(text="👑 Дать админ", callback_data=f"adm_toggle_admin:{user['id']}:true")

    # Plan change buttons
    builder.button(text="📋 Изменить план", callback_data=f"adm_plan_pick:{user['id']}")
    builder.button(text="🔙 К списку", callback_data="adm_users")
    builder.adjust(2, 1, 1)

    await callback.message.answer(text, reply_markup=builder.as_markup())
    await callback.answer()


# ── Toggle Active / Admin ────────────────────────────────────────────────────


@router.callback_query(lambda c: c.data and c.data.startswith("adm_toggle_active:"))
async def cb_toggle_active(callback: CallbackQuery, api: APIClient = None, user_data: dict = None, **kwargs) -> None:
    if not _is_admin(user_data):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    parts = callback.data.split(":")
    user_id = parts[1]
    new_state = parts[2] == "true"

    try:
        result = await api.admin_update_user(user_id, is_active=new_state)
        status = "активирован" if new_state else "заблокирован"
        await callback.message.answer(f"Пользователь {status}.")
    except Exception as e:
        await callback.message.answer(f"Ошибка: {e}")

    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("adm_toggle_admin:"))
async def cb_toggle_admin(callback: CallbackQuery, api: APIClient = None, user_data: dict = None, **kwargs) -> None:
    if not _is_admin(user_data):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    parts = callback.data.split(":")
    user_id = parts[1]
    new_state = parts[2] == "true"

    try:
        result = await api.admin_update_user(user_id, is_superuser=new_state)
        status = "назначен администратором" if new_state else "лишён прав администратора"
        await callback.message.answer(f"Пользователь {status}.")
    except Exception as e:
        await callback.message.answer(f"Ошибка: {e}")

    await callback.answer()


# ── Plan Change ──────────────────────────────────────────────────────────────


@router.callback_query(lambda c: c.data and c.data.startswith("adm_plan_pick:"))
async def cb_plan_pick(callback: CallbackQuery, api: APIClient = None, user_data: dict = None, **kwargs) -> None:
    if not _is_admin(user_data):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    user_id = callback.data.split(":")[1]

    builder = InlineKeyboardBuilder()
    for plan in ("monitor", "creator", "autopilot", "enterprise"):
        builder.button(text=plan.capitalize(), callback_data=f"adm_set_plan:{user_id}:{plan}")
    builder.button(text="Отмена", callback_data=f"adm_user:{user_id}")
    builder.adjust(2, 2, 1)

    await callback.message.answer(
        "Выберите новый тарифный план:",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("adm_set_plan:"))
async def cb_set_plan(callback: CallbackQuery, api: APIClient = None, user_data: dict = None, **kwargs) -> None:
    if not _is_admin(user_data):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    parts = callback.data.split(":")
    user_id = parts[1]
    plan = parts[2]

    try:
        result = await api.admin_change_plan(user_id, plan)
        await callback.message.answer(
            f"План пользователя изменён на <b>{plan.capitalize()}</b>.",
        )
    except Exception as e:
        await callback.message.answer(f"Ошибка: {e}")

    await callback.answer()


# ── System Health ────────────────────────────────────────────────────────────


@router.message(Command("syshealth"))
async def cmd_syshealth(message: Message, api: APIClient = None, user_data: dict = None, **kwargs) -> None:
    """Show system health status."""
    if not _is_admin(user_data):
        await message.answer("Доступ запрещён.")
        return

    await _send_health(message, api)


@router.callback_query(lambda c: c.data == "adm_health")
async def cb_health(callback: CallbackQuery, api: APIClient = None, user_data: dict = None, **kwargs) -> None:
    if not _is_admin(user_data):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    await _send_health(callback.message, api)
    await callback.answer()


async def _send_health(message: Message, api: APIClient | None) -> None:
    if not api:
        await message.answer("API недоступен.")
        return

    try:
        health = await api.admin_health()
    except Exception as e:
        logger.exception("Failed to fetch health")
        await message.answer(f"Ошибка проверки здоровья: {e}")
        return

    overall = health.get("status", "unknown")
    overall_icon = "✅" if overall == "ok" else "⚠️"

    lines = [f"<b>{overall_icon} Состояние системы: {overall.upper()}</b>\n"]

    checks = health.get("checks", {})
    for service, result in checks.items():
        s = result.get("status", "unknown")
        icon = "✅" if s == "ok" else "❌"
        latency = result.get("latency_ms", "?")
        error = result.get("error")

        line = f"{icon} <b>{service}:</b> {s} ({latency}ms)"
        if error:
            line += f"\n   <i>{error[:100]}</i>"
        lines.append(line)

    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Обновить", callback_data="adm_health")
    builder.button(text="🔙 Админ-панель", callback_data="adm_back")
    builder.adjust(2)

    await message.answer("\n".join(lines), reply_markup=builder.as_markup())


# ── Navigation ───────────────────────────────────────────────────────────────


@router.callback_query(lambda c: c.data == "adm_back")
async def cb_admin_back(callback: CallbackQuery, api: APIClient = None, user_data: dict = None, **kwargs) -> None:
    """Return to admin panel."""
    if not _is_admin(user_data):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    text = (
        "<b>Панель администратора</b>\n\n"
        "/stats — статистика\n"
        "/users — пользователи\n"
        "/syshealth — состояние сервисов"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="Статистика", callback_data="adm_stats")
    builder.button(text="Пользователи", callback_data="adm_users")
    builder.button(text="Здоровье системы", callback_data="adm_health")
    builder.adjust(2, 1)

    await callback.message.answer(text, reply_markup=builder.as_markup())
    await callback.answer()
