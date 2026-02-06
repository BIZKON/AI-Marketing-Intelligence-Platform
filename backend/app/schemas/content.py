import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, field_validator

from app.models.content_plan import PlanPeriod, PlanStatus
from app.models.content_task import TaskStatus


# ── Plans ────────────────────────────────────────────────────────────────────


class ContentPlanCreate(BaseModel):
    title: str | None = None
    period: PlanPeriod = PlanPeriod.WEEKLY


class ContentPlanResponse(BaseModel):
    id: uuid.UUID
    title: str | None = None
    period: PlanPeriod
    status: PlanStatus
    content: dict[str, Any] | None = None
    ai_response: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Tasks ────────────────────────────────────────────────────────────────────


class ContentTaskCreate(BaseModel):
    content_plan_id: uuid.UUID | None = None
    title: str
    body: str | None = None
    platform: str
    content_type: str = "text"
    scheduled_at: datetime | None = None
    metadata_json: dict[str, Any] | None = None


class ContentTaskUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    platform: str | None = None
    content_type: str | None = None
    status: TaskStatus | None = None
    scheduled_at: datetime | None = None
    metadata_json: dict[str, Any] | None = None


class ContentTaskResponse(BaseModel):
    id: uuid.UUID
    content_plan_id: uuid.UUID | None = None
    title: str
    body: str | None = None
    platform: str
    content_type: str = "text"
    status: TaskStatus
    metadata_json: dict[str, Any] | None = None
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Generation ───────────────────────────────────────────────────────────────


class GenerateDraftRequest(BaseModel):
    """Request to generate an AI draft for a specific task."""
    task_id: uuid.UUID


class RegenerateDraftRequest(BaseModel):
    """Request to regenerate a draft with optional instructions."""
    task_id: uuid.UUID
    instructions: str = ""


class GeneratePlanDraftsRequest(BaseModel):
    """Generate AI drafts for all pending tasks in a plan."""
    plan_id: uuid.UUID


class GenerateResponse(BaseModel):
    task_id: uuid.UUID
    status: str
    body_preview: str | None = None


class BulkGenerateResponse(BaseModel):
    plan_id: uuid.UUID
    generated_count: int
    total_pending: int


# ── Publishing ───────────────────────────────────────────────────────────────


class PublishRequest(BaseModel):
    """Manual publish request for an approved task."""
    task_id: uuid.UUID
    target_channel: str | None = None  # Override channel/group to publish to


class ScheduleRequest(BaseModel):
    """Schedule a task for future auto-publishing."""
    task_id: uuid.UUID
    scheduled_at: datetime

    @field_validator("scheduled_at")
    @classmethod
    def ensure_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class PublishResponse(BaseModel):
    task_id: uuid.UUID
    status: str
    published_url: str | None = None
    message: str = ""
