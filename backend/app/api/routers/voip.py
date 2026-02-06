"""VoIP integration routes — webhook for auto-analysis of calls."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.voip_recording import VoIPRecording

router = APIRouter()


class VoIPWebhookPayload(BaseModel):
    call_id: str
    direction: str = "inbound"
    caller_number: str | None = None
    audio_url: str | None = None
    duration_seconds: int | None = None
    user_id: str | None = None


@router.post("/webhook")
async def voip_webhook(
    payload: VoIPWebhookPayload,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Receive VoIP call recording webhook and queue for analysis."""
    recording = VoIPRecording(
        call_id=payload.call_id,
        direction=payload.direction,
        caller_number=payload.caller_number,
        audio_url=payload.audio_url,
        duration_seconds=payload.duration_seconds,
        user_id=uuid.UUID(payload.user_id) if payload.user_id else None,
        status="pending",
    )
    db.add(recording)
    await db.commit()
    await db.refresh(recording)

    return {
        "id": str(recording.id),
        "call_id": recording.call_id,
        "status": "queued",
    }


@router.get("/recordings")
async def list_recordings(
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List VoIP recordings for current user."""
    result = await db.execute(
        select(VoIPRecording)
        .where(VoIPRecording.user_id == user.id)
        .order_by(VoIPRecording.created_at.desc())
        .limit(limit)
    )
    recordings = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "call_id": r.call_id,
            "direction": r.direction,
            "caller_number": r.caller_number,
            "duration_seconds": r.duration_seconds,
            "status": r.status,
            "transcript": r.transcript,
            "analysis_score": r.analysis_score,
            "created_at": r.created_at.isoformat(),
        }
        for r in recordings
    ]


@router.get("/recordings/{recording_id}")
async def get_recording(
    recording_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get VoIP recording details."""
    result = await db.execute(
        select(VoIPRecording).where(
            VoIPRecording.id == uuid.UUID(recording_id),
            VoIPRecording.user_id == user.id,
        )
    )
    recording = result.scalar_one_or_none()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    return {
        "id": str(recording.id),
        "call_id": recording.call_id,
        "direction": recording.direction,
        "caller_number": recording.caller_number,
        "audio_url": recording.audio_url,
        "duration_seconds": recording.duration_seconds,
        "status": recording.status,
        "transcript": recording.transcript,
        "analysis_score": recording.analysis_score,
        "created_at": recording.created_at.isoformat(),
    }
