"""Multiplayer session model — competitive training between users."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.multiplayer_participant import MultiplayerParticipant


class MultiplayerStatus(str, enum.Enum):
    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class MultiplayerSession(Base):
    __tablename__ = "multiplayer_sessions"

    session_code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_scenarios.id"),
        nullable=False,
    )
    host_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    status: Mapped[MultiplayerStatus] = mapped_column(
        Enum(MultiplayerStatus, name="multiplayer_status_enum"),
        default=MultiplayerStatus.WAITING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    participants: Mapped[list[MultiplayerParticipant]] = relationship(
        back_populates="multiplayer_session",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<MultiplayerSession {self.id} code={self.session_code}>"
