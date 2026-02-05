"""Report handlers: digest, daily report, voice, video — all with API integration."""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.services.api_client import APIClient

logger = logging.getLogger(__name__)
router = Router()


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
        await message.answer(
            "<b>Дайджест создан!</b>\n\n"
            f"ID отчёта: <code>{report['id'][:8]}...</code>\n"
            f"Статус: {report.get('content', {}).get('status', 'generating')}\n\n"
            "Вы получите уведомление когда отчёт будет готов."
        )
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

    lines = ["<b>Последние отчёты:</b>\n"]
    type_labels = {
        "digest": "📊 Дайджест",
        "alert": "🔔 Алерт",
        "strategy": "📈 Стратегия",
        "voice": "🎙 Голос",
        "video": "🎬 Видео",
    }

    for report in reports:
        label = type_labels.get(report.get("type", ""), report.get("type", ""))
        title = report.get("title", "Без названия")
        created = report.get("created_at", "")[:10]
        lines.append(f"• {label}: <b>{title}</b> ({created})")

    await message.answer("\n".join(lines))


@router.message(Command("voice"))
async def cmd_voice(message: Message, api: APIClient = None, user_plan: str = "monitor", **kwargs) -> None:
    """Request voice report (Creator+). Plan check is done in SubscriptionMiddleware."""
    if not api:
        await message.answer("Ошибка подключения. Попробуйте позже.")
        return

    await message.answer(
        "<b>Генерация голосового отчёта...</b>\n\n"
        "Конвертируем последний дайджест в аудио.\n"
        "Вы получите .ogg файл в этот чат."
    )

    # Voice generation will be triggered via Celery in Phase 5
    # For now, confirm the request was accepted
    try:
        reports = await api.list_reports(report_type="digest", limit=1)
        if not reports:
            await message.answer("Сначала создайте дайджест командой /digest.")
            return
        await message.answer(
            "Запрос на голосовой отчёт принят.\n"
            "Генерация аудио будет доступна в следующем обновлении."
        )
    except Exception:
        logger.exception("Failed to process voice request")
        await message.answer("Ошибка при создании голосового отчёта.")


@router.message(Command("video"))
async def cmd_video(message: Message, api: APIClient = None, user_plan: str = "monitor", **kwargs) -> None:
    """Request video report (Autopilot+). Plan check is done in SubscriptionMiddleware."""
    if not api:
        await message.answer("Ошибка подключения. Попробуйте позже.")
        return

    await message.answer(
        "<b>Генерация видеоотчёта...</b>\n\n"
        "Создаём видео с AI-аватаром и визуализацией данных.\n"
        "Это может занять несколько минут."
    )

    try:
        reports = await api.list_reports(report_type="digest", limit=1)
        if not reports:
            await message.answer("Сначала создайте дайджест командой /digest.")
            return
        await message.answer(
            "Запрос на видеоотчёт принят.\n"
            "Генерация видео будет доступна в следующем обновлении."
        )
    except Exception:
        logger.exception("Failed to process video request")
        await message.answer("Ошибка при создании видеоотчёта.")
