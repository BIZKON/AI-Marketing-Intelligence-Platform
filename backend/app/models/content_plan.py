from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.content_task import ContentTask
    from app.models.user import User


class PlanPeriod(str, enum.Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class PlanStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    PUBLISHED = "published"


class ContentPlan(Base):
    __tablename__ = "content_plans"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    ai_response: Mapped[str | None] = mapped_column(Text)
    period: Mapped[PlanPeriod] = mapped_column(
        Enum(PlanPeriod, name="plan_period"),
        nullable=False,
        default=PlanPeriod.WEEKLY,
    )
    status: Mapped[PlanStatus] = mapped_column(
        Enum(PlanStatus, name="plan_status"),
        nullable=False,
        default=PlanStatus.DRAFT,
    )

    # Relationships
    user: Mapped[User] = relationship(back_populates="content_plans")
    tasks: Mapped[list[ContentTask]] = relationship(back_populates="content_plan", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ContentPlan {self.id} period={self.period} status={self.status}>"
