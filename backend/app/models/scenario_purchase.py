"""Scenario purchase model — tracks one-time purchases of premium training scenarios."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ScenarioPurchase(Base):
    __tablename__ = "scenario_purchases"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_scenarios.id", ondelete="CASCADE"),
        nullable=False,
    )
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="usd")

    def __repr__(self) -> str:
        return f"<ScenarioPurchase {self.id} user={self.user_id} scenario={self.scenario_id}>"
