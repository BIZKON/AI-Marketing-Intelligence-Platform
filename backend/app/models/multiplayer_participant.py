"""Multiplayer participant model — users in a multiplayer session."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.multiplayer_session import MultiplayerSession


class MultiplayerParticipant(Base):
    __tablename__ = "multiplayer_participants"
    __table_args__ = (
        UniqueConstraint("multiplayer_session_id", "user_id", name="uq_mp_session_user"),
    )

    multiplayer_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("multiplayer_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    training_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    final_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    multiplayer_session: Mapped[MultiplayerSession] = relationship(
        back_populates="participants",
    )

    def __repr__(self) -> str:
        return f"<MultiplayerParticipant {self.id} user={self.user_id}>"
