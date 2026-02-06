"""Training module handler: practice sales calls with AI via Telegram.

Commands:
  /train    — Start a training session (pick scenario)
  /mystats  — View training analytics

In-session flow:
  1. User picks scenario from inline keyboard
  2. Bot creates session via API
  3. User sends text messages → AI responds as client
  4. User sends /done → Session completes, evaluation returned
"""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.api_client import APIClient
from bot.states.training import TrainingStates

logger = logging.getLogger(__name__)
router = Router()

DIFFICULTY_ICONS = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}


@router.message(Command("train"))
async def cmd_train(message: Message, state: FSMContext, api: APIClient = None, **kwargs) -> None:
    """Show available training scenarios."""
    if not api:
        await message.answer("Ошибка: не удалось подключиться к серверу.")
        return

    try:
        scenarios = await api.list_training_scenarios()
    except Exception:
        logger.exception("Failed to fetch training scenarios")
        await message.answer("Не удалось загрузить сценарии. Попробуйте позже.")
        return

    if not scenarios:
        await message.answer("Сценарии тренировок пока не добавлены.")
        return

    builder = InlineKeyboardBuilder()
    for sc in scenarios:
        icon = DIFFICULTY_ICONS.get(sc.get("difficulty", "medium"), "🟡")
        label = f"{icon} {sc['title']}"
        builder.button(text=label, callback_data=f"train_start_{sc['id'][:8]}")
    builder.adjust(1)

    # Store scenario mapping for later lookup
    scenario_map = {sc["id"][:8]: sc["id"] for sc in scenarios}
    await state.update_data(scenario_map=scenario_map)
    await state.set_state(TrainingStates.choosing_scenario)

    lines = ["<b>Тренажёр продаж</b>\n", "Выберите сценарий для тренировки:\n"]
    for sc in scenarios:
        icon = DIFFICULTY_ICONS.get(sc.get("difficulty", "medium"), "🟡")
        persona = sc.get("client_persona", {})
        client_name = persona.get("name", "Клиент")
        lines.append(f"{icon} <b>{sc['title']}</b>")
        lines.append(f"   Клиент: {client_name}")
        if sc.get("description"):
            desc = sc["description"][:80]
            lines.append(f"   {desc}{'...' if len(sc['description']) > 80 else ''}")
        lines.append("")

    await message.answer("\n".join(lines), reply_markup=builder.as_markup())


@router.callback_query(
    TrainingStates.choosing_scenario,
    lambda c: c.data and c.data.startswith("train_start_"),
)
async def cb_start_training(
    callback: CallbackQuery, state: FSMContext, api: APIClient = None, **kwargs
) -> None:
    """Create a training session for the chosen scenario."""
    if not api:
        await callback.answer("Ошибка подключения")
        return

    prefix = callback.data.replace("train_start_", "")
    data = await state.get_data()
    scenario_map = data.get("scenario_map", {})
    scenario_id = scenario_map.get(prefix)

    if not scenario_id:
        await callback.answer("Сценарий не найден")
        await state.clear()
        return

    try:
        session = await api.create_training_session(scenario_id)
    except Exception:
        logger.exception("Failed to create training session")
        await callback.message.answer("Не удалось создать сессию. Попробуйте позже.")
        await callback.answer()
        await state.clear()
        return

    await state.update_data(
        training_session_id=session["id"],
        scenario_id=scenario_id,
    )
    await state.set_state(TrainingStates.in_session)

    await callback.message.answer(
        "<b>Тренировка начата!</b>\n\n"
        "Напишите своё первое сообщение клиенту. "
        "AI ответит как реальный клиент.\n\n"
        "Когда закончите — отправьте /done для оценки."
    )
    await callback.answer()


