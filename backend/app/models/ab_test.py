"""A/B test model — compare two script variants head-to-head."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.ab_test_result import ABTestResult


class ABTest(Base):
    __tablename__ = "ab_tests"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    variant_a: Mapped[str] = mapped_column(Text, nullable=False)
    variant_b: Mapped[str] = mapped_column(Text, nullable=False)
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_scenarios.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    results: Mapped[list[ABTestResult]] = relationship(
        back_populates="test",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ABTest {self.id} title={self.title!r}>"
