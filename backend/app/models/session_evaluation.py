"""Session evaluation model — AI-generated assessment of training sessions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.training_session import TrainingSession


class SessionEvaluation(Base):
    __tablename__ = "session_evaluations"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    overall_score: Mapped[int | None] = mapped_column(Integer)  # 0-100
    criteria_scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    strengths: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    improvements: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    detailed_feedback: Mapped[str | None] = mapped_column(Text)
    mood_analysis: Mapped[str | None] = mapped_column(String(50))  # happy, neutral, frustrated
    evaluator: Mapped[str] = mapped_column(
        String(100),
        default="claude-sonnet-4-20250514",
    )

    # Relationships
    session: Mapped[TrainingSession] = relationship(back_populates="evaluation")

    def __repr__(self) -> str:
        return f"<SessionEvaluation {self.id} score={self.overall_score}>"
