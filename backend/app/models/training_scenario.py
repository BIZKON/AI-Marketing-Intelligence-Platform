"""Training scenario model — predefined sales training scenarios."""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Enum, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.training_session import TrainingSession
    from app.models.user import User


class ScenarioType(str, enum.Enum):
    INCOMING_CALL = "incoming_call"
    OUTBOUND_CALL = "outbound_call"
    PARTNER_PITCH = "partner_pitch"
    OBJECTION_HANDLING = "objection_handling"
    CLOSING = "closing"


class ScenarioDifficulty(str, enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class TrainingScenario(Base):
    __tablename__ = "training_scenarios"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    type: Mapped[ScenarioType] = mapped_column(
        Enum(ScenarioType, name="scenario_type_enum"),
        nullable=False,
    )
    difficulty: Mapped[ScenarioDifficulty] = mapped_column(
        Enum(ScenarioDifficulty, name="scenario_difficulty_enum"),
        default=ScenarioDifficulty.MEDIUM,
    )

    # Client persona as JSON
    client_persona: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # System prompt for the AI client
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)

    # Reference ideal script
    ideal_script: Mapped[str | None] = mapped_column(Text)

    # Success criteria as JSON
    success_criteria: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Creator
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)))

    # Relationships
    sessions: Mapped[list[TrainingSession]] = relationship(
        back_populates="scenario",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<TrainingScenario {self.id} title={self.title!r}>"
