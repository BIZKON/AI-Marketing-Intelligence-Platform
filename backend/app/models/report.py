from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class ReportType(str, enum.Enum):
    DIGEST = "digest"
    ALERT = "alert"
    STRATEGY = "strategy"
    VOICE = "voice"
    VIDEO = "video"


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_user_type", "user_id", "type"),
        Index("ix_reports_type", "type"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[ReportType] = mapped_column(
        Enum(ReportType, name="report_type"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    content_markdown: Mapped[str | None] = mapped_column(Text)
    media_url: Mapped[str | None] = mapped_column(Text)

    # Relationships
    user: Mapped[User] = relationship(back_populates="reports")

    def __repr__(self) -> str:
        return f"<Report {self.id} type={self.type}>"
