import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_plan
from app.models.report import Report, ReportType
from app.models.subscription import PlanType, Subscription
from app.models.user import User
from app.schemas.report import DigestRequest, ReportResponse

router = APIRouter()


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


@router.post("/digest", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def request_digest(
    body: DigestRequest,
    user: User = Depends(get_current_user),
    _sub: Subscription = Depends(require_plan(PlanType.MONITOR)),
    db: AsyncSession = Depends(get_db),
) -> Report:
    # TODO: trigger async digest generation via Celery
    report = Report(
        user_id=user.id,
        type=ReportType.DIGEST,
        title="Weekly Digest",
        content={"status": "generating", "competitor_ids": [str(c) for c in (body.competitor_ids or [])]},
    )
    db.add(report)
    await db.flush()
    return report
