import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_active_subscription, get_current_user
from app.models.competitor import Competitor
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.competitor import CompetitorCreate, CompetitorResponse, CompetitorUpdate
from app.services.limits_service import LimitsService

router = APIRouter()


class CompetitorCreateResponse(CompetitorResponse):
    limit_warning: str | None = None


@router.get("/", response_model=list[CompetitorResponse])
async def list_competitors(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Competitor]:
    result = await db.execute(
        select(Competitor).where(Competitor.user_id == user.id).order_by(Competitor.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/", response_model=CompetitorCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_competitor(
    body: CompetitorCreate,
    user: User = Depends(get_current_user),
    subscription: Subscription = Depends(get_active_subscription),
    db: AsyncSession = Depends(get_db),
) -> dict:
    limits_svc = LimitsService(db)
    check = await limits_svc.check_competitor_limit(user.id, subscription.plan)

    if not check.allowed:
        detail = f"Competitor limit reached ({check.limit}). Upgrade your plan for more."
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

    competitor = Competitor(user_id=user.id, **body.model_dump())
    db.add(competitor)
    await db.flush()

    return {
        "id": competitor.id,
        "name": competitor.name,
        "url": competitor.url,
        "description": competitor.description,
        "platforms": competitor.platforms,
        "tracking_config": competitor.tracking_config,
        "is_active": competitor.is_active,
        "limit_warning": check.warning,
    }


@router.get("/{competitor_id}", response_model=CompetitorResponse)
async def get_competitor(
    competitor_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Competitor:
    result = await db.execute(
        select(Competitor).where(Competitor.id == competitor_id, Competitor.user_id == user.id)
    )
    competitor = result.scalar_one_or_none()
    if not competitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Competitor not found")
    return competitor


@router.patch("/{competitor_id}", response_model=CompetitorResponse)
async def update_competitor(
    competitor_id: uuid.UUID,
    body: CompetitorUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Competitor:
    result = await db.execute(
        select(Competitor).where(Competitor.id == competitor_id, Competitor.user_id == user.id)
    )
    competitor = result.scalar_one_or_none()
    if not competitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Competitor not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(competitor, field, value)
    await db.flush()
    return competitor


@router.delete("/{competitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_competitor(
    competitor_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(Competitor).where(Competitor.id == competitor_id, Competitor.user_id == user.id)
    )
    competitor = result.scalar_one_or_none()
    if not competitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Competitor not found")
    await db.delete(competitor)


class UsageSummaryResponse(BaseModel):
    competitors: int
    competitors_limit: int
    tasks_this_month: int
    tasks_limit: int
    voice_this_week: int
    voice_limit: int
    video_this_week: int
    video_limit: int


@router.get("/usage/summary", response_model=UsageSummaryResponse)
async def get_usage_summary(
    user: User = Depends(get_current_user),
    subscription: Subscription = Depends(get_active_subscription),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get current resource usage against plan limits."""
    limits_svc = LimitsService(db)
    usage = await limits_svc.get_usage(user.id, subscription.plan)
    return {
        "competitors": usage.competitors,
        "competitors_limit": usage.competitors_limit,
        "tasks_this_month": usage.tasks_this_month,
        "tasks_limit": usage.tasks_limit,
        "voice_this_week": usage.voice_this_week,
        "voice_limit": usage.voice_limit,
        "video_this_week": usage.video_this_week,
        "video_limit": usage.video_limit,
    }
