"""Telegram Export API — endpoints for the TG Data Export + RAG Pipeline module.

Provides REST API for:
- Connecting user's Telegram account (Telethon session)
- Managing export sources (channels, groups, chats)
- Running and tracking export jobs
- Semantic search over exported data
- Analytics: popular posts, top authors, activity
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import get_active_subscription, get_current_user
from app.models.export import (
    ExportJob,
    ExportJobStatus,
    ExportSource,
    ExportSourceType,
    MessageMeta,
    TelegramSession,
)
from app.models.subscription import PlanType, Subscription
from app.models.user import User

router = APIRouter()
settings = get_settings()

# ── Plan limits ──────────────────────────────────────────────────────────────

SOURCE_LIMITS = {
    PlanType.MONITOR: 3,
    PlanType.CREATOR: 7,
    PlanType.AUTOPILOT: 15,
    PlanType.ENTERPRISE: 999,
}

SEARCH_DAILY_LIMITS = {
    PlanType.MONITOR: 10,
    PlanType.CREATOR: 50,
    PlanType.AUTOPILOT: 999,
    PlanType.ENTERPRISE: 999,
}


# ── Schemas ──────────────────────────────────────────────────────────────────


class ConnectRequest(BaseModel):
    api_id: int
    api_hash: str
    phone: str


class ConnectResponse(BaseModel):
    session_id: str
    status: str = "code_required"


class VerifyRequest(BaseModel):
    session_id: str
    code: str
    password_2fa: str | None = None


class VerifyResponse(BaseModel):
    status: str
    message: str


class SourceCreateRequest(BaseModel):
    telegram_id_or_username: str
    source_type: ExportSourceType = ExportSourceType.CHANNEL
    title: str | None = None


class SourceResponse(BaseModel):
    id: str
    telegram_id: int
    telegram_type: str
    username: str | None
    title: str
    auto_export: bool
    total_messages: int
    total_chunks: int
    last_export_at: str | None

    class Config:
        from_attributes = True


class JobCreateRequest(BaseModel):
    source_id: str
    date_from: str | None = None  # ISO format
    date_to: str | None = None
    min_reactions: int = 0
    include_media: bool = True
    transcribe_voice: bool = True
    chunk_size: int = 500
    chunk_overlap: int = 50


class JobResponse(BaseModel):
    id: str
    source_name: str
    source_type: str
    status: str
    total_messages: int | None
    processed_messages: int
    total_chunks: int
    error_message: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None

    class Config:
        from_attributes = True


class SearchRequest(BaseModel):
    query: str
    source_ids: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None
    min_reactions: int = 0
    limit: int = Field(default=10, le=50)


class SearchResultItem(BaseModel):
    text: str
    score: float
    source_name: str
    author_name: str | None
    date: str | None
    reactions_count: int
    views_count: int
    message_url: str | None


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    total: int


class PopularPostItem(BaseModel):
    text_preview: str
    reactions_count: int
    views_count: int
    author_name: str | None
    date: str


class AuthorStatsItem(BaseModel):
    author_name: str
    author_username: str | None
    message_count: int
    total_reactions: int
    avg_reactions: float


class ActivityStatsResponse(BaseModel):
    total_messages: int
    active_days: int
    avg_per_day: float
    peak_day: str | None
    peak_day_count: int
    daily_breakdown: list[dict]


# ── Connect / Verify ─────────────────────────────────────────────────────────


@router.post("/connect", response_model=ConnectResponse)
async def connect_telegram(
    body: ConnectRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Initialize a Telegram session. Encrypts api_hash and stores in DB."""
    from cryptography.fernet import Fernet

    encryption_key = settings.telegram_encryption_key
    if not encryption_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Telegram encryption not configured",
        )

    fernet = Fernet(encryption_key.encode())
    encrypted_hash = fernet.encrypt(body.api_hash.encode()).decode()

    session = TelegramSession(
        user_id=user.id,
        phone=body.phone,
        api_id=body.api_id,
        api_hash_encrypted=encrypted_hash,
    )
    db.add(session)
    await db.flush()

    return {"session_id": str(session.id), "status": "code_required"}


