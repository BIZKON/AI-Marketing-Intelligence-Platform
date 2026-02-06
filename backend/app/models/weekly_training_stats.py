"""Weekly training stats model — aggregated weekly performance metrics."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class WeeklyTrainingStats(Base):
    __tablename__ = "weekly_training_stats"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start", name="uq_weekly_stats_user_week"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    sessions_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    total_duration_minutes: Mapped[int] = mapped_column(Integer, default=0)
    top_scenario_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<WeeklyTrainingStats {self.id} user={self.user_id} week={self.week_start}>"
