"""Add Telegram Export tables: sessions, sources, jobs, message_meta.

Revision ID: 004_telegram_export
Revises: 003_v2_v4
Create Date: 2026-02-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004_telegram_export"
down_revision = "003_v2_v4"
branch_labels = None
depends_on = None

export_source_type_enum = postgresql.ENUM(
    "channel", "group", "chat", "folder",
    name="export_source_type", create_type=False,
)

export_job_status_enum = postgresql.ENUM(
    "pending", "processing", "chunking", "embedding",
    "completed", "failed", "cancelled",
    name="export_job_status", create_type=False,
)


def upgrade() -> None:
    export_source_type_enum.create(op.get_bind(), checkfirst=True)
    export_job_status_enum.create(op.get_bind(), checkfirst=True)

    # telegram_sessions
    op.create_table(
        "telegram_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("api_id", sa.Integer, nullable=False),
        sa.Column("api_hash_encrypted", sa.Text, nullable=False),
        sa.Column("session_string_encrypted", sa.Text),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_telegram_sessions_user_id", "telegram_sessions", ["user_id"])

    # export_sources
    op.create_table(
        "export_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("telegram_id", sa.BigInteger, nullable=False),
        sa.Column("telegram_type", export_source_type_enum, nullable=False),
        sa.Column("username", sa.String(255)),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("qdrant_collection", sa.String(255),
                  server_default=sa.text("'telegram_messages'")),
        sa.Column("auto_export", sa.Boolean, server_default=sa.text("false")),
        sa.Column("export_schedule", sa.String(50)),
        sa.Column("last_export_at", sa.DateTime(timezone=True)),
        sa.Column("last_message_id", sa.BigInteger),
        sa.Column("total_messages", sa.Integer, server_default=sa.text("0")),
        sa.Column("total_chunks", sa.Integer, server_default=sa.text("0")),
        sa.Column("total_authors", sa.Integer, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_export_sources_user_id", "export_sources", ["user_id"])
    op.create_index("ix_export_sources_telegram_id", "export_sources", ["telegram_id"])

    # export_jobs
    op.create_table(
        "export_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("telegram_sessions.id", ondelete="SET NULL")),
        sa.Column("source_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("export_sources.id", ondelete="SET NULL")),
        sa.Column("source_type", export_source_type_enum, nullable=False),
        sa.Column("source_tg_id", sa.String(255), nullable=False),
        sa.Column("source_name", sa.String(500), nullable=False),
        sa.Column("config", postgresql.JSONB, server_default=sa.text("'{}'")),
        sa.Column("status", export_job_status_enum,
                  server_default=sa.text("'pending'")),
        sa.Column("total_messages", sa.Integer),
        sa.Column("processed_messages", sa.Integer, server_default=sa.text("0")),
        sa.Column("total_chunks", sa.Integer, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_export_jobs_user_id", "export_jobs", ["user_id"])
    op.create_index("ix_export_jobs_status", "export_jobs", ["status"])

    # message_meta
    op.create_table(
        "message_meta",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("export_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("export_job_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("export_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger, nullable=False),
        sa.Column("author_telegram_id", sa.BigInteger),
        sa.Column("author_username", sa.String(255)),
        sa.Column("author_name", sa.String(500)),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reactions_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("views_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("forwards_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("replies_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("has_media", sa.Boolean, server_default=sa.text("false")),
        sa.Column("media_type", sa.String(50)),
        sa.Column("has_transcription", sa.Boolean, server_default=sa.text("false")),
        sa.Column("text_length", sa.Integer, server_default=sa.text("0")),
        sa.Column("chunks_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("qdrant_point_ids", postgresql.JSONB, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_message_meta_source_id", "message_meta", ["source_id"])
    op.create_index("ix_message_meta_export_job_id", "message_meta", ["export_job_id"])
    op.create_index("ix_message_meta_author_tg_id", "message_meta", ["author_telegram_id"])
    op.create_index("ix_message_meta_date", "message_meta", ["date"])
    op.create_index("ix_message_meta_reactions", "message_meta", ["reactions_count"])


def downgrade() -> None:
    op.drop_table("message_meta")
    op.drop_table("export_jobs")
    op.drop_table("export_sources")
    op.drop_table("telegram_sessions")

    export_job_status_enum.drop(op.get_bind(), checkfirst=True)
    export_source_type_enum.drop(op.get_bind(), checkfirst=True)
