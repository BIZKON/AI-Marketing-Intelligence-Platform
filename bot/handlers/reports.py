"""Report handlers: digest, daily report, PDF, voice, video — all with API integration."""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.services.api_client import APIClient

logger = logging.getLogger(__name__)
router = Router()


# ── /digest — Request a competitive intelligence digest ─────────────────────


@router.message(Command("digest"))
async def cmd_digest(message: Message, api: APIClient = None, **kwargs) -> None:
    """Request weekly competitive intelligence digest."""
    if not api:
        await message.answer("Ошибка подключения. Попробуйте позже.")
        return

    await message.answer(
        "<b>Генерация еженедельного дайджеста...</b>\n\n"
        "AI анализирует активность ваших конкурентов. Это может занять некоторое время."
    )

    try:
        report = await api.request_digest()
        report_id = report["id"]

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📄 PDF", callback_data=f"rpt_pdf:{report_id}"),
                InlineKeyboardButton(text="🎙 Голос", callback_data=f"rpt_voice:{report_id}"),
            ],
            [
                InlineKeyboardButton(text="🎬 Видео", callback_data=f"rpt_video:{report_id}"),
                InlineKeyboardButton(text="📖 Текст", callback_data=f"rpt_text:{report_id}"),
            ],
        ])

        markdown = report.get("content_markdown", "")
        preview = markdown[:500] + "..." if markdown and len(markdown) > 500 else markdown

        text = (
            "<b>Дайджест создан!</b>\n\n"
            f"<b>{report.get('title', 'Дайджест')}</b>\n\n"
        )
        if preview:
            text += f"{_html_escape(preview)}\n\n"
        text += "Выберите формат:"

        await message.answer(text, reply_markup=kb)
    except Exception as e:
        error_text = str(e)
        if "403" in error_text:
            await message.answer(
                "Для дайджестов необходима подписка Monitor или выше.\n\n"
                "Используйте /billing для подключения."
            )
        else:
            logger.exception("Failed to request digest")
            await message.answer("Не удалось создать дайджест. Попробуйте позже.")


# ── /report — List recent reports with action buttons ────────────────────────


