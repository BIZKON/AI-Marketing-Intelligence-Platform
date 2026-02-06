"""Add v2-v4 tables: A/B tests, multiplayer, CRM, VoIP, gamification v2.

Revision ID: 003_v2_v4
Revises: 002_training
Create Date: 2026-02-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003_v2_v4"
down_revision = "002_training"
branch_labels = None
depends_on = None

multiplayer_status_enum = postgresql.ENUM(
    "waiting", "in_progress", "completed",
    name="multiplayer_status_enum", create_type=False,
)


def upgrade() -> None:
    multiplayer_status_enum.create(op.get_bind(), checkfirst=True)

    # ab_tests
    op.create_table(
        "ab_tests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("variant_a", sa.Text, nullable=False),
        sa.Column("variant_b", sa.Text, nullable=False),
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("training_scenarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ab_test_results
    op.create_table(
        "ab_test_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("test_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ab_tests.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("variant", sa.String(1), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("training_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("score", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # multiplayer_sessions
    op.create_table(
        "multiplayer_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_code", sa.String(10), unique=True, nullable=False),
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("training_scenarios.id"), nullable=False),
        sa.Column("host_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", multiplayer_status_enum, server_default="waiting"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # multiplayer_participants
    op.create_table(
        "multiplayer_participants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("multiplayer_session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("multiplayer_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("training_session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("training_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("final_score", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("multiplayer_session_id", "user_id", name="uq_mp_session_user"),
    )

    # crm_clients
    op.create_table(
        "crm_clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("amocrm_contact_id", sa.BigInteger, unique=True, nullable=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String(100)), nullable=True),
        sa.Column("custom_fields", postgresql.JSONB, nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # voip_recordings
    op.create_table(
        "voip_recordings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("call_id", sa.String(255), unique=True, nullable=False),
        sa.Column("from_number", sa.String(50), nullable=True),
        sa.Column("to_number", sa.String(50), nullable=True),
        sa.Column("direction", sa.String(20), nullable=True),
        sa.Column("audio_url", sa.Text, nullable=False),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("real_call_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # daily_challenges
    op.create_table(
        "daily_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("challenge_type", sa.String(50), nullable=False),
        sa.Column("target", sa.Integer, nullable=False),
        sa.Column("current_progress", sa.Integer, server_default="0"),
        sa.Column("reward_coins", sa.Integer, server_default="0"),
        sa.Column("label", sa.String(500), nullable=False),
        sa.Column("challenge_date", sa.Date, nullable=False),
        sa.Column("is_completed", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # user_gamification
    op.create_table(
        "user_gamification",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("level", sa.String(50), server_default="trainee"),
        sa.Column("xp", sa.Integer, server_default="0"),
        sa.Column("coins", sa.Integer, server_default="0"),
        sa.Column("current_streak", sa.Integer, server_default="0"),
        sa.Column("longest_streak", sa.Integer, server_default="0"),
        sa.Column("last_active_date", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("user_gamification")
    op.drop_table("daily_challenges")
    op.drop_table("voip_recordings")
    op.drop_table("crm_clients")
    op.drop_table("multiplayer_participants")
    op.drop_table("multiplayer_sessions")
    op.drop_table("ab_test_results")
    op.drop_table("ab_tests")
    multiplayer_status_enum.drop(op.get_bind(), checkfirst=True)
