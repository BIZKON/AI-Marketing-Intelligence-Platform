"""Multiplayer training service — competitive sessions between users."""

from __future__ import annotations

import logging
import random
import string
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.multiplayer_participant import MultiplayerParticipant
from app.models.multiplayer_session import MultiplayerSession, MultiplayerStatus

logger = logging.getLogger(__name__)


class MultiplayerService:
    """Manage multiplayer training sessions."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _generate_code() -> str:
        return "".join(random.choices(string.digits, k=6))

    async def create_session(
        self, host_user_id: uuid.UUID, scenario_id: uuid.UUID
    ) -> MultiplayerSession:
        code = self._generate_code()
        session = MultiplayerSession(
            session_code=code,
            scenario_id=scenario_id,
            host_user_id=host_user_id,
            status=MultiplayerStatus.WAITING,
        )
        self.db.add(session)
        await self.db.flush()

        # Add host as participant
        participant = MultiplayerParticipant(
            multiplayer_session_id=session.id,
            user_id=host_user_id,
        )
        self.db.add(participant)
        await self.db.flush()
        await self.db.refresh(session)
        return session

    async def join_session(
        self, session_code: str, user_id: uuid.UUID
    ) -> MultiplayerSession | None:
        result = await self.db.execute(
            select(MultiplayerSession)
            .options(selectinload(MultiplayerSession.participants))
            .where(MultiplayerSession.session_code == session_code)
        )
        session = result.scalar_one_or_none()
        if not session or session.status != MultiplayerStatus.WAITING:
            return None

        # Check if already joined
        existing = await self.db.execute(
            select(MultiplayerParticipant).where(
                MultiplayerParticipant.multiplayer_session_id == session.id,
                MultiplayerParticipant.user_id == user_id,
            )
        )
        if existing.scalar_one_or_none():
            return session

        participant = MultiplayerParticipant(
            multiplayer_session_id=session.id,
            user_id=user_id,
        )
        self.db.add(participant)
        await self.db.flush()
        await self.db.refresh(session)
        return session

    async def start_session(self, session_id: uuid.UUID) -> MultiplayerSession | None:
        result = await self.db.execute(
            select(MultiplayerSession).where(MultiplayerSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            return None
        session.status = MultiplayerStatus.IN_PROGRESS
        session.started_at = datetime.utcnow()
        await self.db.flush()
        return session

    async def complete_session(self, session_id: uuid.UUID) -> MultiplayerSession | None:
        result = await self.db.execute(
            select(MultiplayerSession)
            .options(selectinload(MultiplayerSession.participants))
            .where(MultiplayerSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            return None
        session.status = MultiplayerStatus.COMPLETED
        session.completed_at = datetime.utcnow()
        await self.db.flush()
        return session

    async def get_session(self, session_id: uuid.UUID) -> MultiplayerSession | None:
        result = await self.db.execute(
            select(MultiplayerSession)
            .options(selectinload(MultiplayerSession.participants))
            .where(MultiplayerSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def set_participant_score(
        self, session_id: uuid.UUID, user_id: uuid.UUID,
        training_session_id: uuid.UUID, score: int
    ) -> None:
        result = await self.db.execute(
            select(MultiplayerParticipant).where(
                MultiplayerParticipant.multiplayer_session_id == session_id,
                MultiplayerParticipant.user_id == user_id,
            )
        )
        participant = result.scalar_one_or_none()
        if participant:
            participant.training_session_id = training_session_id
            participant.final_score = score
            await self.db.flush()

    async def get_leaderboard(self, limit: int = 10) -> list[dict]:
        """Get top users by average multiplayer scores."""
        from sqlalchemy import func, desc
        result = await self.db.execute(
            select(
                MultiplayerParticipant.user_id,
                func.avg(MultiplayerParticipant.final_score).label("avg_score"),
                func.count(MultiplayerParticipant.id).label("games_played"),
            )
            .where(MultiplayerParticipant.final_score.isnot(None))
            .group_by(MultiplayerParticipant.user_id)
            .order_by(desc("avg_score"))
            .limit(limit)
        )
        return [
            {"user_id": str(row[0]), "avg_score": float(row[1]), "games_played": row[2]}
            for row in result.all()
        ]
