from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.competitor_post import CompetitorPost
    from app.models.user import User


class Competitor(Base):
    __tablename__ = "competitors"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Platforms being tracked (e.g., ["telegram", "youtube", "vk"])
    platforms: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # Platform-specific tracking configuration
    # e.g., {"telegram": {"channel": "@competitor"}, "youtube": {"channel_id": "UC..."}}
    tracking_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Relationships
    user: Mapped[User] = relationship(back_populates="competitors")
    posts: Mapped[list[CompetitorPost]] = relationship(back_populates="competitor", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Competitor {self.id} name={self.name}>"
