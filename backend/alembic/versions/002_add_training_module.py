"""Add training module tables — scenarios, sessions, messages, evaluations, achievements, weekly stats.

Revision ID: 002_training
Revises: 001_initial
Create Date: 2026-02-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002_training"
down_revision = "001_initial"
branch_labels = None
depends_on = None

# Enum types
scenario_type_enum = postgresql.ENUM(
    "incoming_call", "outbound_call", "partner_pitch", "objection_handling", "closing",
    name="scenario_type_enum", create_type=False,
)
scenario_difficulty_enum = postgresql.ENUM(
    "easy", "medium", "hard",
    name="scenario_difficulty_enum", create_type=False,
)
session_mode_enum = postgresql.ENUM(
    "text", "voice", "real_call_analysis",
    name="session_mode_enum", create_type=False,
)
session_status_enum = postgresql.ENUM(
    "in_progress", "completed", "abandoned",
    name="session_status_enum", create_type=False,
)


def upgrade() -> None:
    # Create enum types
    scenario_type_enum.create(op.get_bind(), checkfirst=True)
    scenario_difficulty_enum.create(op.get_bind(), checkfirst=True)
    session_mode_enum.create(op.get_bind(), checkfirst=True)
    session_status_enum.create(op.get_bind(), checkfirst=True)

    # training_scenarios
    op.create_table(
        "training_scenarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("type", scenario_type_enum, nullable=False),
        sa.Column("difficulty", scenario_difficulty_enum, nullable=False, server_default="medium"),
        sa.Column("client_persona", postgresql.JSONB, nullable=False),
        sa.Column("system_prompt", sa.Text, nullable=False),
        sa.Column("ideal_script", sa.Text, nullable=True),
        sa.Column("success_criteria", postgresql.JSONB, nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_public", sa.Boolean, server_default="true"),
        sa.Column("tags", postgresql.ARRAY(sa.String(100)), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # training_sessions
    op.create_table(
        "training_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
        ),
        sa.Column(
            "scenario_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("training_scenarios.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("mode", session_mode_enum, nullable=False, server_default="text"),
        sa.Column("status", session_status_enum, nullable=False, server_default="in_progress"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # session_messages
    op.create_table(
        "session_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False, index=True,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # session_evaluations
    op.create_table(
        "session_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False, unique=True,
        ),
        sa.Column("overall_score", sa.Integer, nullable=True),
        sa.Column("criteria_scores", postgresql.JSONB, nullable=False),
        sa.Column("strengths", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("improvements", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("detailed_feedback", sa.Text, nullable=True),
        sa.Column("mood_analysis", sa.String(50), nullable=True),
        sa.Column("evaluator", sa.String(100), server_default="claude-sonnet-4-20250514"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # training_achievements
    op.create_table(
        "training_achievements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
        ),
        sa.Column("achievement_type", sa.String(100), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # weekly_training_stats
    op.create_table(
        "weekly_training_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
        ),
        sa.Column("week_start", sa.Date, nullable=False),
        sa.Column("sessions_count", sa.Integer, server_default="0"),
        sa.Column("avg_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("total_duration_minutes", sa.Integer, server_default="0"),
        sa.Column("top_scenario_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "week_start", name="uq_weekly_stats_user_week"),
    )


def downgrade() -> None:
    op.drop_table("weekly_training_stats")
    op.drop_table("training_achievements")
    op.drop_table("session_evaluations")
    op.drop_table("session_messages")
    op.drop_table("training_sessions")
    op.drop_table("training_scenarios")

    session_status_enum.drop(op.get_bind(), checkfirst=True)
    session_mode_enum.drop(op.get_bind(), checkfirst=True)
    scenario_difficulty_enum.drop(op.get_bind(), checkfirst=True)
    scenario_type_enum.drop(op.get_bind(), checkfirst=True)
