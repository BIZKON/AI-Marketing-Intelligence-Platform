from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.competitor import Competitor
    from app.models.content_plan import ContentPlan
    from app.models.content_task import ContentTask
    from app.models.report import Report
    from app.models.subscription import Subscription


class User(Base):
    __tablename__ = "users"

    # Telegram
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True)
    telegram_username: Mapped[str | None] = mapped_column(String(255))

    # Auth
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(Text)

    # Profile
    full_name: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")
    language: Mapped[str] = mapped_column(String(10), default="ru")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)

    # Brand profile for AI content generation
    brand_name: Mapped[str | None] = mapped_column(String(255))
    brand_description: Mapped[str | None] = mapped_column(Text)
    tone_of_voice: Mapped[str | None] = mapped_column(Text)

    # Stripe
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), unique=True)

    # Relationships
    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="user", cascade="all, delete-orphan")
    competitors: Mapped[list[Competitor]] = relationship(back_populates="user", cascade="all, delete-orphan")
    reports: Mapped[list[Report]] = relationship(back_populates="user", cascade="all, delete-orphan")
    content_plans: Mapped[list[ContentPlan]] = relationship(back_populates="user", cascade="all, delete-orphan")
    content_tasks: Mapped[list[ContentTask]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User {self.id} tg={self.telegram_id}>"
