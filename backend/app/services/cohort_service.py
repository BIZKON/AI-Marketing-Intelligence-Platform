"""Cohort analytics service — cross-user progress comparison and group analysis."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session_evaluation import SessionEvaluation
from app.models.subscription import PlanType, Subscription, SubscriptionStatus
from app.models.training_session import SessionStatus, TrainingSession
from app.models.user import User
from app.models.user_gamification import UserGamification

logger = logging.getLogger(__name__)


class CohortService:
    """Analytics for comparing progress across user groups (cohorts)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_cohort_by_registration(self, period_days: int = 30) -> list[dict]:
        """Group users by registration month and compare aggregate metrics."""
        cohorts = []
        now = datetime.now(timezone.utc)

        # Get up to 6 cohorts (6 months back)
        for i in range(6):
            start = now - timedelta(days=period_days * (i + 1))
            end = now - timedelta(days=period_days * i)

            # Users in this cohort
            user_ids_result = await self.db.execute(
                select(User.id).where(
                    User.created_at >= start,
                    User.created_at < end,
                    User.is_active.is_(True),
                )
            )
            user_ids = [r[0] for r in user_ids_result.all()]
            if not user_ids:
                continue

            # Aggregate training metrics for the cohort
            metrics = await self._get_group_metrics(user_ids)
            cohorts.append({
                "cohort_label": start.strftime("%b %Y"),
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
                "user_count": len(user_ids),
                **metrics,
            })

        return cohorts

    async def get_cohort_by_plan(self) -> list[dict]:
        """Compare metrics across subscription plans."""
        plans = [PlanType.MONITOR, PlanType.CREATOR, PlanType.AUTOPILOT, PlanType.ENTERPRISE]
        cohorts = []

        for plan in plans:
            # Users with this plan
            user_ids_result = await self.db.execute(
                select(Subscription.user_id).where(
                    Subscription.plan == plan,
                    Subscription.status == SubscriptionStatus.ACTIVE,
                )
            )
            user_ids = list({r[0] for r in user_ids_result.all()})
            if not user_ids:
                cohorts.append({
                    "cohort_label": plan.value,
                    "user_count": 0,
                    "total_sessions": 0,
                    "completed_sessions": 0,
                    "avg_score": None,
                    "avg_sessions_per_user": 0,
                    "completion_rate": 0,
                })
                continue

            metrics = await self._get_group_metrics(user_ids)
            cohorts.append({
                "cohort_label": plan.value,
                "user_count": len(user_ids),
                **metrics,
            })

        return cohorts

    async def get_leaderboard(self, limit: int = 20) -> list[dict]:
        """Get top-performing users by average score."""
        result = await self.db.execute(
            select(
                TrainingSession.user_id,
                func.count(TrainingSession.id).label("sessions"),
                func.avg(SessionEvaluation.overall_score).label("avg_score"),
                func.max(SessionEvaluation.overall_score).label("best_score"),
            )
            .join(SessionEvaluation, SessionEvaluation.session_id == TrainingSession.id)
            .where(TrainingSession.status == SessionStatus.COMPLETED)
            .group_by(TrainingSession.user_id)
            .having(func.count(TrainingSession.id) >= 3)  # Minimum 3 sessions
            .order_by(func.avg(SessionEvaluation.overall_score).desc())
            .limit(limit)
        )
        rows = result.all()

        # Enrich with user info and gamification level
        leaderboard = []
        for row in rows:
            user_result = await self.db.execute(
                select(User.full_name, User.telegram_username).where(User.id == row.user_id)
            )
            user_info = user_result.one_or_none()

            gam_result = await self.db.execute(
                select(UserGamification.level, UserGamification.xp).where(
                    UserGamification.user_id == row.user_id
                )
            )
            gam_info = gam_result.one_or_none()

            display_name = "Anonymous"
            if user_info:
                display_name = user_info.full_name or user_info.telegram_username or "Anonymous"

            leaderboard.append({
                "user_id": str(row.user_id),
                "display_name": display_name,
                "sessions": row.sessions,
                "avg_score": round(float(row.avg_score), 1) if row.avg_score else None,
                "best_score": int(row.best_score) if row.best_score else None,
                "level": gam_info.level if gam_info else "trainee",
                "xp": gam_info.xp if gam_info else 0,
            })

        return leaderboard

    async def get_user_rank(self, user_id: uuid.UUID) -> dict:
        """Get a specific user's rank among all users."""
        # Subquery: all users with avg scores
        sub = (
            select(
                TrainingSession.user_id,
                func.avg(SessionEvaluation.overall_score).label("avg_score"),
                func.count(TrainingSession.id).label("sessions"),
            )
            .join(SessionEvaluation, SessionEvaluation.session_id == TrainingSession.id)
            .where(TrainingSession.status == SessionStatus.COMPLETED)
            .group_by(TrainingSession.user_id)
            .having(func.count(TrainingSession.id) >= 1)
            .subquery()
        )

        # Count how many users have a higher avg score
        higher_count = await self.db.execute(
            select(func.count()).select_from(sub).where(
                sub.c.avg_score > (
                    select(func.avg(SessionEvaluation.overall_score))
                    .join(TrainingSession, SessionEvaluation.session_id == TrainingSession.id)
                    .where(TrainingSession.user_id == user_id)
                    .scalar_subquery()
                )
            )
        )
        rank = (higher_count.scalar() or 0) + 1

        total_users_result = await self.db.execute(select(func.count()).select_from(sub))
        total_users = total_users_result.scalar() or 0

        # User's own metrics
        user_metrics = await self._get_group_metrics([user_id])

        return {
            "rank": rank,
            "total_users": total_users,
            "percentile": round((1 - rank / max(total_users, 1)) * 100, 1),
            **user_metrics,
        }

    async def _get_group_metrics(self, user_ids: list[uuid.UUID]) -> dict:
        """Compute aggregate training metrics for a group of users."""
        # Total and completed sessions
        total_result = await self.db.execute(
            select(func.count(TrainingSession.id)).where(
                TrainingSession.user_id.in_(user_ids)
            )
        )
        total_sessions = total_result.scalar() or 0

        completed_result = await self.db.execute(
            select(func.count(TrainingSession.id)).where(
                TrainingSession.user_id.in_(user_ids),
                TrainingSession.status == SessionStatus.COMPLETED,
            )
        )
        completed_sessions = completed_result.scalar() or 0

        # Average score
        score_result = await self.db.execute(
            select(func.avg(SessionEvaluation.overall_score))
            .join(TrainingSession, SessionEvaluation.session_id == TrainingSession.id)
            .where(TrainingSession.user_id.in_(user_ids))
        )
        avg_score_raw = score_result.scalar()
        avg_score = round(float(avg_score_raw), 1) if avg_score_raw else None

        user_count = len(user_ids)
        return {
            "total_sessions": total_sessions,
            "completed_sessions": completed_sessions,
            "avg_score": avg_score,
            "avg_sessions_per_user": round(total_sessions / max(user_count, 1), 1),
            "completion_rate": round(completed_sessions / max(total_sessions, 1) * 100, 1),
        }
