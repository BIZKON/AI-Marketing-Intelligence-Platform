"""Training service — AI client simulation, dialog evaluation, and analytics.

Handles the core training loop: simulate client responses via Atlas Cloud,
evaluate completed dialogs, track achievements, and compute analytics.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, date
from typing import Any

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.atlas_cloud import get_atlas_client
from app.core.config import get_settings
from app.models.session_evaluation import SessionEvaluation
from app.models.session_message import SessionMessage
from app.models.training_achievement import TrainingAchievement
from app.models.training_scenario import TrainingScenario
from app.models.training_session import SessionStatus, TrainingSession
from app.models.weekly_training_stats import WeeklyTrainingStats
from app.models.user import User

logger = logging.getLogger(__name__)

settings = get_settings()

# Achievement definitions
ACHIEVEMENT_DEFS = {
    "first_session": {"name": "Первая сессия", "icon": "star", "description": "Проведи свою первую тренировку"},
    "sessions_10": {"name": "Практик", "icon": "fire", "description": "Проведи 10 тренировок"},
    "sessions_50": {"name": "Мастер диалога", "icon": "trophy", "description": "Проведи 50 тренировок"},
    "perfect_score": {"name": "Идеальный звонок", "icon": "medal", "description": "Получи 100 баллов"},
    "score_80_plus": {"name": "Профессионал", "icon": "award", "description": "Получи 80+ баллов"},
    "all_scenarios": {"name": "Универсал", "icon": "target", "description": "Пройди все сценарии"},
    "streak_7": {"name": "Неделя без пропусков", "icon": "flame", "description": "Тренируйся 7 дней подряд"},
}


class TrainingService:
    """Core training service for AI-powered sales simulation via Atlas Cloud."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.atlas = get_atlas_client()

    # ── Scenarios ─────────────────────────────────────────────────────────────

    async def list_scenarios(self, user_id: uuid.UUID | None = None) -> list[TrainingScenario]:
        stmt = select(TrainingScenario).where(
            (TrainingScenario.is_public.is_(True))
            | (TrainingScenario.created_by == user_id)
        ).order_by(TrainingScenario.created_at)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_scenario(self, scenario_id: uuid.UUID) -> TrainingScenario | None:
        result = await self.db.execute(
            select(TrainingScenario).where(TrainingScenario.id == scenario_id)
        )
        return result.scalar_one_or_none()

    async def create_scenario(self, user_id: uuid.UUID, data: dict) -> TrainingScenario:
        scenario = TrainingScenario(
            title=data["title"],
            description=data.get("description"),
            type=data["type"],
            difficulty=data.get("difficulty", "medium"),
            client_persona=data["client_persona"],
            system_prompt=data["system_prompt"],
            ideal_script=data.get("ideal_script"),
            success_criteria=data.get("success_criteria"),
            created_by=user_id,
            is_public=data.get("is_public", False),
            tags=data.get("tags"),
        )
        self.db.add(scenario)
        await self.db.flush()
        await self.db.refresh(scenario)
        return scenario

    # ── Sessions ──────────────────────────────────────────────────────────────

    async def create_session(
        self, user_id: uuid.UUID, scenario_id: uuid.UUID, mode: str = "text"
    ) -> TrainingSession:
        session = TrainingSession(
            user_id=user_id,
            scenario_id=scenario_id,
            mode=mode,
            status=SessionStatus.IN_PROGRESS,
        )
        self.db.add(session)
        await self.db.flush()
        await self.db.refresh(session)
        return session

    async def get_session(self, session_id: uuid.UUID) -> TrainingSession | None:
        result = await self.db.execute(
            select(TrainingSession)
            .options(
                selectinload(TrainingSession.messages),
                selectinload(TrainingSession.evaluation),
                selectinload(TrainingSession.scenario),
            )
            .where(TrainingSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_user_sessions(
        self, user_id: uuid.UUID, limit: int = 20, offset: int = 0
    ) -> list[TrainingSession]:
        result = await self.db.execute(
            select(TrainingSession)
            .options(selectinload(TrainingSession.evaluation))
            .where(TrainingSession.user_id == user_id)
            .order_by(desc(TrainingSession.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def complete_session(self, session: TrainingSession) -> TrainingSession:
        session.status = SessionStatus.COMPLETED
        session.completed_at = datetime.utcnow()
        if session.started_at:
            delta = session.completed_at - session.started_at
            session.duration_seconds = int(delta.total_seconds())
        await self.db.flush()
        return session

    # ── AI Client Simulation ──────────────────────────────────────────────────

    async def simulate_client(
        self, session: TrainingSession, user_message: str,
    ) -> tuple[SessionMessage, SessionMessage]:
        """Send user message and get AI client response via Atlas Cloud."""
        user_msg = SessionMessage(session_id=session.id, role="user", content=user_message)
        self.db.add(user_msg)
        await self.db.flush()

        history = []
        for msg in session.messages:
            if msg.id != user_msg.id:
                history.append({"role": msg.role, "content": msg.content})
        history.append({"role": "user", "content": user_message})

        scenario = session.scenario
        if not scenario:
            scenario = await self.get_scenario(session.scenario_id)
        system_prompt = scenario.system_prompt if scenario else self._default_system_prompt()

        result = await self.atlas.chat(
            messages=history, system=system_prompt, max_tokens=500, temperature=0.8,
        )
        ai_response = result.get("content", "...")

        assistant_msg = SessionMessage(session_id=session.id, role="assistant", content=ai_response)
        self.db.add(assistant_msg)
        await self.db.flush()
        await self.db.refresh(user_msg)
        await self.db.refresh(assistant_msg)
        return user_msg, assistant_msg

    # ── Dialog Evaluation ─────────────────────────────────────────────────────

    async def evaluate_session(self, session: TrainingSession) -> SessionEvaluation:
        transcript_lines = []
        for msg in session.messages:
            speaker = "Администратор" if msg.role == "user" else "Клиент"
            transcript_lines.append(f"{speaker}: {msg.content}")
        transcript = "\n".join(transcript_lines)

        scenario = session.scenario
        if not scenario:
            scenario = await self.get_scenario(session.scenario_id)
        ideal_script = scenario.ideal_script if scenario else ""

        eval_prompt = self._build_evaluation_prompt(transcript, ideal_script)

        result = await self.atlas.chat(
            messages=[{"role": "user", "content": eval_prompt}],
            system=self._evaluation_system_prompt(),
            max_tokens=2000, temperature=0.3,
        )
        result_text = result.get("content", "")
        scores = self._parse_evaluation(result_text)

        evaluation = SessionEvaluation(
            session_id=session.id,
            overall_score=scores.get("overall_score", 0),
            criteria_scores=scores.get("criteria_scores", {}),
            strengths=scores.get("strengths", []),
            improvements=scores.get("improvements", []),
            detailed_feedback=scores.get("detailed_feedback", ""),
            mood_analysis=scores.get("mood_analysis", "neutral"),
        )
        self.db.add(evaluation)
        await self.db.flush()
        await self.db.refresh(evaluation)
        await self._check_achievements(session.user_id, evaluation)
        return evaluation

    # ── Analytics ─────────────────────────────────────────────────────────────

    async def get_analytics(self, user_id: uuid.UUID) -> dict[str, Any]:
        total_result = await self.db.execute(
            select(func.count(TrainingSession.id)).where(TrainingSession.user_id == user_id)
        )
        total_sessions = total_result.scalar() or 0

        completed_result = await self.db.execute(
            select(func.count(TrainingSession.id)).where(
                TrainingSession.user_id == user_id, TrainingSession.status == SessionStatus.COMPLETED,
            )
        )
        completed_sessions = completed_result.scalar() or 0

        score_result = await self.db.execute(
            select(func.avg(SessionEvaluation.overall_score), func.max(SessionEvaluation.overall_score))
            .join(TrainingSession, SessionEvaluation.session_id == TrainingSession.id)
            .where(TrainingSession.user_id == user_id)
        )
        row = score_result.one_or_none()
        avg_score = float(row[0]) if row and row[0] else None
        best_score = int(row[1]) if row and row[1] else None

        duration_result = await self.db.execute(
            select(func.sum(TrainingSession.duration_seconds)).where(
                TrainingSession.user_id == user_id, TrainingSession.duration_seconds.isnot(None),
            )
        )
        total_seconds = duration_result.scalar() or 0
        total_duration_minutes = total_seconds // 60

        criteria_result = await self.db.execute(
            select(SessionEvaluation.criteria_scores)
            .join(TrainingSession, SessionEvaluation.session_id == TrainingSession.id)
            .where(TrainingSession.user_id == user_id)
        )
        all_criteria = [r[0] for r in criteria_result.all() if r[0]]
        criteria_averages = self._compute_criteria_averages(all_criteria)

        weekly_result = await self.db.execute(
            select(WeeklyTrainingStats).where(WeeklyTrainingStats.user_id == user_id)
            .order_by(desc(WeeklyTrainingStats.week_start)).limit(12)
        )
        weekly_stats = list(weekly_result.scalars().all())
        recent = await self.list_user_sessions(user_id, limit=10)

        ach_result = await self.db.execute(
            select(TrainingAchievement).where(TrainingAchievement.user_id == user_id)
            .order_by(desc(TrainingAchievement.created_at))
        )
        achievements = list(ach_result.scalars().all())

        return {
            "total_sessions": total_sessions,
            "completed_sessions": completed_sessions,
            "avg_score": round(avg_score, 1) if avg_score else None,
            "best_score": best_score,
            "total_duration_minutes": total_duration_minutes,
            "criteria_averages": criteria_averages,
            "weekly_stats": weekly_stats,
            "recent_sessions": recent,
            "achievements": achievements,
        }

    # ── Private Methods ───────────────────────────────────────────────────────

    @staticmethod
    def _default_system_prompt() -> str:
        return (
            "Ты — потенциальный клиент студии йоги и растяжки 'Алхимия'. "
            "Тебе позвонил администратор студии. Веди себя как реальный клиент: "
            "задавай вопросы, выражай сомнения, реагируй естественно. "
            "Отвечай на русском языке. Будь реалистичной и не слишком простой собеседницей."
        )

    @staticmethod
    def _evaluation_system_prompt() -> str:
        return (
            "Ты — эксперт по оценке качества телефонных продаж для студии йоги и растяжки. "
            "Ты анализируешь диалоги между администратором студии и клиентом. "
            "Оценивай строго, но справедливо. Давай конкретные рекомендации. "
            "Всегда отвечай в формате JSON."
        )

    @staticmethod
    def _build_evaluation_prompt(transcript: str, ideal_script: str) -> str:
        prompt = f"""Проанализируй следующий диалог между администратором студии йоги и клиентом.

ТРАНСКРИПТ ДИАЛОГА:
{transcript}
"""
        if ideal_script:
            prompt += f"""
ИДЕАЛЬНЫЙ СКРИПТ ДЛЯ СРАВНЕНИЯ:
{ideal_script}
"""
        prompt += """
Оцени работу администратора по 7 критериям (0-100 баллов каждый):
1. greeting — Приветствие и установление контакта
2. listening — Активное слушание
3. objection_handling — Работа с возражениями
4. product_knowledge — Знание продукта
5. closing — Техника закрытия сделки
6. tone_empathy — Тон и эмпатия
7. script_adherence — Следование скрипту

Верни ТОЛЬКО валидный JSON (без markdown-обёртки) в формате:
{
  "overall_score": 75,
  "criteria_scores": {
    "greeting": 80, "listening": 70, "objection_handling": 65,
    "product_knowledge": 75, "closing": 60, "tone_empathy": 85,
    "script_adherence": 70
  },
  "strengths": ["Тёплое приветствие", "Хорошая эмпатия"],
  "improvements": ["Нужно задавать больше вопросов"],
  "detailed_feedback": "Подробный разбор диалога...",
  "mood_analysis": "neutral"
}
"""
        return prompt

    @staticmethod
    def _parse_evaluation(text: str) -> dict[str, Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        import re
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end != -1:
            try:
                return json.loads(text[brace_start:brace_end + 1])
            except json.JSONDecodeError:
                pass
        logger.warning("Failed to parse evaluation response: %s", text[:200])
        return {
            "overall_score": 0, "criteria_scores": {}, "strengths": [],
            "improvements": ["Не удалось выполнить оценку"],
            "detailed_feedback": text, "mood_analysis": "neutral",
        }

    @staticmethod
    def _compute_criteria_averages(all_criteria: list[dict]) -> dict[str, float]:
        if not all_criteria:
            return {}
        totals: dict[str, list[float]] = {}
        for criteria in all_criteria:
            for key, value in criteria.items():
                if isinstance(value, (int, float)):
                    totals.setdefault(key, []).append(float(value))
        return {key: round(sum(values) / len(values), 1) for key, values in totals.items()}

    async def _check_achievements(
        self, user_id: uuid.UUID, evaluation: SessionEvaluation
    ) -> list[TrainingAchievement]:
        new_achievements = []
        result = await self.db.execute(
            select(TrainingAchievement.achievement_type).where(TrainingAchievement.user_id == user_id)
        )
        existing = {r[0] for r in result.all()}
        count_result = await self.db.execute(
            select(func.count(TrainingSession.id)).where(
                TrainingSession.user_id == user_id, TrainingSession.status == SessionStatus.COMPLETED,
            )
        )
        session_count = count_result.scalar() or 0

        if "first_session" not in existing and session_count >= 1:
            new_achievements.append(await self._award_achievement(user_id, "first_session"))
        if "sessions_10" not in existing and session_count >= 10:
            new_achievements.append(await self._award_achievement(user_id, "sessions_10"))
        if "sessions_50" not in existing and session_count >= 50:
            new_achievements.append(await self._award_achievement(user_id, "sessions_50"))
        if "perfect_score" not in existing and evaluation.overall_score == 100:
            new_achievements.append(await self._award_achievement(user_id, "perfect_score"))
        if "score_80_plus" not in existing and (evaluation.overall_score or 0) >= 80:
            new_achievements.append(await self._award_achievement(user_id, "score_80_plus"))
        return new_achievements

    async def _award_achievement(self, user_id: uuid.UUID, achievement_type: str) -> TrainingAchievement:
        achievement = TrainingAchievement(
            user_id=user_id, achievement_type=achievement_type,
            metadata_json=ACHIEVEMENT_DEFS.get(achievement_type, {}),
        )
        self.db.add(achievement)
        await self.db.flush()
        logger.info("Awarded achievement %s to user %s", achievement_type, user_id)
        return achievement
