"""Export models — Telegram session management, export jobs, sources, and message metadata.

Part of the Telegram Data Export + RAG Pipeline module (L1 Data Collection).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, Integer,
    String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


# ── Enums ────────────────────────────────────────────────────────────────────


class ExportSourceType(str, enum.Enum):
    CHANNEL = "channel"
    GROUP = "group"
    CHAT = "chat"
    FOLDER = "folder"


class ExportJobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ── TelegramSession ─────────────────────────────────────────────────────────


class TelegramSession(Base):
    """Encrypted Telethon sessions for each user.

    SECURITY: api_hash and session_string are stored Fernet-encrypted.
    The encryption key lives in .env (TELEGRAM_ENCRYPTION_KEY), NOT in the DB.
    """

    __tablename__ = "telegram_sessions"
    __table_args__ = (
        Index("ix_telegram_sessions_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    api_id: Mapped[int] = mapped_column(Integer, nullable=False)
    api_hash_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    session_string_encrypted: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<TelegramSession {self.id} user={self.user_id} phone={self.phone[:4]}***>"


# ── ExportSource ─────────────────────────────────────────────────────────────


class ExportSource(Base):
    """Registered Telegram sources for monitoring and export.

    Links a Telegram entity (channel/group/chat) to a Qdrant collection
    and tracks incremental export state.
    """

    __tablename__ = "export_sources"
    __table_args__ = (
        Index("ix_export_sources_user_id", "user_id"),
        Index("ix_export_sources_telegram_id", "telegram_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_type: Mapped[ExportSourceType] = mapped_column(
        Enum(ExportSourceType, name="export_source_type"),
        nullable=False,
    )
    username: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500), nullable=False)

    # Qdrant collection name for this source's vectors
    qdrant_collection: Mapped[str] = mapped_column(
        String(255), default="telegram_messages",
    )

    # Auto-export configuration
    auto_export: Mapped[bool] = mapped_column(Boolean, default=False)
    export_schedule: Mapped[str | None] = mapped_column(String(50))  # Cron expression
    last_export_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_id: Mapped[int | None] = mapped_column(BigInteger)  # For incremental export

    # Aggregate statistics
    total_messages: Mapped[int] = mapped_column(Integer, default=0)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)
    total_authors: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:
        return f"<ExportSource {self.id} tg_id={self.telegram_id} @{self.username}>"


# ── ExportJob ────────────────────────────────────────────────────────────────


class ExportJob(Base):
    """Export task — tracks progress and history of each export run."""

    __tablename__ = "export_jobs"
    __table_args__ = (
        Index("ix_export_jobs_user_id", "user_id"),
        Index("ix_export_jobs_status", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("telegram_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("export_sources.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Target info
    source_type: Mapped[ExportSourceType] = mapped_column(
        Enum(ExportSourceType, name="export_source_type", create_type=False),
        nullable=False,
    )
    source_tg_id: Mapped[str] = mapped_column(String(255), nullable=False)  # TG ID or username
    source_name: Mapped[str] = mapped_column(String(500), nullable=False)

    # Export configuration snapshot
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Status tracking
    status: Mapped[ExportJobStatus] = mapped_column(
        Enum(ExportJobStatus, name="export_job_status"),
        default=ExportJobStatus.PENDING,
    )

    # Progress
    total_messages: Mapped[int | None] = mapped_column(Integer)
    processed_messages: Mapped[int] = mapped_column(Integer, default=0)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(Text)

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<ExportJob {self.id} status={self.status} source={self.source_name}>"


# ── MessageMeta ──────────────────────────────────────────────────────────────


class MessageMeta(Base):
    """Per-message metadata stored in PostgreSQL for efficient analytics.

    Qdrant stores the vector + text chunks; PostgreSQL stores structured
    metadata that's more efficient to aggregate (top authors, activity, etc.).
    """

    __tablename__ = "message_meta"
    __table_args__ = (
        Index("ix_message_meta_source_id", "source_id"),
        Index("ix_message_meta_export_job_id", "export_job_id"),
        Index("ix_message_meta_author_tg_id", "author_telegram_id"),
        Index("ix_message_meta_date", "date"),
        Index("ix_message_meta_reactions", "reactions_count"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("export_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    export_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("export_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    author_telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    author_username: Mapped[str | None] = mapped_column(String(255))
    author_name: Mapped[str | None] = mapped_column(String(500))

    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reactions_count: Mapped[int] = mapped_column(Integer, default=0)
    views_count: Mapped[int] = mapped_column(Integer, default=0)
    forwards_count: Mapped[int] = mapped_column(Integer, default=0)
    replies_count: Mapped[int] = mapped_column(Integer, default=0)

    has_media: Mapped[bool] = mapped_column(Boolean, default=False)
    media_type: Mapped[str | None] = mapped_column(String(50))
    has_transcription: Mapped[bool] = mapped_column(Boolean, default=False)

    text_length: Mapped[int] = mapped_column(Integer, default=0)
    chunks_count: Mapped[int] = mapped_column(Integer, default=0)
    qdrant_point_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)

    def __repr__(self) -> str:
        return f"<MessageMeta {self.id} msg_id={self.telegram_message_id} source={self.source_id}>"