@router.message(TrainingStates.in_session, Command("done"))
async def cmd_done_training(
    message: Message, state: FSMContext, api: APIClient = None, **kwargs
) -> None:
    """Complete the training session and show evaluation."""
    if not api:
        await message.answer("Ошибка подключения.")
        await state.clear()
        return

    data = await state.get_data()
    session_id = data.get("training_session_id")
    if not session_id:
        await message.answer("Нет активной сессии. Начните новую: /train")
        await state.clear()
        return

    await message.answer("Завершаю сессию и анализирую диалог...")

    try:
        evaluation = await api.complete_training_session(session_id)
    except Exception:
        logger.exception("Failed to complete training session")
        await message.answer("Не удалось оценить диалог. Попробуйте позже.")
        await state.clear()
        return

    await state.clear()

    # Format evaluation
    overall = evaluation.get("overall_score", 0)
    criteria = evaluation.get("criteria_scores", {})
    strengths = evaluation.get("strengths", [])
    improvements = evaluation.get("improvements", [])
    feedback = evaluation.get("detailed_feedback", "")

    criteria_labels = {
        "greeting": "Приветствие",
        "listening": "Слушание",
        "objection_handling": "Возражения",
        "product_knowledge": "Знание продукта",
        "closing": "Закрытие",
        "tone_empathy": "Тон и эмпатия",
        "script_adherence": "Скрипт",
    }

    lines = [
        f"<b>Результат тренировки</b>\n",
        f"Общий балл: <b>{overall}/100</b>\n",
        "<b>Оценка по критериям:</b>",
    ]
    for key, label in criteria_labels.items():
        score = criteria.get(key, "—")
        bar = _score_bar(score if isinstance(score, int) else 0)
        lines.append(f"  {label}: {bar} {score}")

    if strengths:
        lines.append("\n<b>Сильные стороны:</b>")
        for s in strengths[:3]:
            lines.append(f"  + {s}")

    if improvements:
        lines.append("\n<b>Области для улучшения:</b>")
        for s in improvements[:3]:
            lines.append(f"  - {s}")

    if feedback:
        # Truncate long feedback for Telegram
        truncated = feedback[:500] + ("..." if len(feedback) > 500 else "")
        lines.append(f"\n<b>Подробный разбор:</b>\n{truncated}")

    builder = InlineKeyboardBuilder()
    builder.button(text="Тренироваться ещё", callback_data="action_train_again")
    builder.button(text="Моя статистика", callback_data="action_mystats")
    builder.adjust(2)

    await message.answer("\n".join(lines), reply_markup=builder.as_markup())


@router.message(TrainingStates.in_session)
async def process_training_message(
    message: Message, state: FSMContext, api: APIClient = None, **kwargs
) -> None:
    """Forward user message to AI client and return response."""
    if not api or not message.text:
        return

    data = await state.get_data()
    session_id = data.get("training_session_id")
    if not session_id:
        await message.answer("Нет активной сессии. Начните новую: /train")
        await state.clear()
        return

    try:
        result = await api.send_training_message(session_id, message.text)
    except Exception:
        logger.exception("Failed to send training message")
        await message.answer("Ошибка отправки. Попробуйте ещё раз или /done для завершения.")
        return

    assistant_msg = result.get("assistant_message", {})
    reply_text = assistant_msg.get("content", "...")

    await message.answer(f"<b>Клиент:</b>\n{reply_text}")


@router.message(Command("mystats"))
async def cmd_mystats(message: Message, api: APIClient = None, **kwargs) -> None:
    """Show training analytics summary."""
    if not api:
        await message.answer("Ошибка подключения.")
        return

    try:
        analytics = await api.get_training_analytics()
    except Exception:
        logger.exception("Failed to fetch training analytics")
        await message.answer("Не удалось загрузить статистику. Попробуйте позже.")
        return

    total = analytics.get("total_sessions", 0)
    completed = analytics.get("completed_sessions", 0)
    avg_score = analytics.get("avg_score")
    best_score = analytics.get("best_score")
    duration = analytics.get("total_duration_minutes", 0)
    achievements = analytics.get("achievements", [])

    lines = [
        "<b>Статистика тренировок</b>\n",
        f"Всего сессий: {total}",
        f"Завершено: {completed}",
        f"Средний балл: {avg_score if avg_score else '—'}",
        f"Лучший балл: {best_score if best_score else '—'}",
        f"Общее время: {duration} мин",
    ]

    if achievements:
        lines.append(f"\nДостижений: {len(achievements)}")
        for ach in achievements[:5]:
            meta = ach.get("metadata_json", {})
            name = meta.get("name", ach.get("achievement_type", "?"))
            lines.append(f"  • {name}")

    criteria_avg = analytics.get("criteria_averages", {})
    if criteria_avg:
        criteria_labels = {
            "greeting": "Приветствие",
            "listening": "Слушание",
            "objection_handling": "Возражения",
            "product_knowledge": "Знание продукта",
            "closing": "Закрытие",
            "tone_empathy": "Тон и эмпатия",
            "script_adherence": "Скрипт",
        }
        lines.append("\n<b>Средние баллы по критериям:</b>")
        for key, label in criteria_labels.items():
            val = criteria_avg.get(key)
            if val is not None:
                bar = _score_bar(int(val))
                lines.append(f"  {label}: {bar} {val}")

    builder = InlineKeyboardBuilder()
    builder.button(text="Начать тренировку", callback_data="action_train_again")

    await message.answer("\n".join(lines), reply_markup=builder.as_markup())


@router.callback_query(lambda c: c.data == "action_train_again")
async def cb_train_again(callback: CallbackQuery, state: FSMContext, **kwargs) -> None:
    await callback.answer()
    await cmd_train(callback.message, state, **kwargs)


@router.callback_query(lambda c: c.data == "action_mystats")
async def cb_mystats(callback: CallbackQuery, **kwargs) -> None:
    await callback.answer()
    await cmd_mystats(callback.message, **kwargs)


def _score_bar(score: int) -> str:
    """Generate a simple text progress bar for a 0-100 score."""
    filled = score // 10
    return "█" * filled + "░" * (10 - filled)
