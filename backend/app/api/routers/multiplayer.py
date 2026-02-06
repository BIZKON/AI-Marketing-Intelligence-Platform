"""Multiplayer mode routes — competitive training sessions."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.multiplayer_service import MultiplayerService

router = APIRouter()


class CreateMultiplayerRequest(BaseModel):
    scenario_id: str
    max_participants: int = 5


class JoinRequest(BaseModel):
    session_code: str


@router.post("/")
async def create_session(
    data: CreateMultiplayerRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a new multiplayer session."""
    svc = MultiplayerService(db)
    session = await svc.create_session(
        host_user_id=user.id,
        scenario_id=uuid.UUID(data.scenario_id),
        max_participants=data.max_participants,
    )
    return {
        "id": str(session.id),
        "session_code": session.session_code,
        "status": session.status.value,
        "max_participants": session.max_participants,
    }


@router.post("/join")
async def join_session(
    data: JoinRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Join a multiplayer session by code."""
    svc = MultiplayerService(db)
    participant = await svc.join_session(
        session_code=data.session_code,
        user_id=user.id,
    )
    if not participant:
        raise HTTPException(status_code=400, detail="Cannot join session")
    return {
        "session_id": str(participant.session_id),
        "status": "joined",
    }


@router.post("/{session_id}/start")
async def start_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Start a multiplayer session (host only)."""
    svc = MultiplayerService(db)
    session = await svc.start_session(uuid.UUID(session_id), user.id)
    if not session:
        raise HTTPException(status_code=400, detail="Cannot start session")
    return {"status": session.status.value}


@router.post("/{session_id}/complete")
async def complete_participation(
    session_id: str,
    score: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mark participant as completed with their score."""
    svc = MultiplayerService(db)
    participant = await svc.complete_participant(
        uuid.UUID(session_id), user.id, score,
    )
    if not participant:
        raise HTTPException(status_code=400, detail="Cannot complete")
    return {"status": "completed", "score": score}


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get multiplayer session details with participants."""
    svc = MultiplayerService(db)
    result = await svc.get_session_details(uuid.UUID(session_id))
    if not result:
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@router.get("/leaderboard/top")
async def get_leaderboard(
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Get global multiplayer leaderboard."""
    svc = MultiplayerService(db)
    return await svc.get_leaderboard(limit)
