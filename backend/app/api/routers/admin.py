"""Admin API — platform statistics, user management, system health."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_superuser
from app.models.competitor import Competitor
from app.models.competitor_post import CompetitorPost
from app.models.content_task import ContentTask
from app.models.report import Report
from app.models.subscription import PlanType, Subscription, SubscriptionStatus
from app.models.user import User

router = APIRouter()


# ── Platform Stats ────────────────────────────────────────────────────────────


@router.get("/stats")
async def platform_stats(
    _admin: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get aggregated platform statistics."""
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    active_users = (await db.execute(
        select(func.count(User.id)).where(User.is_active.is_(True))
    )).scalar() or 0

    total_subs = (await db.execute(
        select(func.count(Subscription.id)).where(
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
    )).scalar() or 0

    # Plan distribution
    plan_dist_rows = (await db.execute(
        select(Subscription.plan, func.count(Subscription.id))
        .where(Subscription.status == SubscriptionStatus.ACTIVE)
        .group_by(Subscription.plan)
    )).all()
    plan_distribution = {row[0].value: row[1] for row in plan_dist_rows}

    total_competitors = (await db.execute(select(func.count(Competitor.id)))).scalar() or 0
    total_posts = (await db.execute(select(func.count(CompetitorPost.id)))).scalar() or 0
    total_reports = (await db.execute(select(func.count(Report.id)))).scalar() or 0
    total_tasks = (await db.execute(select(func.count(ContentTask.id)))).scalar() or 0

    # Activity last 24h
    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    posts_24h = (await db.execute(
        select(func.count(CompetitorPost.id)).where(CompetitorPost.created_at >= since_24h)
    )).scalar() or 0
    reports_24h = (await db.execute(
        select(func.count(Report.id)).where(Report.created_at >= since_24h)
    )).scalar() or 0
    tasks_24h = (await db.execute(
        select(func.count(ContentTask.id)).where(ContentTask.created_at >= since_24h)
    )).scalar() or 0

    return {
        "users": {
            "total": total_users,
            "active": active_users,
        },
        "subscriptions": {
            "active": total_subs,
            "plan_distribution": plan_distribution,
        },
        "data": {
            "competitors": total_competitors,
            "posts": total_posts,
            "reports": total_reports,
            "content_tasks": total_tasks,
        },
        "activity_24h": {
            "new_posts": posts_24h,
            "new_reports": reports_24h,
            "new_tasks": tasks_24h,
        },
    }


# ── User Management ──────────────────────────────────────────────────────────


@router.get("/users")
async def list_users(
    limit: int = Query(50, le=200),
    offset: int = 0,
    is_active: bool | None = None,
    _admin: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List all users with subscription info."""
    query = select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    users = (await db.execute(query)).scalars().all()

    result = []
    for user in users:
        # Get active subscription
        sub = (await db.execute(
            select(Subscription).where(
                Subscription.user_id == user.id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        )).scalar_one_or_none()

        result.append({
            "id": str(user.id),
            "telegram_id": user.telegram_id,
            "telegram_username": user.telegram_username,
            "email": user.email,
            "full_name": user.full_name,
            "brand_name": user.brand_name,
            "is_active": user.is_active,
            "is_superuser": user.is_superuser,
            "plan": sub.plan.value if sub else None,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        })

    return result


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: uuid.UUID,
    _admin: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get detailed user info with usage stats."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    sub = (await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
    )).scalar_one_or_none()

    competitor_count = (await db.execute(
        select(func.count(Competitor.id)).where(Competitor.user_id == user.id)
    )).scalar() or 0
    report_count = (await db.execute(
        select(func.count(Report.id)).where(Report.user_id == user.id)
    )).scalar() or 0
    task_count = (await db.execute(
        select(func.count(ContentTask.id)).where(ContentTask.user_id == user.id)
    )).scalar() or 0

    return {
        "id": str(user.id),
        "telegram_id": user.telegram_id,
        "telegram_username": user.telegram_username,
        "email": user.email,
        "full_name": user.full_name,
        "brand_name": user.brand_name,
        "brand_industry": user.brand_industry,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "language": user.language,
        "timezone": user.timezone,
        "plan": sub.plan.value if sub else None,
        "subscription_status": sub.status.value if sub else None,
        "usage": {
            "competitors": competitor_count,
            "reports": report_count,
            "content_tasks": task_count,
        },
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.patch("/users/{user_id}")
async def update_user_admin(
    user_id: uuid.UUID,
    is_active: bool | None = None,
    is_superuser: bool | None = None,
    _admin: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update user status (activate/deactivate, grant/revoke admin)."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if is_active is not None:
        user.is_active = is_active
    if is_superuser is not None:
        user.is_superuser = is_superuser

    await db.flush()
    return {
        "id": str(user.id),
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "message": "User updated",
    }


@router.patch("/users/{user_id}/plan")
async def change_user_plan(
    user_id: uuid.UUID,
    plan: PlanType,
    _admin: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Override a user's subscription plan (admin grant)."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    sub = (await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
        .order_by(Subscription.created_at.desc())
    )).scalars().first()

    if sub:
        sub.plan = plan
        sub.status = SubscriptionStatus.ACTIVE
    else:
        sub = Subscription(
            user_id=user.id,
            plan=plan,
            status=SubscriptionStatus.ACTIVE,
        )
        db.add(sub)

    await db.flush()
    return {
        "user_id": str(user.id),
        "plan": plan.value,
        "message": f"Plan set to {plan.value}",
    }
