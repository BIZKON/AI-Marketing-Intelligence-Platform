"""Initial schema — all tables for AI Marketing Intelligence Platform.

Revision ID: 001_initial
Revises:
Create Date: 2026-02-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None

# Enum types
plan_type = postgresql.ENUM("monitor", "creator", "autopilot", "enterprise", name="plan_type", create_type=False)
subscription_status = postgresql.ENUM("active", "past_due", "canceled", "trialing", name="subscription_status", create_type=False)
platform_type = postgresql.ENUM("telegram", "youtube", "vk", "website", "instagram", name="platform_type", create_type=False)
report_type = postgresql.ENUM("digest", "alert", "strategy", "voice", "video", name="report_type", create_type=False)
plan_period = postgresql.ENUM("weekly", "monthly", name="plan_period", create_type=False)
plan_status = postgresql.ENUM("draft", "approved", "published", name="plan_status", create_type=False)
task_status = postgresql.ENUM("pending", "draft", "in_review", "approved", "published", name="task_status", create_type=False)


def upgrade() -> None:
    # Create enum types
    plan_type.create(op.get_bind(), checkfirst=True)
    subscription_status.create(op.get_bind(), checkfirst=True)
    platform_type.create(op.get_bind(), checkfirst=True)
    report_type.create(op.get_bind(), checkfirst=True)
    plan_period.create(op.get_bind(), checkfirst=True)
    plan_status.create(op.get_bind(), checkfirst=True)
    task_status.create(op.get_bind(), checkfirst=True)

    # ── Users ────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), unique=True, index=True, nullable=True),
        sa.Column("telegram_username", sa.String(255), nullable=True),
        sa.Column("email", sa.String(320), unique=True, index=True, nullable=True),
        sa.Column("hashed_password", sa.Text(), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("timezone", sa.String(50), server_default="UTC", nullable=False),
        sa.Column("language", sa.String(10), server_default="ru", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("brand_name", sa.String(255), nullable=True),
        sa.Column("brand_industry", sa.String(255), nullable=True),
        sa.Column("brand_description", sa.Text(), nullable=True),
        sa.Column("tone_of_voice", sa.Text(), nullable=True),
        sa.Column("stripe_customer_id", sa.String(255), unique=True, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── Subscriptions ────────────────────────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("plan", plan_type, nullable=False, server_default="monitor"),
        sa.Column("status", subscription_status, nullable=False, server_default="active"),
        sa.Column("stripe_subscription_id", sa.String(255), unique=True, nullable=True),
        sa.Column("stripe_price_id", sa.String(255), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── Competitors ──────────────────────────────────────────────────────────
    op.create_table(
        "competitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("platforms", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("tracking_config", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── Competitor Posts ─────────────────────────────────────────────────────
    op.create_table(
        "competitor_posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("competitor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", platform_type, nullable=False),
        sa.Column("external_id", sa.String(500), nullable=True),
        sa.Column("title", sa.String(1000), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("media_urls", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("views", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("likes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("comments", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("shares", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("engagement_rate", sa.Float(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_data", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("simhash", sa.String(64), nullable=True),
        sa.Column("qdrant_point_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Composite unique constraint: (external_id, platform) instead of global unique on external_id
    op.create_unique_constraint(
        "uq_competitor_posts_external_id_platform",
        "competitor_posts",
        ["external_id", "platform"],
    )
    op.create_index("ix_competitor_posts_competitor_platform", "competitor_posts", ["competitor_id", "platform"])
    op.create_index("ix_competitor_posts_published_at", "competitor_posts", ["published_at"])
    op.create_index("ix_competitor_posts_simhash", "competitor_posts", ["simhash"])

    # ── Reports ──────────────────────────────────────────────────────────────
    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("type", report_type, nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("content", postgresql.JSONB(), nullable=True),
        sa.Column("content_markdown", sa.Text(), nullable=True),
        sa.Column("media_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_reports_type", "reports", ["type"])

    # ── Content Plans ────────────────────────────────────────────────────────
    op.create_table(
        "content_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("content", postgresql.JSONB(), server_default="{}", nullable=True),
        sa.Column("ai_response", sa.Text(), nullable=True),
        sa.Column("period", plan_period, nullable=False, server_default="weekly"),
        sa.Column("status", plan_status, nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── Content Tasks ────────────────────────────────────────────────────────
    op.create_table(
        "content_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("content_plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("content_plans.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("content_type", sa.String(50), server_default="text", nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), server_default="{}", nullable=True),
        sa.Column("status", task_status, nullable=False, server_default="pending"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_content_tasks_status", "content_tasks", ["status"])
    op.create_index("ix_content_tasks_plan_status", "content_tasks", ["content_plan_id", "status"])


def downgrade() -> None:
    op.drop_table("content_tasks")
    op.drop_table("content_plans")
    op.drop_table("reports")
    op.drop_table("competitor_posts")
    op.drop_table("competitors")
    op.drop_table("subscriptions")
    op.drop_table("users")

    task_status.drop(op.get_bind(), checkfirst=True)
    plan_status.drop(op.get_bind(), checkfirst=True)
    plan_period.drop(op.get_bind(), checkfirst=True)
    report_type.drop(op.get_bind(), checkfirst=True)
    platform_type.drop(op.get_bind(), checkfirst=True)
    subscription_status.drop(op.get_bind(), checkfirst=True)
    plan_type.drop(op.get_bind(), checkfirst=True)
