import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_active_subscription, get_current_user, require_plan
from app.core.limits import get_plan_limits
from app.models.content_plan import ContentPlan
from app.models.content_task import ContentTask, TaskStatus
from app.models.subscription import PlanType, Subscription
from app.models.user import User
from app.schemas.content import (
    ContentPlanCreate,
    ContentPlanResponse,
    ContentTaskCreate,
    ContentTaskResponse,
    ContentTaskUpdate,
)

router = APIRouter()

# ── Content Plans ────────────────────────────────────────────────────────────


@router.get("/plans", response_model=list[ContentPlanResponse])
async def list_plans(
    user: User = Depends(get_current_user),
    _sub: Subscription = Depends(require_plan(PlanType.CREATOR)),
    db: AsyncSession = Depends(get_db),
) -> list[ContentPlan]:
    result = await db.execute(
        select(ContentPlan).where(ContentPlan.user_id == user.id).order_by(ContentPlan.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/plans", response_model=ContentPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    body: ContentPlanCreate,
    user: User = Depends(get_current_user),
    _sub: Subscription = Depends(require_plan(PlanType.CREATOR)),
    db: AsyncSession = Depends(get_db),
) -> ContentPlan:
    # TODO: trigger AI plan generation via Celery
    plan = ContentPlan(user_id=user.id, **body.model_dump())
    db.add(plan)
    await db.flush()
    return plan


# ── Content Tasks ────────────────────────────────────────────────────────────


@router.get("/tasks", response_model=list[ContentTaskResponse])
async def list_tasks(
    plan_id: uuid.UUID | None = None,
    task_status: TaskStatus | None = None,
    user: User = Depends(get_current_user),
    _sub: Subscription = Depends(require_plan(PlanType.CREATOR)),
    db: AsyncSession = Depends(get_db),
) -> list[ContentTask]:
    query = select(ContentTask).where(ContentTask.user_id == user.id)
    if plan_id:
        query = query.where(ContentTask.content_plan_id == plan_id)
    if task_status:
        query = query.where(ContentTask.status == task_status)
    query = query.order_by(ContentTask.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("/tasks", response_model=ContentTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: ContentTaskCreate,
    user: User = Depends(get_current_user),
    subscription: Subscription = Depends(get_active_subscription),
    db: AsyncSession = Depends(get_db),
) -> ContentTask:
    limits = get_plan_limits(subscription.plan)
    if limits.tasks_per_month == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Content tasks require Creator plan or higher",
        )

    count_result = await db.execute(
        select(func.count()).where(ContentTask.user_id == user.id)
    )
    current_count = count_result.scalar() or 0

    if current_count >= limits.tasks_per_month:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Monthly task limit reached ({limits.tasks_per_month}). Upgrade your plan.",
        )

    task = ContentTask(user_id=user.id, **body.model_dump())
    db.add(task)
    await db.flush()
    return task


@router.patch("/tasks/{task_id}", response_model=ContentTaskResponse)
async def update_task(
    task_id: uuid.UUID,
    body: ContentTaskUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContentTask:
    result = await db.execute(
        select(ContentTask).where(ContentTask.id == task_id, ContentTask.user_id == user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    update_data = body.model_dump(exclude_unset=True)
    if "status" in update_data and update_data["status"] == TaskStatus.PUBLISHED:
        update_data["published_at"] = datetime.now(timezone.utc)

    for field, value in update_data.items():
        setattr(task, field, value)
    await db.flush()
    return task


@router.post("/tasks/{task_id}/approve", response_model=ContentTaskResponse)
async def approve_task(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContentTask:
    result = await db.execute(
        select(ContentTask).where(ContentTask.id == task_id, ContentTask.user_id == user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if task.status != TaskStatus.IN_REVIEW:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task must be in review to approve")

    task.status = TaskStatus.APPROVED
    await db.flush()
    return task
