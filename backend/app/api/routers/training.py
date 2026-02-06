"""Training module API routes — scenarios, sessions, chat, evaluation, analytics."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.training_session import SessionStatus
from app.models.user import User
from app.schemas.training import (
    AchievementResponse,
    EvaluationResponse,
    MessageResponse,
    ScenarioCreate,
    ScenarioResponse,
    SendMessageRequest,
    SessionCreate,
    SessionDetailResponse,
    SessionResponse,
    SimulateClientResponse,
    TrainingAnalytics,
    WeeklyStatsResponse,
)
from app.services.training_service import TrainingService

router = APIRouter()


# ── Scenarios ─────────────────────────────────────────────────────────────────


@router.get("/scenarios", response_model=list[ScenarioResponse])
async def list_scenarios(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ScenarioResponse]:
    """List all available training scenarios."""
    svc = TrainingService(db)
    scenarios = await svc.list_scenarios(user_id=user.id)
    return [ScenarioResponse.model_validate(s) for s in scenarios]


@router.get("/scenarios/{scenario_id}", response_model=ScenarioResponse)
async def get_scenario(
    scenario_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScenarioResponse:
    """Get a specific training scenario."""
    svc = TrainingService(db)
    scenario = await svc.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found")
    return ScenarioResponse.model_validate(scenario)


@router.post("/scenarios", response_model=ScenarioResponse, status_code=status.HTTP_201_CREATED)
async def create_scenario(
    body: ScenarioCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScenarioResponse:
    """Create a custom training scenario."""
    svc = TrainingService(db)
    scenario = await svc.create_scenario(
        user_id=user.id,
        data=body.model_dump(),
    )
    await db.commit()
    return ScenarioResponse.model_validate(scenario)


# ── Sessions ──────────────────────────────────────────────────────────────────


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: SessionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """Start a new training session for a given scenario."""
    svc = TrainingService(db)
    scenario = await svc.get_scenario(body.scenario_id)
    if not scenario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found")

    session = await svc.create_session(
        user_id=user.id,
        scenario_id=body.scenario_id,
        mode=body.mode,
    )
    await db.commit()
    return SessionResponse.model_validate(session)


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    limit: int = 20,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionResponse]:
    """List user's training sessions."""
    svc = TrainingService(db)
    sessions = await svc.list_user_sessions(user.id, limit=limit, offset=offset)
    return [SessionResponse.model_validate(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionDetailResponse:
    """Get a training session with messages and evaluation."""
    svc = TrainingService(db)
    session = await svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.user_id != user.id and not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return SessionDetailResponse(
        id=session.id,
        user_id=session.user_id,
        scenario_id=session.scenario_id,
        mode=session.mode.value if hasattr(session.mode, "value") else session.mode,
        status=session.status.value if hasattr(session.status, "value") else session.status,
        started_at=session.started_at,
        completed_at=session.completed_at,
        duration_seconds=session.duration_seconds,
        created_at=session.created_at,
        messages=[MessageResponse.model_validate(m) for m in session.messages],
        evaluation=EvaluationResponse.model_validate(session.evaluation) if session.evaluation else None,
        scenario=ScenarioResponse.model_validate(session.scenario) if session.scenario else None,
    )


# ── Chat (Simulate Client) ───────────────────────────────────────────────────


@router.post("/sessions/{session_id}/message", response_model=SimulateClientResponse)
async def send_message(
    session_id: uuid.UUID,
    body: SendMessageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SimulateClientResponse:
    """Send a message in a training session and get AI client response."""
    svc = TrainingService(db)
    session = await svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if session.status != SessionStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is not in progress",
        )

    user_msg, assistant_msg = await svc.simulate_client(session, body.message)
    await db.commit()

    return SimulateClientResponse(
        user_message=MessageResponse.model_validate(user_msg),
        assistant_message=MessageResponse.model_validate(assistant_msg),
    )


# ── Complete & Evaluate ───────────────────────────────────────────────────────


@router.post("/sessions/{session_id}/complete", response_model=EvaluationResponse)
async def complete_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EvaluationResponse:
    """Complete a training session and get AI evaluation."""
    svc = TrainingService(db)
    session = await svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if session.status != SessionStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is already completed or abandoned",
        )
    if not session.messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot evaluate empty session",
        )

    # Complete the session
    await svc.complete_session(session)

    # Evaluate the dialog
    evaluation = await svc.evaluate_session(session)
    await db.commit()

    return EvaluationResponse.model_validate(evaluation)


# ── Analytics ─────────────────────────────────────────────────────────────────


@router.get("/analytics", response_model=TrainingAnalytics)
async def get_analytics(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrainingAnalytics:
    """Get training analytics and progress for the current user."""
    svc = TrainingService(db)
    data = await svc.get_analytics(user.id)

    return TrainingAnalytics(
        total_sessions=data["total_sessions"],
        completed_sessions=data["completed_sessions"],
        avg_score=data["avg_score"],
        best_score=data["best_score"],
        total_duration_minutes=data["total_duration_minutes"],
        criteria_averages=data["criteria_averages"],
        weekly_stats=[WeeklyStatsResponse.model_validate(w) for w in data["weekly_stats"]],
        recent_sessions=[SessionResponse.model_validate(s) for s in data["recent_sessions"]],
        achievements=[AchievementResponse.model_validate(a) for a in data["achievements"]],
    )


# ── Achievements ──────────────────────────────────────────────────────────────


@router.get("/achievements", response_model=list[AchievementResponse])
async def get_achievements(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AchievementResponse]:
    """Get user's training achievements."""
    svc = TrainingService(db)
    data = await svc.get_analytics(user.id)
    return [AchievementResponse.model_validate(a) for a in data["achievements"]]
