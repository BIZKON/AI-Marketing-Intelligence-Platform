import uuid
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

    model_config = {"from_attributes": True}
