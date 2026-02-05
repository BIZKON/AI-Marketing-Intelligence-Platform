import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.report import ReportType


class ReportResponse(BaseModel):
    id: uuid.UUID
    type: ReportType
    title: str | None = None
    content: dict[str, Any] | None = None
    content_markdown: str | None = None
    media_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DigestRequest(BaseModel):
    competitor_ids: list[uuid.UUID] | None = None
