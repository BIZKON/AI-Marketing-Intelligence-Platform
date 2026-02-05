import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.content_plan import PlanPeriod, PlanStatus
from app.models.content_task import TaskStatus


class ContentPlanCreate(BaseModel):
    title: str | None = None
    period: PlanPeriod = PlanPeriod.WEEKLY


class ContentPlanResponse(BaseModel):
    id: uuid.UUID
    title: str | None = None
    period: PlanPeriod
    status: PlanStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class ContentTaskCreate(BaseModel):
    content_plan_id: uuid.UUID | None = None
    title: str
    body: str | None = None
    platform: str
    scheduled_at: datetime | None = None


class ContentTaskUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    platform: str | None = None
    status: TaskStatus | None = None
    scheduled_at: datetime | None = None


class ContentTaskResponse(BaseModel):
    id: uuid.UUID
    content_plan_id: uuid.UUID | None = None
    title: str
    body: str | None = None
    platform: str
    status: TaskStatus
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