@router.message(Command("report"))
async def cmd_report(message: Message, api: APIClient = None, **kwargs) -> None:
    """Show latest reports."""
    if not api:
        await message.answer("Ошибка подключения. Попробуйте позже.")
        return

    try:
        reports = await api.list_reports(limit=5)
    except Exception:
        logger.exception("Failed to list reports")
        await message.answer("Не удалось загрузить отчёты.")
        return

    if not reports:
        await message.answer(
            "<b>У вас пока нет отчётов.</b>\n\n"
            "Используйте /digest чтобы запросить первый дайджест."
        )
        return

    type_labels = {
        "digest": "📊 Дайджест",
        "alert": "🔔 Алерт",
        "strategy": "📈 Стратегия",
        "voice": "🎙 Голос",
        "video": "🎬 Видео",
    }

    lines = ["<b>Последние отчёты:</b>\n"]
    buttons = []

    for report in reports:
        label = type_labels.get(report.get("type", ""), report.get("type", ""))
        title = report.get("title", "Без названия")
        created = report.get("created_at", "")[:10]
        report_id = report["id"]

        # Status indicator for media reports
        content = report.get("content") or {}
        status_icon = ""
        if report.get("type") in ("voice", "video"):
            s = content.get("status", "")
            if s == "generating":
                status_icon = " ⏳"
            elif s == "completed":
                status_icon = " ✅"
            elif s == "error":
                status_icon = " ❌"

        lines.append(f"• {label}: <b>{title}</b> ({created}){status_icon}")

        # Add action button for digest reports
        if report.get("type") == "digest":
            buttons.append([
                InlineKeyboardButton(
                    text=f"📄 PDF: {title[:30]}",
                    callback_data=f"rpt_pdf:{report_id}",
                ),
                InlineKeyboardButton(
                    text="🎙",
                    callback_data=f"rpt_voice:{report_id}",
                ),
            ])
        elif report.get("type") in ("voice", "video") and report.get("media_url"):
            buttons.append([
                InlineKeyboardButton(
                    text=f"▶️ {label}: скачать",
                    callback_data=f"rpt_media:{report_id}",
                ),
            ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await message.answer("\n".join(lines), reply_markup=kb)


# ── View full text report ────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("rpt_text:"))
async def cb_report_text(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    """Show full text content of a report."""
    report_id = callback.data.split(":", 1)[1]
    await callback.answer()

    try:
        report = await api.get_report(report_id)
    except Exception:
        await callback.message.answer("Не удалось загрузить отчёт.")
        return

    markdown = report.get("content_markdown", "")
    if not markdown:
        await callback.message.answer("Текстовое содержимое отсутствует.")
        return

    # Split into chunks if too long for Telegram (4096 chars)
    chunks = _split_text(markdown, 4000)
    for chunk in chunks:
        await callback.message.answer(_html_escape(chunk))


# ── PDF generation ───────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("rpt_pdf:"))
async def cb_report_pdf(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    """Generate and send PDF report."""
    report_id = callback.data.split(":", 1)[1]
    await callback.answer("Генерация PDF...")

    try:
        result = await api.request_pdf(report_id)
        pdf_url = result.get("pdf_url", "")
        size_kb = result.get("size_bytes", 0) // 1024

        await callback.message.answer(
            f"<b>📄 PDF отчёт готов!</b>\n\n"
            f"Размер: {size_kb} КБ\n"
            f"Ссылка для скачивания (24 часа):\n"
            f"<a href='{pdf_url}'>Скачать PDF</a>"
        )
    except Exception as e:
        error_text = str(e)
        if "403" in error_text:
            await callback.message.answer(
                "Для PDF-отчётов необходима подписка Monitor или выше."
            )
        elif "400" in error_text:
            await callback.message.answer("У этого отчёта нет данных для PDF.")
        else:
            logger.exception("PDF generation failed")
            await callback.message.answer("Не удалось сгенерировать PDF. Попробуйте позже.")


# ── /voice — Voice report ────────────────────────────────────────────────────


@router.message(Command("voice"))
async def cmd_voice(message: Message, api: APIClient = None, **kwargs) -> None:
    """Request voice report generation."""
    if not api:
        await message.answer("Ошибка подключения. Попробуйте позже.")
        return

    # Find the latest digest report
    try:
        reports = await api.list_reports(report_type="digest", limit=1)
        if not reports:
            await message.answer("Сначала создайте дайджест командой /digest.")
            return

        report = reports[0]
        report_id = report["id"]
    except Exception:
        logger.exception("Failed to list reports for voice")
        await message.answer("Ошибка при загрузке отчётов.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎙 Создать голосовой отчёт",
            callback_data=f"rpt_voice:{report_id}",
        )],
    ])

    await message.answer(
        f"<b>Голосовой отчёт</b>\n\n"
        f"Последний дайджест: <b>{report.get('title', 'Дайджест')}</b>\n"
        f"Дата: {report.get('created_at', '')[:10]}\n\n"
        f"AI конвертирует отчёт в аудио через ElevenLabs.",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("rpt_voice:"))
async def cb_report_voice(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    """Trigger voice report generation."""
    report_id = callback.data.split(":", 1)[1]
    await callback.answer("Запуск генерации аудио...")

    try:
        result = await api.request_voice_report(report_id)
        voice_report_id = result.get("report_id", "")

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔄 Проверить статус",
                callback_data=f"rpt_status:{voice_report_id}",
            )],
        ])

        await callback.message.answer(
            "<b>🎙 Генерация голосового отчёта запущена!</b>\n\n"
            "ElevenLabs конвертирует ваш дайджест в аудио.\n"
            "Это займёт около минуты.\n\n"
            f"ID: <code>{str(voice_report_id)[:8]}...</code>",
            reply_markup=kb,
        )
    except Exception as e:
        error_text = str(e)
        if "403" in error_text:
            await callback.message.answer(
                "Голосовые отчёты доступны на тарифе Creator и выше.\n"
                "Используйте /billing для подключения."
            )
        elif "400" in error_text:
            await callback.message.answer("У этого отчёта нет данных для аудио.")
        else:
            logger.exception("Voice report request failed")
            await callback.message.answer("Ошибка при создании голосового отчёта.")


# ── /video — Video report ────────────────────────────────────────────────────


@router.message(Command("video"))
async def cmd_video(message: Message, api: APIClient = None, **kwargs) -> None:
    """Request video report generation."""
    if not api:
        await message.answer("Ошибка подключения. Попробуйте позже.")
        return

    try:
        reports = await api.list_reports(report_type="digest", limit=1)
        if not reports:
            await message.answer("Сначала создайте дайджест командой /digest.")
            return

        report = reports[0]
        report_id = report["id"]
    except Exception:
        logger.exception("Failed to list reports for video")
        await message.answer("Ошибка при загрузке отчётов.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎬 Создать видеоотчёт",
            callback_data=f"rpt_video:{report_id}",
        )],
    ])

    await message.answer(
        f"<b>Видеоотчёт</b>\n\n"
        f"Последний дайджест: <b>{report.get('title', 'Дайджест')}</b>\n"
        f"Дата: {report.get('created_at', '')[:10]}\n\n"
        f"AI создаст видео с аватаром и визуализацией данных через HeyGen.\n"
        f"Генерация может занять несколько минут.",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("rpt_video:"))
