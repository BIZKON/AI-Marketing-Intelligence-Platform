"""Reports API — digests, alerts, PDF, voice, video generation."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_plan
from app.models.report import Report, ReportType
from app.models.subscription import PlanType, Subscription
from app.models.user import User
from app.schemas.report import (
    DigestRequest,
    MediaGenerationResponse,
    PDFReportRequest,
    PDFResponse,
    ReportResponse,
    VideoReportRequest,
    VoiceReportRequest,
)

router = APIRouter()


# ── List & Get ────────────────────────────────────────────────────────────────


@router.get("/", response_model=list[ReportResponse])
async def list_reports(
    report_type: ReportType | None = None,
    limit: int = 20,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Report]:
    query = select(Report).where(Report.user_id == user.id)
    if report_type:
        query = query.where(Report.type == report_type)
    query = query.order_by(Report.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Report:
    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.user_id == user.id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return report


# ── Digest ────────────────────────────────────────────────────────────────────


@router.post("/digest", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def request_digest(
    body: DigestRequest,
    user: User = Depends(get_current_user),
    _sub: Subscription = Depends(require_plan(PlanType.MONITOR)),
    db: AsyncSession = Depends(get_db),
) -> Report:
    """Generate a competitive intelligence digest."""
    from app.services.report_generator import ReportGenerator

    generator = ReportGenerator(db)
    comp_ids = [str(c) for c in (body.competitor_ids or [])] or None
    report = await generator.generate_digest(user, competitor_ids=comp_ids)
    await db.commit()
    return report


# ── PDF ───────────────────────────────────────────────────────────────────────


@router.post("/pdf", response_model=PDFResponse)
async def generate_pdf(
    body: PDFReportRequest,
    user: User = Depends(get_current_user),
    _sub: Subscription = Depends(require_plan(PlanType.MONITOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Generate a PDF from an existing report (synchronous, returns URL)."""
    from app.services.media.pdf_generator import generate_digest_pdf
    from app.services.s3_storage import S3Storage

    report = await _get_user_report(db, body.report_id, user.id)

    if not report.content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Report has no content for PDF generation",
        )

    pdf_bytes = generate_digest_pdf(report.content, title=report.title or "")

    s3 = S3Storage()
    await s3.ensure_bucket()
    s3_key = S3Storage.generate_key("reports/pdf", "pdf")
    await s3.upload_bytes(pdf_bytes, s3_key, content_type="application/pdf")
    pdf_url = await s3.get_presigned_url(s3_key, expires_in=86400)

    report.media_url = pdf_url
    await db.commit()

    return {
        "report_id": report.id,
        "pdf_url": pdf_url,
        "size_bytes": len(pdf_bytes),
    }


# ── Voice ─────────────────────────────────────────────────────────────────────


@router.post("/voice", response_model=MediaGenerationResponse, status_code=status.HTTP_202_ACCEPTED)
async def request_voice_report(
    body: VoiceReportRequest,
    user: User = Depends(get_current_user),
    _sub: Subscription = Depends(require_plan(PlanType.CREATOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Queue voice report generation via Celery (returns immediately)."""
    from app.workers.tasks import generate_voice_report

    report = await _get_user_report(db, body.report_id, user.id)

    if not report.content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Report has no content for voice generation",
        )

    voice_report = Report(
        user_id=user.id,
        type=ReportType.VOICE,
        title=f"🎙 {report.title or 'Голосовой отчёт'}",
        content={"source_report_id": str(report.id), "status": "generating"},
    )
    db.add(voice_report)
    await db.commit()

    generate_voice_report.delay(str(voice_report.id), str(report.id))

    return {
        "report_id": voice_report.id,
        "media_type": "voice",
        "status": "generating",
        "message": "Голосовой отчёт генерируется. Вы получите уведомление.",
    }


# ── Video ─────────────────────────────────────────────────────────────────────


@router.post("/video", response_model=MediaGenerationResponse, status_code=status.HTTP_202_ACCEPTED)
async def request_video_report(
    body: VideoReportRequest,
    user: User = Depends(get_current_user),
    _sub: Subscription = Depends(require_plan(PlanType.AUTOPILOT)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Queue video report generation via Celery (returns immediately)."""
    from app.workers.tasks import generate_video_report

    report = await _get_user_report(db, body.report_id, user.id)

    if not report.content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Report has no content for video generation",
        )

    video_report = Report(
        user_id=user.id,
        type=ReportType.VIDEO,
        title=f"🎬 {report.title or 'Видеоотчёт'}",
        content={"source_report_id": str(report.id), "status": "generating"},
    )
    db.add(video_report)
    await db.commit()

    generate_video_report.delay(str(video_report.id), str(report.id))

    return {
        "report_id": video_report.id,
        "media_type": "video",
        "status": "generating",
        "message": "Видеоотчёт генерируется. Это может занять несколько минут.",
    }


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_user_report(db: AsyncSession, report_id: uuid.UUID, user_id: uuid.UUID) -> Report:
    """Fetch a report belonging to the user or raise 404."""
    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.user_id == user_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return report
