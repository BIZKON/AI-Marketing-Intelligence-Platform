"""Limits service: usage tracking, limit enforcement, warnings, and upsell messages."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limits import LIMIT_WARNING_THRESHOLD, PlanLimits, get_plan_limits
from app.models.competitor import Competitor
from app.models.content_task import ContentTask
from app.models.report import Report, ReportType
from app.models.subscription import PlanType


@dataclass
class UsageInfo:
    """Current usage statistics for a user's plan."""

    competitors: int
    competitors_limit: int
    tasks_this_month: int
    tasks_limit: int
    voice_this_week: int
    voice_limit: int
    video_this_week: int
    video_limit: int

    @property
    def competitors_pct(self) -> float:
        return self.competitors / self.competitors_limit if self.competitors_limit > 0 else 0

    @property
    def tasks_pct(self) -> float:
        return self.tasks_this_month / self.tasks_limit if self.tasks_limit > 0 else 0

    def near_limit(self, resource: str) -> bool:
        pct = getattr(self, f"{resource}_pct", 0)
        return pct >= LIMIT_WARNING_THRESHOLD

    def at_limit(self, resource: str) -> bool:
        usage = getattr(self, resource, 0)
        limit = getattr(self, f"{resource}_limit", 0)
        return usage >= limit


@dataclass
class LimitCheckResult:
    allowed: bool
    current_usage: int
    limit: int
    warning: str | None = None
    upsell_message: str | None = None


UPSELL_MESSAGES: dict[PlanType, str] = {
    PlanType.MONITOR: (
        "🚀 <b>Upgrade to Creator ($499/мес)</b>\n\n"
        "Получите:\n"
        "• До 7 конкурентов\n"
        "• 3 AI-агента\n"
        "• 20 задач контент-плана в месяц\n"
        "• Голосовые отчёты\n"
        "• Ежедневные алерты\n\n"
        "Используйте /billing для апгрейда."
    ),
    PlanType.CREATOR: (
        "🚀 <b>Upgrade to Autopilot ($999/мес)</b>\n\n"
        "Получите:\n"
        "• До 15 конкурентов\n"
        "• 5 AI-агентов\n"
        "• 50 задач в месяц\n"
        "• Автопостинг\n"
        "• Видеоотчёты\n"
        "• Стратегические отчёты\n\n"
        "Используйте /billing для апгрейда."
    ),
    PlanType.AUTOPILOT: (
        "🚀 <b>Upgrade to Enterprise ($2500+/мес)</b>\n\n"
        "Получите:\n"
        "• Безлимитные конкуренты\n"
        "• Безлимитные агенты\n"
        "• White-label\n"
        "• API-доступ\n"
        "• Приоритетная поддержка\n\n"
        "Используйте /billing для апгрейда."
    ),
    PlanType.ENTERPRISE: "",
}


class LimitsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_usage(self, user_id: uuid.UUID, plan: PlanType) -> UsageInfo:
        """Get full usage statistics for a user."""
        limits = get_plan_limits(plan)
        now = datetime.now(timezone.utc)

        competitors_count = await self._count_competitors(user_id)
        tasks_count = await self._count_tasks_this_month(user_id, now)
        voice_count = await self._count_reports_this_week(user_id, ReportType.VOICE, now)
        video_count = await self._count_reports_this_week(user_id, ReportType.VIDEO, now)

        return UsageInfo(
            competitors=competitors_count,
            competitors_limit=limits.competitors,
            tasks_this_month=tasks_count,
            tasks_limit=limits.tasks_per_month,
            voice_this_week=voice_count,
            voice_limit=limits.voice_per_week,
            video_this_week=video_count,
            video_limit=limits.video_per_week,
        )

    async def check_competitor_limit(self, user_id: uuid.UUID, plan: PlanType) -> LimitCheckResult:
        """Check if user can add another competitor."""
        limits = get_plan_limits(plan)
        count = await self._count_competitors(user_id)

        if count >= limits.competitors:
            return LimitCheckResult(
                allowed=False,
                current_usage=count,
                limit=limits.competitors,
                upsell_message=UPSELL_MESSAGES.get(plan),
            )

        warning = None
        if limits.competitors > 0 and count / limits.competitors >= LIMIT_WARNING_THRESHOLD:
            remaining = limits.competitors - count
            warning = f"⚠️ У вас осталось {remaining} слот(ов) для конкурентов из {limits.competitors}."

        return LimitCheckResult(allowed=True, current_usage=count, limit=limits.competitors, warning=warning)

    async def check_task_limit(self, user_id: uuid.UUID, plan: PlanType) -> LimitCheckResult:
        """Check if user can create another content task this month."""
        limits = get_plan_limits(plan)
        if limits.tasks_per_month == 0:
            return LimitCheckResult(
                allowed=False,
                current_usage=0,
                limit=0,
                upsell_message=UPSELL_MESSAGES.get(plan),
            )

        now = datetime.now(timezone.utc)
        count = await self._count_tasks_this_month(user_id, now)

        if count >= limits.tasks_per_month:
            return LimitCheckResult(
                allowed=False,
                current_usage=count,
                limit=limits.tasks_per_month,
                upsell_message=UPSELL_MESSAGES.get(plan),
            )

        warning = None
        if count / limits.tasks_per_month >= LIMIT_WARNING_THRESHOLD:
            remaining = limits.tasks_per_month - count
            warning = f"⚠️ У вас осталось {remaining} задач(а) из {limits.tasks_per_month} в этом месяце."

        return LimitCheckResult(allowed=True, current_usage=count, limit=limits.tasks_per_month, warning=warning)

    async def check_voice_limit(self, user_id: uuid.UUID, plan: PlanType) -> LimitCheckResult:
        """Check if user can request a voice report this week."""
        limits = get_plan_limits(plan)
        if limits.voice_per_week == 0:
            return LimitCheckResult(
                allowed=False,
                current_usage=0,
                limit=0,
                upsell_message=UPSELL_MESSAGES.get(plan),
            )

        now = datetime.now(timezone.utc)
        count = await self._count_reports_this_week(user_id, ReportType.VOICE, now)

        if count >= limits.voice_per_week:
            return LimitCheckResult(
                allowed=False, current_usage=count, limit=limits.voice_per_week,
                upsell_message=UPSELL_MESSAGES.get(plan),
            )
        return LimitCheckResult(allowed=True, current_usage=count, limit=limits.voice_per_week)

    async def check_video_limit(self, user_id: uuid.UUID, plan: PlanType) -> LimitCheckResult:
        """Check if user can request a video report this week."""
        limits = get_plan_limits(plan)
        if limits.video_per_week == 0:
            return LimitCheckResult(
                allowed=False,
                current_usage=0,
                limit=0,
                upsell_message=UPSELL_MESSAGES.get(plan),
            )

        now = datetime.now(timezone.utc)
        count = await self._count_reports_this_week(user_id, ReportType.VIDEO, now)

        if count >= limits.video_per_week:
            return LimitCheckResult(
                allowed=False, current_usage=count, limit=limits.video_per_week,
                upsell_message=UPSELL_MESSAGES.get(plan),
            )
        return LimitCheckResult(allowed=True, current_usage=count, limit=limits.video_per_week)

    def format_usage_summary(self, usage: UsageInfo, plan: PlanType) -> str:
        """Format a human-readable usage summary for Telegram."""
        lines = [
            f"📊 <b>Использование ({plan.value.capitalize()})</b>\n",
            f"👥 Конкуренты: {usage.competitors}/{usage.competitors_limit}",
        ]
        if usage.tasks_limit > 0:
            lines.append(f"📝 Задачи (мес): {usage.tasks_this_month}/{usage.tasks_limit}")
        if usage.voice_limit > 0:
            lines.append(f"🎙 Голос (нед): {usage.voice_this_week}/{usage.voice_limit}")
        if usage.video_limit > 0:
            lines.append(f"🎬 Видео (нед): {usage.video_this_week}/{usage.video_limit}")
        return "\n".join(lines)

    async def _count_competitors(self, user_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count()).where(Competitor.user_id == user_id, Competitor.is_active.is_(True))
        )
        return result.scalar() or 0

    async def _count_tasks_this_month(self, user_id: uuid.UUID, now: datetime) -> int:
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        result = await self.db.execute(
            select(func.count()).where(
                ContentTask.user_id == user_id,
                ContentTask.created_at >= month_start,
            )
        )
        return result.scalar() or 0

    async def _count_reports_this_week(
        self, user_id: uuid.UUID, report_type: ReportType, now: datetime
    ) -> int:
        week_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        # Go back to Monday
        days_since_monday = now.weekday()
        from datetime import timedelta

        week_start = week_start - timedelta(days=days_since_monday)

        result = await self.db.execute(
            select(func.count()).where(
                Report.user_id == user_id,
                Report.type == report_type,
                Report.created_at >= week_start,
            )
        )
        return result.scalar() or 0