async def cb_report_video(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    """Trigger video report generation."""
    report_id = callback.data.split(":", 1)[1]
    await callback.answer("Запуск генерации видео...")

    try:
        result = await api.request_video_report(report_id)
        video_report_id = result.get("report_id", "")

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔄 Проверить статус",
                callback_data=f"rpt_status:{video_report_id}",
            )],
        ])

        await callback.message.answer(
            "<b>🎬 Генерация видеоотчёта запущена!</b>\n\n"
            "HeyGen создаёт видео с AI-аватаром и графиками.\n"
            "Это может занять до 10 минут.\n\n"
            f"ID: <code>{str(video_report_id)[:8]}...</code>",
            reply_markup=kb,
        )
    except Exception as e:
        error_text = str(e)
        if "403" in error_text:
            await callback.message.answer(
                "Видеоотчёты доступны на тарифе Autopilot и выше.\n"
                "Используйте /billing для подключения."
            )
        elif "400" in error_text:
            await callback.message.answer("У этого отчёта нет данных для видео.")
        else:
            logger.exception("Video report request failed")
            await callback.message.answer("Ошибка при создании видеоотчёта.")


# ── Check media generation status ────────────────────────────────────────────


@router.callback_query(F.data.startswith("rpt_status:"))
async def cb_report_status(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    """Check status of voice/video report generation."""
    report_id = callback.data.split(":", 1)[1]
    await callback.answer("Проверяю статус...")

    try:
        report = await api.get_report(report_id)
    except Exception:
        await callback.message.answer("Не удалось проверить статус.")
        return

    content = report.get("content") or {}
    status = content.get("status", "unknown")
    media_url = report.get("media_url")
    report_type = report.get("type", "")

    type_label = "🎙 Голосовой" if report_type == "voice" else "🎬 Видео"

    if status == "completed" and media_url:
        fmt = "ogg" if report_type == "voice" else "mp4"
        duration = content.get("duration_estimate", "")
        extra = f"\nДлительность: {duration}" if duration else ""

        await callback.message.answer(
            f"<b>{type_label} отчёт готов! ✅</b>{extra}\n\n"
            f"<a href='{media_url}'>Скачать .{fmt}</a>\n\n"
            f"Ссылка действительна 24 часа."
        )
    elif status == "generating":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔄 Проверить снова",
                callback_data=f"rpt_status:{report_id}",
            )],
        ])
        await callback.message.answer(
            f"<b>{type_label} отчёт ещё генерируется... ⏳</b>\n\n"
            f"Нажмите кнопку чтобы проверить снова.",
            reply_markup=kb,
        )
    elif status == "error":
        error = content.get("error", "Неизвестная ошибка")
        await callback.message.answer(
            f"<b>{type_label} отчёт: ошибка ❌</b>\n\n"
            f"Причина: {_html_escape(error[:200])}\n\n"
            f"Попробуйте создать отчёт заново."
        )
    else:
        await callback.message.answer(f"Статус: {status}")


# ── Download media ───────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("rpt_media:"))
async def cb_report_media(callback: CallbackQuery, api: APIClient = None, **kwargs) -> None:
    """Show download link for completed media report."""
    report_id = callback.data.split(":", 1)[1]
    await callback.answer()

    try:
        report = await api.get_report(report_id)
    except Exception:
        await callback.message.answer("Не удалось загрузить отчёт.")
        return

    media_url = report.get("media_url")
    if not media_url:
        await callback.message.answer("Медиафайл недоступен. Попробуйте сгенерировать заново.")
        return

    report_type = report.get("type", "")
    fmt = "ogg" if report_type == "voice" else "mp4"
    label = "🎙 Голосовой" if report_type == "voice" else "🎬 Видео"

    await callback.message.answer(
        f"<b>{label} отчёт</b>\n\n"
        f"<a href='{media_url}'>Скачать .{fmt}</a>\n\n"
        f"Ссылка действительна 24 часа."
    )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _html_escape(text: str) -> str:
    """Escape HTML special characters for Telegram (#082)."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def _split_text(text: str, max_len: int = 4000) -> list[str]:
    """Split text into chunks at paragraph boundaries (#084).

    Handles paragraphs that exceed max_len by splitting at word boundaries.
    """
    if len(text) <= max_len:
        return [text]

    def _split_long(paragraph: str) -> list[str]:
        """Split a single paragraph longer than max_len at word boundaries."""
        words = paragraph.split(" ")
        parts: list[str] = []
        buf = ""
        for word in words:
            if buf and len(buf) + 1 + len(word) > max_len:
                parts.append(buf)
                buf = word
            else:
                buf = buf + " " + word if buf else word
        if buf:
            parts.append(buf)
        return parts

    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        # Handle oversized paragraphs
        if len(paragraph) > max_len:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long(paragraph))
            continue

        if len(current) + len(paragraph) + 2 > max_len:
            if current:
                chunks.append(current)
            current = paragraph
        else:
            current = current + "\n\n" + paragraph if current else paragraph

    if current:
        chunks.append(current)
    return chunks
