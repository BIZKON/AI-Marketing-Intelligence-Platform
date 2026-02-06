"""Call analysis API routes — upload and analyze real sales calls."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.call_analysis_service import CallAnalysisService

router = APIRouter()


@router.post("/analyze")
async def analyze_call(
    file: UploadFile = File(...),
    scenario_id: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Upload and analyze a sales call recording."""
    svc = CallAnalysisService(db)
    audio_data = await file.read()
    filename = file.filename or "call.mp3"
    sid = uuid.UUID(scenario_id) if scenario_id else None
    result = await svc.analyze_call(
        user_id=user.id,
        audio_data=audio_data,
        filename=filename,
        scenario_id=sid,
    )
    return result


@router.get("/history")
async def get_call_history(
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Get user's analyzed call history (returns training sessions of voice type)."""
    from sqlalchemy import select
    from app.models.training_session import TrainingSession, SessionMode

    result = await db.execute(
        select(TrainingSession)
        .where(
            TrainingSession.user_id == user.id,
            TrainingSession.mode == SessionMode.VOICE,
        )
        .order_by(TrainingSession.created_at.desc())
        .limit(limit)
    )
    sessions = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "status": s.status.value,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "duration_seconds": s.duration_seconds,
        }
        for s in sessions
    ]
