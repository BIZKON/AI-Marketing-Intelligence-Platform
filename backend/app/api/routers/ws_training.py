"""WebSocket endpoint for real-time training chat sessions.

Clients connect to /ws/training/{session_id}?token=JWT and exchange messages
in real-time instead of polling the REST API.
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.security import ALGORITHM
from app.models.training_session import SessionStatus, TrainingSession
from app.services.training_service import TrainingService

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


async def _authenticate_ws(token: str) -> str | None:
    """Validate JWT token and return user_id, or None if invalid."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id: str | None = payload.get("sub")
        if user_id and payload.get("type") != "refresh":
            return user_id
    except JWTError:
        pass
    return None


@router.websocket("/ws/training/{session_id}")
async def training_ws(
    websocket: WebSocket,
    session_id: uuid.UUID,
    token: str = Query(...),
) -> None:
    """Real-time training chat via WebSocket.

    Protocol:
    - Client sends: {"type": "message", "content": "text"}
    - Server replies: {"type": "response", "user_message": {...}, "assistant_message": {...}}
    - Client sends: {"type": "complete"}
    - Server replies: {"type": "evaluation", "evaluation": {...}}
    - Server sends: {"type": "error", "detail": "..."} on errors
    """
    # Authenticate
    user_id = await _authenticate_ws(token)
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()

    async with async_session_factory() as db:
        # Verify session ownership
        result = await db.execute(
            select(TrainingSession)
            .options(
                selectinload(TrainingSession.messages),
                selectinload(TrainingSession.scenario),
                selectinload(TrainingSession.evaluation),
            )
            .where(TrainingSession.id == session_id)
        )
        session = result.scalar_one_or_none()

        if not session:
            await websocket.send_json({"type": "error", "detail": "Session not found"})
            await websocket.close(code=4004)
            return

        if str(session.user_id) != user_id:
            await websocket.send_json({"type": "error", "detail": "Access denied"})
            await websocket.close(code=4003)
            return

        if session.status != SessionStatus.IN_PROGRESS:
            await websocket.send_json({"type": "error", "detail": "Session is not in progress"})
            await websocket.close(code=4002)
            return

        # Send session info on connect
        await websocket.send_json({
            "type": "connected",
            "session_id": str(session.id),
            "scenario_title": session.scenario.title if session.scenario else None,
            "message_count": len(session.messages),
        })

        svc = TrainingService(db)

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "detail": "Invalid JSON"})
                    continue

                msg_type = data.get("type")

                if msg_type == "message":
                    content = data.get("content", "").strip()
                    if not content:
                        await websocket.send_json({"type": "error", "detail": "Empty message"})
                        continue

                    # Reload session messages for context
                    result = await db.execute(
                        select(TrainingSession)
                        .options(
                            selectinload(TrainingSession.messages),
                            selectinload(TrainingSession.scenario),
                        )
                        .where(TrainingSession.id == session_id)
                    )
                    session = result.scalar_one_or_none()

                    user_msg, assistant_msg = await svc.simulate_client(session, content)
                    await db.commit()

                    await websocket.send_json({
                        "type": "response",
                        "user_message": {
                            "id": str(user_msg.id),
                            "role": user_msg.role,
                            "content": user_msg.content,
                            "created_at": user_msg.created_at.isoformat(),
                        },
                        "assistant_message": {
                            "id": str(assistant_msg.id),
                            "role": assistant_msg.role,
                            "content": assistant_msg.content,
                            "created_at": assistant_msg.created_at.isoformat(),
                        },
                    })

                elif msg_type == "complete":
                    # Reload with messages
                    result = await db.execute(
                        select(TrainingSession)
                        .options(
                            selectinload(TrainingSession.messages),
                            selectinload(TrainingSession.scenario),
                        )
                        .where(TrainingSession.id == session_id)
                    )
                    session = result.scalar_one_or_none()

                    if not session.messages:
                        await websocket.send_json({
                            "type": "error",
                            "detail": "Cannot evaluate empty session",
                        })
                        continue

                    await svc.complete_session(session)
                    evaluation = await svc.evaluate_session(session)
                    await db.commit()

                    await websocket.send_json({
                        "type": "evaluation",
                        "evaluation": {
                            "overall_score": evaluation.overall_score,
                            "criteria_scores": evaluation.criteria_scores,
                            "strengths": evaluation.strengths,
                            "improvements": evaluation.improvements,
                            "detailed_feedback": evaluation.detailed_feedback,
                            "mood_analysis": evaluation.mood_analysis,
                        },
                    })
                    # Session complete — close connection
                    await websocket.close(code=1000)
                    return

                else:
                    await websocket.send_json({
                        "type": "error",
                        "detail": f"Unknown message type: {msg_type}",
                    })

        except WebSocketDisconnect:
            logger.info("WebSocket disconnected for session %s", session_id)
        except Exception:
            logger.exception("WebSocket error for session %s", session_id)
            try:
                await websocket.send_json({"type": "error", "detail": "Internal server error"})
                await websocket.close(code=1011)
            except Exception:
                pass
