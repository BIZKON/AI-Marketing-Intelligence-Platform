"""Telegram Data Export handler: connect account, manage sources, export, search, analytics.

Commands:
  /connect        — Connect Telegram account via Telethon (API ID + Hash + Phone + Code)
  /sources        — Manage export sources (add / list / delete)
  /export         — Start data export from a Telegram source
  /export_status  — Show active/recent export jobs
  /search <query> — Semantic search across exported messages
  /popular        — Show popular posts from exported data
  /authors        — Show top authors from exported data
  /activity       — Show activity stats from exported data
"""

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.api_client import APIClient
from bot.states.export import ConnectTelegramStates, ExportStates, SearchStates

logger = logging.getLogger(__name__)
router = Router()

# ── Plan limits ───────────────────────────────────────────────────────────────

PLAN_ORDER = {"monitor": 0, "creator": 1, "autopilot": 2, "enterprise": 3}

PLAN_LIMITS = {
    "monitor": {"sources": 3, "export_per_week": 1, "search_per_day": 10, "full_analytics": False},
    "creator": {"sources": 7, "export_per_week": 7, "search_per_day": 50, "full_analytics": True},
    "autopilot": {"sources": 999, "export_per_week": 999, "search_per_day": 999, "full_analytics": True},
    "enterprise": {"sources": 999, "export_per_week": 999, "search_per_day": 999, "full_analytics": True},
}

SOURCE_TYPE_LABELS = {
    "channel": "Канал",
    "group": "Группа",
    "chat": "Чат",
    "folder": "Папка",
}

JOB_STATUS_ICONS = {
    "pending": "⏳",
    "processing": "🔄",
    "chunking": "🔄",
    "embedding": "🔄",
    "completed": "✅",
    "failed": "❌",
    "cancelled": "🚫",
}


def _get_limits(user_plan: str) -> dict:
    return PLAN_LIMITS.get(user_plan, PLAN_LIMITS["monitor"])


# ── /connect — Start Telegram account connection ─────────────────────────────


@router.message(Command("connect"))
async def cmd_connect(message: Message, state: FSMContext, **kwargs) -> None:
    """Start the Telegram account connection flow."""
    await state.set_state(ConnectTelegramStates.waiting_api_id)
    await message.answer(
        "<b>Подключение Telegram-аккаунта</b>\n\n"
        "Для экспорта данных из каналов/групп нужно подключить ваш Telegram-аккаунт "
        "через Telethon API.\n\n"
        "1. Перейдите на <a href='https://my.telegram.org/apps'>my.telegram.org/apps</a>\n"
        "2. Создайте приложение (или используйте существующее)\n\n"
        "Введите ваш <b>API ID</b> (числовой):",
        disable_web_page_preview=True,
    )


