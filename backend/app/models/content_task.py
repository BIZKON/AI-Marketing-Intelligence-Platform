from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.competitor_post import Platform

if TYPE_CHECKING:
    from app.models.content_plan import ContentPlan
    from app.models.user import User


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    PUBLISHED = "published"


class ContentTask(Base):
    __tablename__ = "content_tasks"
    __table_args__ = (
        Index("ix_content_tasks_user_status", "user_id", "status"),
        Index("ix_content_tasks_user_created", "user_id", "created_at"),
        Index("ix_content_tasks_status", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_plans.id", ondelete="SET NULL"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    platform: Mapped[Platform] = mapped_column(
        Enum(Platform, name="platform_type", create_type=False),
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(String(50), default="text")
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"),
        nullable=False,
        default=TaskStatus.PENDING,
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    user: Mapped[User] = relationship(back_populates="content_tasks")
    content_plan: Mapped[ContentPlan | None] = relationship(back_populates="tasks")

    def __repr__(self) -> str:
        return f"<ContentTask {self.id} title={self.title!r} status={self.status}>"