@router.post("/verify", response_model=VerifyResponse)
async def verify_telegram(
    body: VerifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Verify Telegram code/2FA and save the session string."""
    from cryptography.fernet import Fernet
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    session_uuid = uuid.UUID(body.session_id)
    result = await db.execute(
        select(TelegramSession).where(
            TelegramSession.id == session_uuid,
            TelegramSession.user_id == user.id,
        )
    )
    tg_session = result.scalar_one_or_none()
    if not tg_session:
        raise HTTPException(status_code=404, detail="Session not found")

    encryption_key = settings.telegram_encryption_key
    fernet = Fernet(encryption_key.encode())
    api_hash = fernet.decrypt(tg_session.api_hash_encrypted.encode()).decode()

    try:
        client = TelegramClient(StringSession(), tg_session.api_id, api_hash)
        await client.connect()
        await client.sign_in(
            phone=tg_session.phone,
            code=body.code,
            password=body.password_2fa,
        )

        # Save encrypted session string
        session_string = client.session.save()
        encrypted_session = fernet.encrypt(session_string.encode()).decode()
        tg_session.session_string_encrypted = encrypted_session
        tg_session.is_active = True
        await db.flush()

        await client.disconnect()
        return {"status": "connected", "message": "Telegram аккаунт успешно подключён"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Verification failed: {e!s}",
        )


# ── Sources ──────────────────────────────────────────────────────────────────


@router.get("/sources", response_model=list[SourceResponse])
async def list_sources(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List user's registered export sources."""
    result = await db.execute(
        select(ExportSource)
        .where(ExportSource.user_id == user.id)
        .order_by(ExportSource.created_at.desc())
    )
    sources = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "telegram_id": s.telegram_id,
            "telegram_type": s.telegram_type.value,
            "username": s.username,
            "title": s.title,
            "auto_export": s.auto_export,
            "total_messages": s.total_messages,
            "total_chunks": s.total_chunks,
            "last_export_at": s.last_export_at.isoformat() if s.last_export_at else None,
        }
        for s in sources
    ]


