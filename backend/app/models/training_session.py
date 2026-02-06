"""Training session model — individual training runs."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.training_scenario import TrainingScenario
    from app.models.session_message import SessionMessage
    from app.models.session_evaluation import SessionEvaluation
    from app.models.user import User


class SessionMode(str, enum.Enum):
    TEXT = "text"
    VOICE = "voice"
    REAL_CALL_ANALYSIS = "real_call_analysis"


class SessionStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class TrainingSession(Base):
    __tablename__ = "training_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_scenarios.id", ondelete="SET NULL"),
        nullable=True,
    )
    mode: Mapped[SessionMode] = mapped_column(
        Enum(SessionMode, name="session_mode_enum"),
        nullable=False,
        default=SessionMode.TEXT,
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status_enum"),
        default=SessionStatus.IN_PROGRESS,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Relationships
    scenario: Mapped[TrainingScenario | None] = relationship(
        back_populates="sessions",
    )
    messages: Mapped[list[SessionMessage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SessionMessage.created_at",
    )
    evaluation: Mapped[SessionEvaluation | None] = relationship(
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<TrainingSession {self.id} user={self.user_id} status={self.status}>"
