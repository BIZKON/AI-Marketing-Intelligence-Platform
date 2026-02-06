import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CompetitorBase(BaseModel):
    name: str
    url: str | None = None
    description: str | None = None
    platforms: list[str] = []
    tracking_config: dict[str, Any] = {}


class CompetitorCreate(CompetitorBase):
    pass


class CompetitorUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    description: str | None = None
    platforms: list[str] | None = None
    tracking_config: dict[str, Any] | None = None
    is_active: bool | None = None


class CompetitorResponse(CompetitorBase):
    id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompetitorPostResponse(BaseModel):
    id: uuid.UUID
    competitor_id: uuid.UUID
    platform: str
    external_id: str | None = None
    title: str | None = None
    text_content: str | None = None
    url: str | None = None
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    engagement_rate: float | None = None
    published_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
