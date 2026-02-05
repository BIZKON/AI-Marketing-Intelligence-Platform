"""Content management API — plans, tasks, AI generation, publishing."""

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
    BulkGenerateResponse,
    ContentPlanCreate,
    ContentPlanResponse,
    ContentTaskCreate,
    ContentTaskResponse,
    ContentTaskUpdate,
    GenerateDraftRequest,
    GeneratePlanDraftsRequest,
    GenerateResponse,
    PublishRequest,
    PublishResponse,
    RegenerateDraftRequest,
    ScheduleRequest,
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
    from app.services.report_generator import ReportGenerator

    generator = ReportGenerator(db)
    plan_data = await generator.generate_content_plan(user, period=body.period.value)

    plan = ContentPlan(
        user_id=user.id,
        title=body.title or f"Контент-план ({body.period.value})",
        period=body.period,
        status="draft",
        content=plan_data.get("structured_data", {}),
        ai_response=plan_data.get("content", ""),
    )
    db.add(plan)
    await db.flush()

    # Auto-create tasks from structured plan
    tasks_data = plan_data.get("structured_data", {}).get("tasks", [])
    for task_data in tasks_data:
        task = ContentTask(
            user_id=user.id,
            content_plan_id=plan.id,
            title=task_data.get("title", "Untitled"),
            platform=task_data.get("platform", "telegram"),
            content_type=task_data.get("format", "text"),
            body=task_data.get("topic", ""),
            status=TaskStatus.PENDING,
            metadata_json={
                "key_points": task_data.get("key_points", []),
                "hashtags": task_data.get("hashtags", []),
                "suggested_day": task_data.get("suggested_day", ""),
            },
        )
        db.add(task)

    await db.flush()
    return plan


@router.get("/plans/{plan_id}", response_model=ContentPlanResponse)
async def get_plan(
    plan_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContentPlan:
    result = await db.execute(
        select(ContentPlan).where(ContentPlan.id == plan_id, ContentPlan.user_id == user.id)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
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


@router.get("/tasks/{task_id}", response_model=ContentTaskResponse)
async def get_task(
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
    return task


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


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(ContentTask).where(ContentTask.id == task_id, ContentTask.user_id == user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    await db.delete(task)
    await db.flush()


# ── Approval Workflow ────────────────────────────────────────────────────────


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


@router.post("/tasks/{task_id}/reject", response_model=ContentTaskResponse)
async def reject_task(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContentTask:
    """Send task back to draft status for revision."""
    result = await db.execute(
        select(ContentTask).where(ContentTask.id == task_id, ContentTask.user_id == user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if task.status not in (TaskStatus.IN_REVIEW, TaskStatus.APPROVED):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task must be in review or approved")

    task.status = TaskStatus.DRAFT
    await db.flush()
    return task


# ── AI Generation ────────────────────────────────────────────────────────────


@router.post("/generate", response_model=GenerateResponse)
async def generate_draft(
    body: GenerateDraftRequest,
    user: User = Depends(get_current_user),
    _sub: Subscription = Depends(require_plan(PlanType.CREATOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Generate an AI draft for a single content task."""
    from app.services.content_generator import ContentGenerator

    result = await db.execute(
        select(ContentTask).where(ContentTask.id == body.task_id, ContentTask.user_id == user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if task.status not in (TaskStatus.PENDING, TaskStatus.DRAFT):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only generate drafts for pending or draft tasks",
        )

    generator = ContentGenerator(db)
    updated_task = await generator.generate_draft(task, user)

    return {
        "task_id": updated_task.id,
        "status": updated_task.status.value,
        "body_preview": (updated_task.body or "")[:300],
    }


@router.post("/regenerate", response_model=GenerateResponse)
async def regenerate_draft(
    body: RegenerateDraftRequest,
    user: User = Depends(get_current_user),
    _sub: Subscription = Depends(require_plan(PlanType.CREATOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Regenerate a draft with optional user instructions."""
    from app.services.content_generator import ContentGenerator

    result = await db.execute(
        select(ContentTask).where(ContentTask.id == body.task_id, ContentTask.user_id == user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    generator = ContentGenerator(db)
    updated_task = await generator.regenerate_draft(task, user, instructions=body.instructions)

    return {
        "task_id": updated_task.id,
        "status": updated_task.status.value,
        "body_preview": (updated_task.body or "")[:300],
    }


@router.post("/generate-plan-drafts", response_model=BulkGenerateResponse)
async def generate_plan_drafts(
    body: GeneratePlanDraftsRequest,
    user: User = Depends(get_current_user),
    _sub: Subscription = Depends(require_plan(PlanType.CREATOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Generate AI drafts for all pending tasks in a plan."""
    from app.services.content_generator import ContentGenerator

    result = await db.execute(
        select(ContentPlan).where(ContentPlan.id == body.plan_id, ContentPlan.user_id == user.id)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    # Count pending tasks
    pending_count = (await db.execute(
        select(func.count()).where(
            ContentTask.content_plan_id == plan.id,
            ContentTask.status == TaskStatus.PENDING,
        )
    )).scalar() or 0

    generator = ContentGenerator(db)
    generated = await generator.generate_plan_drafts(plan, user)

    return {
        "plan_id": plan.id,
        "generated_count": len(generated),
        "total_pending": pending_count,
    }


# ── Publishing ───────────────────────────────────────────────────────────────


@router.post("/publish", response_model=PublishResponse)
async def publish_task(
    body: PublishRequest,
    user: User = Depends(get_current_user),
    _sub: Subscription = Depends(require_plan(PlanType.AUTOPILOT)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manually publish an approved task to the target platform."""
    from app.services.publisher import PublisherService

    result = await db.execute(
        select(ContentTask).where(ContentTask.id == body.task_id, ContentTask.user_id == user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if task.status != TaskStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task must be approved before publishing",
        )

    publisher = PublisherService()
    pub_result = await publisher.publish(task, target_channel=body.target_channel)

    task.status = TaskStatus.PUBLISHED
    task.published_at = datetime.now(timezone.utc)
    task.metadata_json = {
        **(task.metadata_json or {}),
        "published_url": pub_result.get("url"),
        "publish_result": pub_result.get("result"),
    }
    await db.flush()

    return {
        "task_id": task.id,
        "status": "published",
        "published_url": pub_result.get("url"),
        "message": pub_result.get("message", "Published successfully"),
    }


@router.post("/schedule", response_model=ContentTaskResponse)
async def schedule_task(
    body: ScheduleRequest,
    user: User = Depends(get_current_user),
    _sub: Subscription = Depends(require_plan(PlanType.AUTOPILOT)),
    db: AsyncSession = Depends(get_db),
) -> ContentTask:
    """Schedule an approved task for auto-publishing."""
    result = await db.execute(
        select(ContentTask).where(ContentTask.id == body.task_id, ContentTask.user_id == user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if task.status != TaskStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task must be approved before scheduling",
        )

    if body.scheduled_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scheduled time must be in the future",
        )

    task.scheduled_at = body.scheduled_at
    await db.flush()
    return task