@router.post("/sources", response_model=SourceResponse, status_code=201)
async def add_source(
    body: SourceCreateRequest,
    user: User = Depends(get_current_user),
    subscription: Subscription = Depends(get_active_subscription),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Register a new Telegram source for export."""
    # Check plan limits
    count_result = await db.execute(
        select(func.count(ExportSource.id)).where(ExportSource.user_id == user.id)
    )
    current_count = count_result.scalar() or 0
    limit = SOURCE_LIMITS.get(subscription.plan, 3)

    if current_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Source limit reached ({limit}). Upgrade plan for more.",
        )

    # Parse telegram_id
    tg_input = body.telegram_id_or_username.lstrip("@")
    try:
        tg_id = int(tg_input)
    except ValueError:
        tg_id = 0  # Will be resolved when export runs

    source = ExportSource(
        user_id=user.id,
        telegram_id=tg_id,
        telegram_type=body.source_type,
        username=tg_input if not tg_input.isdigit() else None,
        title=body.title or tg_input,
    )
    db.add(source)
    await db.flush()

    return {
        "id": str(source.id),
        "telegram_id": source.telegram_id,
        "telegram_type": source.telegram_type.value,
        "username": source.username,
        "title": source.title,
        "auto_export": source.auto_export,
        "total_messages": 0,
        "total_chunks": 0,
        "last_export_at": None,
    }


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(
    source_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete source and clean up Qdrant vectors."""
    result = await db.execute(
        select(ExportSource).where(
            ExportSource.id == source_id,
            ExportSource.user_id == user.id,
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    # Clean up Qdrant vectors
    from app.services.rag.ingestion import RAGIngestionPipeline
    from app.services.vectordb.embeddings import EmbeddingService
    from app.services.vectordb.qdrant_client import QdrantService

    rag = RAGIngestionPipeline(
        embeddings=EmbeddingService(),
        qdrant=QdrantService(collection="telegram_messages"),
        db=db,
    )
    await rag.delete_by_source(str(user.id), str(source_id))
    await db.delete(source)


# ── Jobs ─────────────────────────────────────────────────────────────────────


@router.post("/jobs", response_model=JobResponse, status_code=201)
async def start_export(
    body: JobCreateRequest,
    user: User = Depends(get_current_user),
    subscription: Subscription = Depends(get_active_subscription),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Start a new export job."""
    source_uuid = uuid.UUID(body.source_id)
    result = await db.execute(
        select(ExportSource).where(
            ExportSource.id == source_uuid,
            ExportSource.user_id == user.id,
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    # Check for already running exports
    running_result = await db.execute(
        select(func.count(ExportJob.id)).where(
            ExportJob.user_id == user.id,
            ExportJob.status.in_([ExportJobStatus.PROCESSING, ExportJobStatus.CHUNKING, ExportJobStatus.EMBEDDING]),
        )
    )
    running_count = running_result.scalar() or 0
    if running_count >= 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many running exports (max 3). Wait for completion.",
        )

    # Get user's Telegram session
    session_result = await db.execute(
        select(TelegramSession).where(
            TelegramSession.user_id == user.id,
            TelegramSession.is_active.is_(True),
        ).order_by(TelegramSession.created_at.desc())
    )
    tg_session = session_result.scalar_one_or_none()
    if not tg_session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active Telegram session. Use /connect first.",
        )

    job = ExportJob(
        user_id=user.id,
        session_id=tg_session.id,
        source_id=source.id,
        source_type=source.telegram_type,
        source_tg_id=source.username or str(source.telegram_id),
        source_name=source.title,
        config={
            "date_from": body.date_from,
            "date_to": body.date_to,
            "min_reactions": body.min_reactions,
            "include_media": body.include_media,
            "transcribe_voice": body.transcribe_voice,
            "chunk_size": body.chunk_size,
            "chunk_overlap": body.chunk_overlap,
        },
        status=ExportJobStatus.PENDING,
    )
    db.add(job)
    await db.flush()

    # TODO: Dispatch Celery task for background processing
    # from app.workers.export_tasks import run_export_job
    # run_export_job.delay(str(job.id))

    return _job_to_dict(job)


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, le=100),
) -> list[dict]:
    """List export jobs (history + active)."""
    result = await db.execute(
        select(ExportJob)
        .where(ExportJob.user_id == user.id)
        .order_by(ExportJob.created_at.desc())
        .limit(limit)
    )
    jobs = result.scalars().all()
    return [_job_to_dict(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get export job details."""
    result = await db.execute(
        select(ExportJob).where(ExportJob.id == job_id, ExportJob.user_id == user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_dict(job)


@router.post("/jobs/{job_id}/cancel", status_code=200)
async def cancel_job(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cancel a running export job."""
    result = await db.execute(
        select(ExportJob).where(ExportJob.id == job_id, ExportJob.user_id == user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in (ExportJobStatus.COMPLETED, ExportJobStatus.FAILED, ExportJobStatus.CANCELLED):
        raise HTTPException(status_code=400, detail="Job already finished")

    job.status = ExportJobStatus.CANCELLED
    await db.flush()
    return {"status": "cancelled"}


# ── Search ───────────────────────────────────────────────────────────────────


@router.post("/search", response_model=SearchResponse)
async def semantic_search(
    body: SearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Semantic search over exported Telegram data via RAG."""
    from app.services.rag.ingestion import RAGIngestionPipeline
    from app.services.vectordb.embeddings import EmbeddingService
    from app.services.vectordb.qdrant_client import QdrantService

    rag = RAGIngestionPipeline(
        embeddings=EmbeddingService(),
        qdrant=QdrantService(collection="telegram_messages"),
        db=db,
    )

    date_from = datetime.fromisoformat(body.date_from) if body.date_from else None
    date_to = datetime.fromisoformat(body.date_to) if body.date_to else None

    results = await rag.search(
        query=body.query,
        user_id=str(user.id),
        source_ids=body.source_ids,
        date_from=date_from,
        date_to=date_to,
        min_reactions=body.min_reactions,
        limit=body.limit,
    )

    items = []
    for r in results:
        payload = r.get("payload", {})
        items.append({
            "text": payload.get("text", ""),
            "score": r.get("score", 0),
            "source_name": payload.get("source_name", ""),
            "author_name": payload.get("author_name"),
            "date": payload.get("date"),
            "reactions_count": payload.get("reactions_count", 0),
            "views_count": payload.get("views_count", 0),
            "message_url": None,
        })

    return {"results": items, "total": len(items)}


# ── Analytics ────────────────────────────────────────────────────────────────


@router.get("/analytics/popular", response_model=list[PopularPostItem])
async def popular_posts(
    source_id: uuid.UUID = Query(...),
    min_reactions: int = Query(default=5),
    limit: int = Query(default=50, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Get popular posts by reaction count."""
    # Verify ownership
    src = await db.execute(
        select(ExportSource).where(ExportSource.id == source_id, ExportSource.user_id == user.id)
    )
    if not src.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Source not found")

    from app.services.export.analytics import ExportAnalytics

    analytics = ExportAnalytics(db)
    return await analytics.get_top_posts(source_id, limit=limit, min_reactions=min_reactions)


@router.get("/analytics/authors", response_model=list[AuthorStatsItem])
async def top_authors(
    source_id: uuid.UUID = Query(...),
    limit: int = Query(default=20, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Get top authors by activity and engagement."""
    src = await db.execute(
        select(ExportSource).where(ExportSource.id == source_id, ExportSource.user_id == user.id)
    )
    if not src.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Source not found")

    from app.services.export.analytics import ExportAnalytics

    analytics = ExportAnalytics(db)
    return await analytics.get_top_authors(source_id, limit=limit)


@router.get("/analytics/activity", response_model=ActivityStatsResponse)
async def activity_stats(
    source_id: uuid.UUID = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get activity statistics by day."""
    src = await db.execute(
        select(ExportSource).where(ExportSource.id == source_id, ExportSource.user_id == user.id)
    )
    if not src.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Source not found")

    from app.services.export.analytics import ExportAnalytics

    analytics = ExportAnalytics(db)
    return await analytics.get_activity_stats(source_id)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _job_to_dict(job: ExportJob) -> dict:
    return {
        "id": str(job.id),
        "source_name": job.source_name,
        "source_type": job.source_type.value,
        "status": job.status.value,
        "total_messages": job.total_messages,
        "processed_messages": job.processed_messages,
        "total_chunks": job.total_chunks,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
