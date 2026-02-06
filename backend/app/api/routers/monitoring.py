"""Monitoring and Atlas Cloud usage tracking endpoints."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.atlas_cloud import _circuit_state, CIRCUIT_FAILURE_THRESHOLD
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.session_evaluation import SessionEvaluation
from app.models.training_session import SessionStatus, TrainingSession
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/atlas-cloud/status")
async def atlas_cloud_status(
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get Atlas Cloud circuit breaker status for all services."""
    services = {}
    for service, state in _circuit_state.items():
        failures = state.get("failures", 0)
        last_failure = state.get("last_failure", 0)
        is_open = failures >= CIRCUIT_FAILURE_THRESHOLD
        time_since = time.monotonic() - last_failure if last_failure else None

        services[service] = {
            "status": "open" if is_open else "closed",
            "failures": failures,
            "threshold": CIRCUIT_FAILURE_THRESHOLD,
            "seconds_since_last_failure": round(time_since, 1) if time_since else None,
        }

    return {
        "overall": "healthy" if not any(
            s["status"] == "open" for s in services.values()
        ) else "degraded",
        "services": services,
    }


@router.get("/training/stats")
async def training_platform_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get platform-wide training statistics (admin-level overview)."""
    # Total sessions
    total_result = await db.execute(select(func.count(TrainingSession.id)))
    total_sessions = total_result.scalar() or 0

    # Completed sessions
    completed_result = await db.execute(
        select(func.count(TrainingSession.id)).where(
            TrainingSession.status == SessionStatus.COMPLETED
        )
    )
    completed_sessions = completed_result.scalar() or 0

    # In-progress sessions
    in_progress_result = await db.execute(
        select(func.count(TrainingSession.id)).where(
            TrainingSession.status == SessionStatus.IN_PROGRESS
        )
    )
    in_progress_sessions = in_progress_result.scalar() or 0

    # Average score
    avg_result = await db.execute(
        select(func.avg(SessionEvaluation.overall_score))
    )
    avg_score = avg_result.scalar()

    # Unique users who trained
    users_result = await db.execute(
        select(func.count(func.distinct(TrainingSession.user_id)))
    )
    unique_users = users_result.scalar() or 0

    # Total training time
    duration_result = await db.execute(
        select(func.sum(TrainingSession.duration_seconds)).where(
            TrainingSession.duration_seconds.isnot(None)
        )
    )
    total_seconds = duration_result.scalar() or 0

    return {
        "total_sessions": total_sessions,
        "completed_sessions": completed_sessions,
        "in_progress_sessions": in_progress_sessions,
        "completion_rate": round(completed_sessions / total_sessions * 100, 1) if total_sessions else 0,
        "avg_score": round(float(avg_score), 1) if avg_score else None,
        "unique_users": unique_users,
        "total_training_hours": round(total_seconds / 3600, 1),
    }
