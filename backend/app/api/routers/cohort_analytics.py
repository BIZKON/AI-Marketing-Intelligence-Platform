"""Cohort analytics API — cross-user progress comparison, leaderboard, ranking."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.cohort_service import CohortService

router = APIRouter()


# ── Response schemas ─────────────────────────────────────────────────────────


class CohortEntry(BaseModel):
    cohort_label: str
    user_count: int
    total_sessions: int
    completed_sessions: int
    avg_score: float | None = None
    avg_sessions_per_user: float = 0
    completion_rate: float = 0


class LeaderboardEntry(BaseModel):
    user_id: str
    display_name: str
    sessions: int
    avg_score: float | None = None
    best_score: int | None = None
    level: str = "trainee"
    xp: int = 0


class UserRankResponse(BaseModel):
    rank: int
    total_users: int
    percentile: float
    total_sessions: int
    completed_sessions: int
    avg_score: float | None = None
    avg_sessions_per_user: float = 0
    completion_rate: float = 0


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/by-registration", response_model=list[CohortEntry])
async def cohort_by_registration(
    period_days: int = Query(30, ge=7, le=365),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CohortEntry]:
    """Compare user progress grouped by registration month."""
    svc = CohortService(db)
    data = await svc.get_cohort_by_registration(period_days=period_days)
    return [CohortEntry(**c) for c in data]


@router.get("/by-plan", response_model=list[CohortEntry])
async def cohort_by_plan(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CohortEntry]:
    """Compare user progress grouped by subscription plan."""
    svc = CohortService(db)
    data = await svc.get_cohort_by_plan()
    return [CohortEntry(**c) for c in data]


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(
    limit: int = Query(20, ge=1, le=100),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LeaderboardEntry]:
    """Get top-performing users by average training score (min 3 sessions)."""
    svc = CohortService(db)
    data = await svc.get_leaderboard(limit=limit)
    return [LeaderboardEntry(**e) for e in data]


@router.get("/my-rank", response_model=UserRankResponse)
async def my_rank(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserRankResponse:
    """Get the current user's rank among all users."""
    svc = CohortService(db)
    data = await svc.get_user_rank(user.id)
    return UserRankResponse(**data)
