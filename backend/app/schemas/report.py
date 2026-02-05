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


# ── Multimedia Report Requests ────────────────────────────────────────────────


class VoiceReportRequest(BaseModel):
    """Request voice (audio) generation from an existing report."""
    report_id: uuid.UUID


class VideoReportRequest(BaseModel):
    """Request video generation from an existing report."""
    report_id: uuid.UUID


class PDFReportRequest(BaseModel):
    """Request PDF generation from an existing report."""
    report_id: uuid.UUID


class MediaGenerationResponse(BaseModel):
    """Response for async media generation tasks."""
    report_id: uuid.UUID
    media_type: str  # "voice" | "video" | "pdf"
    status: str  # "generating" | "completed" | "error"
    media_url: str | None = None
    message: str = ""


class PDFResponse(BaseModel):
    """Response for synchronous PDF generation (returns URL directly)."""
    report_id: uuid.UUID
    pdf_url: str
    size_bytes: int
