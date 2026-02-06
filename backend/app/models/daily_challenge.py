"""Daily challenge model — gamification v2 daily/weekly challenges."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DailyChallenge(Base):
    __tablename__ = "daily_challenges"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    challenge_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target: Mapped[int] = mapped_column(Integer, nullable=False)
    current_progress: Mapped[int] = mapped_column(Integer, default=0)
    reward_coins: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str] = mapped_column(String(500), nullable=False)
    challenge_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self) -> str:
        return f"<DailyChallenge {self.id} type={self.challenge_type}>"