@router.message(ConnectTelegramStates.waiting_api_id)
async def process_api_id(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("API ID должен быть числом. Попробуйте ещё раз:")
        return

    await state.update_data(api_id=int(raw))
    await state.set_state(ConnectTelegramStates.waiting_api_hash)
    await message.answer("Введите ваш <b>API Hash</b> (строка из 32 символов):")


@router.message(ConnectTelegramStates.waiting_api_hash)
async def process_api_hash(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw or len(raw) < 20:
        await message.answer("API Hash выглядит некорректно. Проверьте и введите снова:")
        return

    await state.update_data(api_hash=raw)
    await state.set_state(ConnectTelegramStates.waiting_phone)
    await message.answer(
        "Введите номер телефона вашего Telegram-аккаунта "
        "(в международном формате, например <code>+79001234567</code>):"
    )


@router.message(ConnectTelegramStates.waiting_phone)
async def process_phone(
    message: Message, state: FSMContext, api: APIClient = None, **kwargs
) -> None:
    raw = (message.text or "").strip()
    if not raw.startswith("+") or len(raw) < 10:
        await message.answer("Номер должен начинаться с + и содержать минимум 10 цифр:")
        return

    if not api:
        await message.answer("Ошибка подключения к серверу. Попробуйте позже.")
        await state.clear()
        return

    data = await state.get_data()
    api_id = data["api_id"]
    api_hash = data["api_hash"]

    await message.answer("Подключение к Telegram...")

    try:
        result = await api.export_connect(api_id=api_id, api_hash=api_hash, phone=raw)
        session_id = result["session_id"]
        await state.update_data(session_id=session_id, phone=raw)
        await state.set_state(ConnectTelegramStates.waiting_code)
        await message.answer(
            "Telegram отправил код подтверждения в ваше приложение.\n\n"
            "Введите <b>код подтверждения</b>:"
        )
    except Exception as e:
        error_text = str(e)
        if "400" in error_text:
            await message.answer("Неверные API ID/Hash или номер телефона. Начните заново: /connect")
        else:
            logger.exception("Failed to initiate Telegram connection")
            await message.answer("Ошибка при подключении. Попробуйте позже.")
        await state.clear()


@router.message(ConnectTelegramStates.waiting_code)
async def process_code(
    message: Message, state: FSMContext, api: APIClient = None, **kwargs
) -> None:
    raw = (message.text or "").strip().replace(" ", "").replace("-", "")
    if not raw or len(raw) < 4:
        await message.answer("Введите код, который пришёл вам в Telegram:")
        return

    if not api:
        await message.answer("Ошибка подключения к серверу.")
        await state.clear()
        return

    data = await state.get_data()
    session_id = data.get("session_id")

    try:
        result = await api.export_verify(session_id=session_id, code=raw)

        if result.get("requires_2fa"):
            await state.set_state(ConnectTelegramStates.waiting_2fa_password)
            await message.answer(
                "У вашего аккаунта включена двухфакторная аутентификация.\n\n"
                "Введите <b>пароль 2FA</b>:"
            )
            return

        await state.clear()
        await message.answer(
            "<b>Telegram-аккаунт успешно подключён!</b>\n\n"
            "Теперь вы можете:\n"
            "• /sources — управлять источниками для экспорта\n"
            "• /export — запустить экспорт данных\n"
            "• /search — искать по экспортированным данным"
        )
    except Exception as e:
        error_text = str(e)
        if "400" in error_text:
            await message.answer("Неверный код. Попробуйте ввести ещё раз:")
        else:
            logger.exception("Failed to verify Telegram code")
            await message.answer("Ошибка верификации. Начните заново: /connect")
            await state.clear()


@router.message(ConnectTelegramStates.waiting_2fa_password)
async def process_2fa_password(
    message: Message, state: FSMContext, api: APIClient = None, **kwargs
) -> None:
    raw = (message.text or "").strip()
    if not raw:
        await message.answer("Введите пароль 2FA:")
        return

    if not api:
        await message.answer("Ошибка подключения к серверу.")
        await state.clear()
        return

    data = await state.get_data()
    session_id = data.get("session_id")

    try:
        await api.export_verify(session_id=session_id, code="", password_2fa=raw)
        await state.clear()
        await message.answer(
            "<b>Telegram-аккаунт успешно подключён!</b>\n\n"
            "Теперь вы можете:\n"
            "• /sources — управлять источниками для экспорта\n"
            "• /export — запустить экспорт данных\n"
            "• /search — искать по экспортированным данным"
        )
    except Exception as e:
        error_text = str(e)
        if "400" in error_text:
            await message.answer("Неверный пароль 2FA. Попробуйте ещё раз:")
        else:
            logger.exception("Failed to verify 2FA password")
            await message.answer("Ошибка верификации. Начните заново: /connect")
            await state.clear()


# ── /sources — Manage export sources ─────────────────────────────────────────


@router.message(Command("sources"))
async def cmd_sources(message: Message, **kwargs) -> None:
    builder = InlineKeyboardBuilder()
    builder.button(text="Добавить источник", callback_data="sources_add")
    builder.button(text="Список источников", callback_data="sources_list")
    builder.adjust(2)

    await message.answer(
        "<b>Управление источниками экспорта</b>\n\n"
        "Добавляйте Telegram-каналы, группы и чаты для экспорта данных.",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(lambda c: c.data == "sources_add")
async def cb_sources_add(
    callback: CallbackQuery, state: FSMContext, user_plan: str = "monitor", **kwargs
) -> None:
    limits = _get_limits(user_plan)

    # Check source limit before adding
    api: APIClient | None = kwargs.get("api")
    if api:
        try:
            existing = await api.export_list_sources()
            if len(existing) >= limits["sources"]:
                await callback.message.answer(
                    f"Достигнут лимит источников для вашего тарифа "
                    f"({limits['sources']} шт.).\n\n"
                    "Используйте /billing для апгрейда."
                )
                await callback.answer()
                return
        except Exception:
            logger.exception("Failed to check source limit")

    # Show type selection
    builder = InlineKeyboardBuilder()
    builder.button(text="Канал", callback_data="sources_add_type_channel")
    builder.button(text="Группа", callback_data="sources_add_type_group")
    builder.button(text="Чат", callback_data="sources_add_type_chat")
    builder.button(text="Папка", callback_data="sources_add_type_folder")
    builder.adjust(2, 2)

    await state.set_state(ExportStates.selecting_type)
    await callback.message.answer(
        "Выберите тип источника:",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(
    ExportStates.selecting_type,
    lambda c: c.data and c.data.startswith("sources_add_type_"),
)
async def cb_sources_add_type(callback: CallbackQuery, state: FSMContext, **kwargs) -> None:
    source_type = callback.data.replace("sources_add_type_", "")
    await state.update_data(source_type=source_type)
    await state.set_state(ExportStates.selecting_source)

    if source_type == "folder":
        # Try to list folders from connected account
        api: APIClient | None = kwargs.get("api")
        if api:
            try:
                folders = await api.export_list_folders()
                if folders:
                    builder = InlineKeyboardBuilder()
                    for folder in folders:
                        label = folder.get("title", "Папка")
                        folder_id = folder.get("id", "")
                        builder.button(
                            text=label,
                            callback_data=f"sources_folder_{str(folder_id)[:8]}",
                        )
                    builder.adjust(1)

                    await state.update_data(
                        folder_map={str(f["id"])[:8]: f for f in folders}
                    )
                    await state.set_state(ExportStates.selecting_folder)
                    await callback.message.answer(
                        "Выберите папку:",
                        reply_markup=builder.as_markup(),
                    )
                    await callback.answer()
                    return
            except Exception:
                logger.exception("Failed to list folders")

        await callback.message.answer(
            "Не удалось загрузить папки. Убедитесь, что аккаунт подключён (/connect)."
        )
        await state.clear()
        await callback.answer()
        return

    type_label = SOURCE_TYPE_LABELS.get(source_type, source_type)
    await callback.message.answer(
        f"Введите @username или числовой ID {type_label.lower()}а:"
    )
    await callback.answer()


@router.callback_query(
    ExportStates.selecting_folder,
    lambda c: c.data and c.data.startswith("sources_folder_"),
)
async def cb_sources_folder_select(
    callback: CallbackQuery, state: FSMContext, api: APIClient = None, **kwargs
) -> None:
    prefix = callback.data.replace("sources_folder_", "")
    data = await state.get_data()
    folder_map = data.get("folder_map", {})
    folder = folder_map.get(prefix)

    if not folder:
        await callback.answer("Папка не найдена")
        await state.clear()
        return

    if not api:
        await callback.message.answer("Ошибка подключения к серверу.")
        await state.clear()
        await callback.answer()
        return

    try:
        result = await api.export_add_source(
            telegram_id_or_username=str(folder["id"]),
            source_type="folder",
        )
        await state.clear()
        await callback.message.answer(
            f"<b>Источник добавлен!</b>\n\n"
            f"Папка: {result.get('title', folder.get('title', ''))}\n"
            f"Тип: Папка"
        )
    except Exception as e:
        error_text = str(e)
        if "403" in error_text:
            await callback.message.answer(
                "Достигнут лимит источников для вашего тарифа.\n\n"
                "Используйте /billing для апгрейда."
            )
        elif "409" in error_text:
            await callback.message.answer("Этот источник уже добавлен.")
        else:
            logger.exception("Failed to add folder source")
            await callback.message.answer("Ошибка при добавлении. Попробуйте позже.")
        await state.clear()
    await callback.answer()


@router.message(ExportStates.selecting_source)
async def process_source_username(
    message: Message, state: FSMContext, api: APIClient = None, **kwargs
) -> None:
    raw = (message.text or "").strip().lstrip("@")
    if not raw or len(raw) < 2:
        await message.answer("Введите корректный @username или числовой ID:")
        return

    if not api:
        await message.answer("Ошибка подключения к серверу.")
        await state.clear()
        return

    data = await state.get_data()
    source_type = data.get("source_type", "channel")

    try:
        result = await api.export_add_source(
            telegram_id_or_username=raw,
            source_type=source_type,
        )
        await state.clear()

        type_label = SOURCE_TYPE_LABELS.get(source_type, source_type)
        title = result.get("title", raw)
        username = result.get("username")
        username_str = f" (@{username})" if username else ""

        await message.answer(
            f"<b>Источник добавлен!</b>\n\n"
            f"Название: {title}{username_str}\n"
            f"Тип: {type_label}"
        )
    except Exception as e:
        error_text = str(e)
        if "403" in error_text:
            await message.answer(
                "Достигнут лимит источников для вашего тарифа.\n\n"
                "Используйте /billing для апгрейда."
            )
        elif "404" in error_text:
            await message.answer(
                "Источник не найден. Проверьте @username или ID и попробуйте снова:"
            )
            return
        elif "409" in error_text:
            await message.answer("Этот источник уже добавлен.")
            await state.clear()
        else:
            logger.exception("Failed to add export source")
            await message.answer("Ошибка при добавлении. Попробуйте позже.")
            await state.clear()


@router.callback_query(lambda c: c.data == "sources_list")
async def cb_sources_list(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    if not api:
        await callback.message.answer("Ошибка загрузки. Попробуйте позже.")
        await callback.answer()
        return

    try:
        sources = await api.export_list_sources()
    except Exception:
        logger.exception("Failed to list export sources")
        await callback.message.answer("Не удалось загрузить список источников.")
        await callback.answer()
        return

    if not sources:
        await callback.message.answer(
            "У вас пока нет источников для экспорта.\n\n"
            "Используйте /sources → «Добавить источник» чтобы начать."
        )
        await callback.answer()
        return

    lines = ["<b>Источники экспорта:</b>\n"]
    for i, src in enumerate(sources, 1):
        type_label = SOURCE_TYPE_LABELS.get(src.get("telegram_type", ""), "?")
        title = src.get("title", "—")
        username = src.get("username")
        username_str = f" @{username}" if username else ""
        total = src.get("total_messages", 0)
        lines.append(f"{i}. <b>{title}</b>{username_str}")
        lines.append(f"   Тип: {type_label} | Сообщений: {total}")

    builder = InlineKeyboardBuilder()
    builder.button(text="Добавить ещё", callback_data="sources_add")

    for src in sources[:5]:
        src_id = str(src["id"])[:8]
        name = src.get("title", "?")[:20]
        builder.button(text=f"🗑 {name}", callback_data=f"sources_delete_{src_id}")
    builder.adjust(1)

    await callback.message.answer("\n".join(lines), reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("sources_delete_"))
async def cb_sources_delete(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    if not api:
        await callback.answer("Ошибка")
        return

    prefix = callback.data.replace("sources_delete_", "")
    try:
        sources = await api.export_list_sources()
        target = next((s for s in sources if str(s["id"]).startswith(prefix)), None)
        if target:
            await api.export_delete_source(target["id"])
            await callback.message.answer(f"Источник <b>{target['title']}</b> удалён.")
        else:
            await callback.message.answer("Источник не найден.")
    except Exception:
        logger.exception("Failed to delete export source")
        await callback.message.answer("Ошибка при удалении.")
    await callback.answer()


# ── /export — Start data export ──────────────────────────────────────────────


@router.message(Command("export"))
async def cmd_export(
    message: Message, state: FSMContext, api: APIClient = None,
    user_plan: str = "monitor", **kwargs,
) -> None:
    if not api:
        await message.answer("Ошибка подключения к серверу.")
        return

    # Show export type selection
    builder = InlineKeyboardBuilder()
    builder.button(text="Канал", callback_data="export_type_channel")
    builder.button(text="Группа", callback_data="export_type_group")
    builder.button(text="Чат", callback_data="export_type_chat")
    builder.button(text="Папка", callback_data="export_type_folder")
    builder.adjust(2, 2)

    limits = _get_limits(user_plan)
    freq = "1 раз/нед." if user_plan == "monitor" else "1 раз/день" if user_plan == "creator" else "без ограничений"

    await state.set_state(ExportStates.selecting_type)
    await state.update_data(user_plan=user_plan)
    await message.answer(
        "<b>Экспорт данных из Telegram</b>\n\n"
        f"Ваш тариф: <b>{user_plan.capitalize()}</b>\n"
        f"Частота экспорта: {freq}\n\n"
        "Выберите тип источника для экспорта:",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(
    ExportStates.selecting_type,
    lambda c: c.data and c.data.startswith("export_type_"),
)
async def cb_export_type(
    callback: CallbackQuery, state: FSMContext, api: APIClient = None, **kwargs
) -> None:
    export_type = callback.data.replace("export_type_", "")
    await state.update_data(export_type=export_type)

    if not api:
        await callback.answer("Ошибка")
        await state.clear()
        return

    try:
        sources = await api.export_list_sources()
    except Exception:
        logger.exception("Failed to list sources for export")
        await callback.message.answer("Не удалось загрузить источники.")
        await state.clear()
        await callback.answer()
        return

    # Filter sources by selected type
    filtered = [s for s in sources if s.get("telegram_type") == export_type]

    if not filtered:
        type_label = SOURCE_TYPE_LABELS.get(export_type, export_type)
        await callback.message.answer(
            f"У вас нет добавленных источников типа «{type_label}».\n\n"
            "Сначала добавьте источник через /sources."
        )
        await state.clear()
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    source_map = {}
    for src in filtered:
        src_prefix = str(src["id"])[:8]
        source_map[src_prefix] = src
        title = src.get("title", "?")[:30]
        username = src.get("username")
        label = f"{title}" + (f" @{username}" if username else "")
        builder.button(text=label, callback_data=f"export_source_{src_prefix}")
    builder.adjust(1)

    await state.update_data(source_map={k: v for k, v in source_map.items()})
    await state.set_state(ExportStates.selecting_source)

    await callback.message.answer(
        "Выберите источник для экспорта:",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(
    ExportStates.selecting_source,
    lambda c: c.data and c.data.startswith("export_source_"),
)
async def cb_export_source(
    callback: CallbackQuery, state: FSMContext, api: APIClient = None, **kwargs
) -> None:
    prefix = callback.data.replace("export_source_", "")
    data = await state.get_data()
    source_map = data.get("source_map", {})
    source = source_map.get(prefix)

    if not source:
        await callback.answer("Источник не найден")
        await state.clear()
        return

    if not api:
        await callback.answer("Ошибка")
        await state.clear()
        return

    await state.update_data(selected_source=source)
    await state.set_state(ExportStates.confirming)

    title = source.get("title", "?")
    username = source.get("username")
    username_str = f" (@{username})" if username else ""
    source_type = SOURCE_TYPE_LABELS.get(source.get("telegram_type", ""), "?")
    total = source.get("total_messages", 0)
    last_export = source.get("last_export_at")
    last_str = last_export[:10] if last_export else "никогда"

    builder = InlineKeyboardBuilder()
    builder.button(text="Запустить экспорт", callback_data="export_confirm_start")
    builder.button(text="Отмена", callback_data="export_confirm_cancel")
    builder.adjust(2)

    await callback.message.answer(
        f"<b>Подтверждение экспорта</b>\n\n"
        f"Источник: <b>{title}</b>{username_str}\n"
        f"Тип: {source_type}\n"
        f"Экспортировано ранее: {total} сообщений\n"
        f"Последний экспорт: {last_str}\n\n"
        "Будет выполнен инкрементальный экспорт новых сообщений.",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(
    ExportStates.confirming,
    lambda c: c.data == "export_confirm_start",
)
async def cb_export_confirm_start(
    callback: CallbackQuery, state: FSMContext, api: APIClient = None, **kwargs
) -> None:
    if not api:
        await callback.answer("Ошибка")
        await state.clear()
        return

    data = await state.get_data()
    source = data.get("selected_source")
    if not source:
        await callback.answer("Источник не найден")
        await state.clear()
        return

    source_id = source["id"]
    await state.clear()

    try:
        job = await api.export_start(source_id=source_id, config={})
        job_id = job.get("id", "")

        await callback.message.answer(
            "<b>Экспорт запущен!</b>\n\n"
            f"ID задачи: <code>{str(job_id)[:8]}...</code>\n"
            f"Статус: ⏳ В очереди\n\n"
            "Используйте /export_status для проверки прогресса."
        )
    except Exception as e:
        error_text = str(e)
        if "403" in error_text:
            await callback.message.answer(
                "Достигнут лимит экспортов для вашего тарифа.\n\n"
                "Используйте /billing для апгрейда."
            )
        elif "400" in error_text:
            await callback.message.answer(
                "Не удалось запустить экспорт. "
                "Убедитесь, что Telegram-аккаунт подключён (/connect)."
            )
        else:
            logger.exception("Failed to start export")
            await callback.message.answer("Ошибка при запуске экспорта. Попробуйте позже.")
    await callback.answer()


@router.callback_query(
    ExportStates.confirming,
    lambda c: c.data == "export_confirm_cancel",
)
async def cb_export_confirm_cancel(callback: CallbackQuery, state: FSMContext, **kwargs) -> None:
    await state.clear()
    await callback.message.answer("Экспорт отменён.")
    await callback.answer()


# ── /export_status — Show export jobs status ─────────────────────────────────


@router.message(Command("export_status"))
async def cmd_export_status(message: Message, api: APIClient = None, **kwargs) -> None:
    if not api:
        await message.answer("Ошибка подключения к серверу.")
        return

    try:
        jobs = await api.export_list_jobs()
    except Exception:
        logger.exception("Failed to list export jobs")
        await message.answer("Не удалось загрузить список задач.")
        return

    if not jobs:
        await message.answer(
            "У вас нет задач экспорта.\n\n"
            "Используйте /export чтобы запустить первый экспорт."
        )
        return

    lines = ["<b>Задачи экспорта:</b>\n"]
    builder = InlineKeyboardBuilder()

    for job in jobs[:10]:
        job_status = job.get("status", "pending")
        icon = JOB_STATUS_ICONS.get(job_status, "?")
        source_name = job.get("source_name", "?")
        processed = job.get("processed_messages", 0)
        total = job.get("total_messages")
        created = job.get("created_at", "")[:16].replace("T", " ")

        progress_str = ""
        if total and total > 0:
            pct = min(100, int(processed / total * 100))
            progress_str = f" ({pct}%: {processed}/{total})"
        elif processed > 0:
            progress_str = f" ({processed} сообщений)"

        lines.append(f"{icon} <b>{source_name}</b>{progress_str}")
        lines.append(f"   Статус: {job_status} | {created}")

        # Add cancel button for active jobs
        if job_status in ("pending", "processing", "chunking", "embedding"):
            job_prefix = str(job["id"])[:8]
            builder.button(
                text=f"Отменить: {source_name[:20]}",
                callback_data=f"export_cancel_{job_prefix}",
            )

        if job.get("error_message"):
            error = job["error_message"][:80]
            lines.append(f"   Ошибка: {error}")
        lines.append("")

    builder.adjust(1)
    markup = builder.as_markup() if builder.export() else None
    await message.answer("\n".join(lines), reply_markup=markup)


@router.callback_query(lambda c: c.data and c.data.startswith("export_cancel_"))
async def cb_export_cancel(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    if not api:
        await callback.answer("Ошибка")
        return

    prefix = callback.data.replace("export_cancel_", "")

    try:
        jobs = await api.export_list_jobs()
        target = next((j for j in jobs if str(j["id"]).startswith(prefix)), None)
        if target:
            await api.export_cancel_job(target["id"])
            await callback.message.answer(
                f"Экспорт <b>{target['source_name']}</b> отменён."
            )
        else:
            await callback.message.answer("Задача не найдена.")
    except Exception:
        logger.exception("Failed to cancel export job")
        await callback.message.answer("Ошибка при отмене.")
    await callback.answer()


# ── /search — Semantic search across exported messages ───────────────────────


@router.message(Command("search"))
async def cmd_search(
    message: Message, command: CommandObject, state: FSMContext,
    api: APIClient = None, user_plan: str = "monitor", **kwargs,
) -> None:
    if not api:
        await message.answer("Ошибка подключения к серверу.")
        return

    query = command.args if command.args else None

    if not query:
        await state.set_state(SearchStates.waiting_query)
        await message.answer(
            "<b>Семантический поиск</b>\n\n"
            "Введите поисковый запрос (можно на любом языке):"
        )
        return

    await _execute_search(message, api, query, user_plan)


@router.message(SearchStates.waiting_query)
async def process_search_query(
    message: Message, state: FSMContext, api: APIClient = None,
    user_plan: str = "monitor", **kwargs,
) -> None:
    query = (message.text or "").strip()
    if not query or len(query) < 2:
        await message.answer("Запрос должен содержать минимум 2 символа:")
        return

    await state.clear()

    if not api:
        await message.answer("Ошибка подключения к серверу.")
        return

    await _execute_search(message, api, query, user_plan)


async def _execute_search(message: Message, api: APIClient, query: str, user_plan: str) -> None:
    """Execute semantic search and format results."""
    await message.answer(f"Ищу: <i>{_html_escape(query)}</i>...")

    try:
        results = await api.export_search(query=query, limit=5)
    except Exception as e:
        error_text = str(e)
        if "429" in error_text:
            limits = _get_limits(user_plan)
            await message.answer(
                f"Достигнут лимит поисковых запросов ({limits['search_per_day']}/день).\n\n"
                "Используйте /billing для апгрейда."
            )
        elif "403" in error_text:
            await message.answer(
                "Для поиска необходима активная подписка.\n\n"
                "Используйте /billing для подключения."
            )
        else:
            logger.exception("Search failed")
            await message.answer("Ошибка поиска. Попробуйте позже.")
        return

    hits = results.get("results", [])
    if not hits:
        await message.answer(
            f"По запросу «{_html_escape(query)}» ничего не найдено.\n\n"
            "Попробуйте другой запрос или экспортируйте больше данных через /export."
        )
        return

    lines = [f"<b>Результаты поиска:</b> «{_html_escape(query)}»\n"]
    for i, hit in enumerate(hits, 1):
        score = hit.get("score", 0)
        payload = hit.get("payload", {})
        text = payload.get("text", "")
        source_name = payload.get("source_name", "—")
        author = payload.get("author_name", "")
        date = payload.get("date", "")[:10]
        reactions = payload.get("reactions_count", 0)

        # Truncate text snippet
        snippet = text[:200] + "..." if len(text) > 200 else text
        snippet = _html_escape(snippet)

        relevance = int(score * 100) if score <= 1 else int(score)
        lines.append(f"<b>{i}.</b> [{relevance}%] <b>{source_name}</b>")
        if author:
            lines.append(f"   Автор: {author} | {date}")
        elif date:
            lines.append(f"   Дата: {date}")
        if reactions:
            lines.append(f"   Реакций: {reactions}")
        lines.append(f"   {snippet}")
        lines.append("")

    total_found = results.get("total", len(hits))
    if total_found > len(hits):
        lines.append(f"<i>Показано {len(hits)} из {total_found} результатов</i>")

    await message.answer("\n".join(lines))


# ── /popular — Show popular posts ────────────────────────────────────────────


@router.message(Command("popular"))
async def cmd_popular(
    message: Message, api: APIClient = None, user_plan: str = "monitor", **kwargs
) -> None:
    if not api:
        await message.answer("Ошибка подключения к серверу.")
        return

    try:
        data = await api.export_popular()
    except Exception as e:
        error_text = str(e)
        if "403" in error_text:
            await message.answer(
                "Аналитика недоступна для вашего тарифа.\n\n"
                "Используйте /billing для апгрейда."
            )
        else:
            logger.exception("Failed to load popular posts")
            await message.answer("Не удалось загрузить популярные посты.")
        return

    posts = data.get("posts", [])
    if not posts:
        await message.answer(
            "Нет данных о популярных постах.\n\n"
            "Сначала экспортируйте данные через /export."
        )
        return

    lines = ["<b>Популярные посты:</b>\n"]
    for i, post in enumerate(posts, 1):
        source_name = post.get("source_name", "—")
        author = post.get("author_name", "")
        reactions = post.get("reactions_count", 0)
        views = post.get("views_count", 0)
        forwards = post.get("forwards_count", 0)
        date = post.get("date", "")[:10]
        text = post.get("text_preview", "")

        snippet = _html_escape(text[:150] + "..." if len(text) > 150 else text)

        lines.append(f"<b>{i}.</b> {source_name}")
        stats_parts = []
        if reactions:
            stats_parts.append(f"👍 {reactions}")
        if views:
            stats_parts.append(f"👁 {views}")
        if forwards:
            stats_parts.append(f"↗️ {forwards}")
        stats_str = " | ".join(stats_parts)
        if author:
            lines.append(f"   {author} | {date} | {stats_str}")
        else:
            lines.append(f"   {date} | {stats_str}")
        if snippet:
            lines.append(f"   {snippet}")
        lines.append("")

    await message.answer("\n".join(lines))


# ── /authors — Show top authors ──────────────────────────────────────────────


@router.message(Command("authors"))
async def cmd_authors(
    message: Message, api: APIClient = None, user_plan: str = "monitor", **kwargs
) -> None:
    if not api:
        await message.answer("Ошибка подключения к серверу.")
        return

    limits = _get_limits(user_plan)
    if not limits["full_analytics"] and PLAN_ORDER.get(user_plan, 0) < PLAN_ORDER["creator"]:
        await message.answer(
            "Полная аналитика авторов доступна на тарифе Creator и выше.\n\n"
            "Используйте /billing для апгрейда."
        )
        return

    try:
        data = await api.export_authors()
    except Exception:
        logger.exception("Failed to load authors")
        await message.answer("Не удалось загрузить статистику авторов.")
        return

    authors = data.get("authors", [])
    if not authors:
        await message.answer(
            "Нет данных об авторах.\n\n"
            "Сначала экспортируйте данные через /export."
        )
        return

    lines = ["<b>Топ авторов:</b>\n"]
    for i, author in enumerate(authors, 1):
        name = author.get("author_name", "Неизвестный")
        username = author.get("author_username")
        username_str = f" @{username}" if username else ""
        messages = author.get("message_count", 0)
        avg_reactions = author.get("avg_reactions", 0)
        total_views = author.get("total_views", 0)

        lines.append(f"<b>{i}.</b> {name}{username_str}")
        lines.append(f"   Сообщений: {messages} | Ср. реакций: {avg_reactions:.1f} | Просмотров: {total_views}")
        lines.append("")

    await message.answer("\n".join(lines))


# ── /activity — Show activity stats ──────────────────────────────────────────


@router.message(Command("activity"))
async def cmd_activity(
    message: Message, api: APIClient = None, user_plan: str = "monitor", **kwargs
) -> None:
    if not api:
        await message.answer("Ошибка подключения к серверу.")
        return

    limits = _get_limits(user_plan)
    if not limits["full_analytics"] and PLAN_ORDER.get(user_plan, 0) < PLAN_ORDER["creator"]:
        await message.answer(
            "Полная аналитика активности доступна на тарифе Creator и выше.\n\n"
            "Используйте /billing для апгрейда."
        )
        return

    try:
        data = await api.export_activity()
    except Exception:
        logger.exception("Failed to load activity stats")
        await message.answer("Не удалось загрузить статистику активности.")
        return

    total_messages = data.get("total_messages", 0)
    total_sources = data.get("total_sources", 0)
    by_hour = data.get("by_hour", {})
    by_weekday = data.get("by_weekday", {})
    recent_daily = data.get("recent_daily", [])

    lines = [
        "<b>Статистика активности:</b>\n",
        f"Всего сообщений: {total_messages}",
        f"Источников: {total_sources}",
    ]

    if by_hour:
        lines.append("\n<b>Активность по часам (топ-5):</b>")
        sorted_hours = sorted(by_hour.items(), key=lambda x: x[1], reverse=True)[:5]
        for hour, count in sorted_hours:
            bar = _activity_bar(count, max(by_hour.values()) if by_hour else 1)
            lines.append(f"  {hour}:00 {bar} {count}")

    weekday_names = {
        "0": "Пн", "1": "Вт", "2": "Ср", "3": "Чт", "4": "Пт", "5": "Сб", "6": "Вс",
    }
    if by_weekday:
        lines.append("\n<b>Активность по дням недели:</b>")
        for day_num in sorted(by_weekday.keys()):
            count = by_weekday[day_num]
            name = weekday_names.get(str(day_num), str(day_num))
            bar = _activity_bar(count, max(by_weekday.values()) if by_weekday else 1)
            lines.append(f"  {name} {bar} {count}")

    if recent_daily:
        lines.append("\n<b>Последние дни:</b>")
        for entry in recent_daily[:7]:
            date = entry.get("date", "")[:10]
            count = entry.get("count", 0)
            lines.append(f"  {date}: {count} сообщений")

    await message.answer("\n".join(lines))


# ── Helpers ──────────────────────────────────────────────────────────────────


def _html_escape(text: str) -> str:
    """Escape HTML special characters for Telegram."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def _activity_bar(value: int, max_value: int, length: int = 8) -> str:
    """Generate a simple text bar chart."""
    if max_value <= 0:
        return "░" * length
    filled = max(1, int(value / max_value * length))
    return "█" * filled + "░" * (length - filled)
