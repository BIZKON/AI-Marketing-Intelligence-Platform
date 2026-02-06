"""CompetitorPost model — stores raw content collected from competitor platforms."""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.competitor import Competitor


class Platform(str, enum.Enum):
    TELEGRAM = "telegram"
    YOUTUBE = "youtube"
    VK = "vk"
    WEBSITE = "website"
    INSTAGRAM = "instagram"


class CompetitorPost(Base):
    __tablename__ = "competitor_posts"
    __table_args__ = (
        Index("ix_competitor_posts_competitor_platform", "competitor_id", "platform"),
        Index("ix_competitor_posts_published_at", "published_at"),
        Index("ix_competitor_posts_simhash", "simhash"),
        UniqueConstraint("external_id", "platform", name="uq_competitor_posts_external_id_platform"),
    )

    competitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("competitors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[Platform] = mapped_column(
        Enum(Platform, name="platform_type"),
        nullable=False,
    )

    # Content
    external_id: Mapped[str | None] = mapped_column(String(500))
    title: Mapped[str | None] = mapped_column(String(1000))
    text_content: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    media_urls: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # Metrics
    views: Mapped[int] = mapped_column(BigInteger, default=0)
    likes: Mapped[int] = mapped_column(BigInteger, default=0)
    comments: Mapped[int] = mapped_column(BigInteger, default=0)
    shares: Mapped[int] = mapped_column(BigInteger, default=0)
    engagement_rate: Mapped[float | None] = mapped_column(default=None)

    # Metadata
    published_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Deduplication
    simhash: Mapped[str | None] = mapped_column(String(64))

    # Vector DB reference
    qdrant_point_id: Mapped[str | None] = mapped_column(String(255))

    # Relationships
    competitor: Mapped[Competitor] = relationship(back_populates="posts")

    def __repr__(self) -> str:
        return f"<CompetitorPost {self.id} platform={self.platform} external_id={self.external_id}>"
