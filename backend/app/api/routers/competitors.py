import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_active_subscription, get_current_user
from app.core.limits import LIMIT_WARNING_THRESHOLD, get_plan_limits
from app.models.competitor import Competitor
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.competitor import CompetitorCreate, CompetitorResponse, CompetitorUpdate

router = APIRouter()


@router.get("/", response_model=list[CompetitorResponse])
async def list_competitors(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Competitor]:
    result = await db.execute(
        select(Competitor).where(Competitor.user_id == user.id).order_by(Competitor.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/", response_model=CompetitorResponse, status_code=status.HTTP_201_CREATED)
async def create_competitor(
    body: CompetitorCreate,
    user: User = Depends(get_current_user),
    subscription: Subscription = Depends(get_active_subscription),
    db: AsyncSession = Depends(get_db),
) -> Competitor:
    limits = get_plan_limits(subscription.plan)

    count_result = await db.execute(
        select(func.count()).where(Competitor.user_id == user.id, Competitor.is_active.is_(True))
    )
    current_count = count_result.scalar() or 0

    if current_count >= limits.competitors:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Competitor limit reached ({limits.competitors}). Upgrade your plan for more.",
        )

    competitor = Competitor(user_id=user.id, **body.model_dump())
    db.add(competitor)
    await db.flush()

    if (current_count + 1) / limits.competitors >= LIMIT_WARNING_THRESHOLD:
        pass  # TODO: send limit warning notification

    return competitor


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
