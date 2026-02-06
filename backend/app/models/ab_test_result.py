"""A/B test result model — individual test run results."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.ab_test import ABTest


class ABTestResult(Base):
    __tablename__ = "ab_test_results"

    test_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ab_tests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    variant: Mapped[str] = mapped_column(String(1), nullable=False)  # 'a' or 'b'
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    score: Mapped[int | None] = mapped_column(Integer)

    # Relationships
    test: Mapped[ABTest] = relationship(back_populates="results")

    def __repr__(self) -> str:
        return f"<ABTestResult {self.id} variant={self.variant} score={self.score}>"
