"""Telegram Data Export router — connect accounts, manage sources, export, search, analytics.

Part of the Telegram Data Export + RAG Pipeline module (L1 Data Collection).

Endpoints:
  POST /connect           — Init Telethon session, send verification code
  POST /verify            — Verify code / 2FA, save encrypted StringSession
  GET  /sources           — List user's export sources
  POST /sources           — Add source (channel / group / chat / folder)
  DELETE /sources/{id}    — Delete source + Qdrant data
  POST /jobs              — Start export job
  GET  /jobs              — List export jobs (history + active)
  GET  /jobs/{id}         — Get job details + progress
  POST /jobs/{id}/cancel  — Cancel running export
  POST /search            — Semantic search across exported messages
  GET  /analytics/popular — Popular posts by reactions
  GET  /analytics/authors — Top authors by activity
  GET  /analytics/activity— Activity distribution (hour, weekday, daily)
  GET  /folders           — List Telegram folders for connected account
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
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

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


# ── Plan limits ───────────────────────────────────────────────────────────────

SOURCE_LIMITS = {
    PlanType.MONITOR: 3,
    PlanType.CREATOR: 7,
    PlanType.AUTOPILOT: 15,
    PlanType.ENTERPRISE: 999,
}

EXPORT_WEEKLY_LIMITS = {
    PlanType.MONITOR: 1,
    PlanType.CREATOR: 7,
    PlanType.AUTOPILOT: 999,
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
    code: str = ""
    password_2fa: str | None = None


class VerifyResponse(BaseModel):
    status: str
    requires_2fa: bool = False
    message: str = ""


class SourceCreateRequest(BaseModel):
    telegram_id_or_username: str
    type: ExportSourceType = ExportSourceType.CHANNEL
    title: str | None = None


class SourceResponse(BaseModel):
    id: str
    telegram_id: int
    telegram_type: str
    username: str | None = None
    title: str
    auto_export: bool = False
    total_messages: int = 0
    total_chunks: int = 0
    total_authors: int = 0
    last_export_at: str | None = None
    created_at: str | None = None

    class Config:
        from_attributes = True


class JobCreateRequest(BaseModel):
    source_id: str
    config: dict[str, Any] = Field(default_factory=dict)


class JobResponse(BaseModel):
    id: str
    source_id: str | None = None
    source_name: str
    source_type: str
    status: str
    total_messages: int | None = None
    processed_messages: int = 0
    total_chunks: int = 0
    error_message: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None

    class Config:
        from_attributes = True


class SearchRequest(BaseModel):
    query: str
    source_ids: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None
    min_reactions: int | None = None
    limit: int = Field(default=5, ge=1, le=50)


class SearchResultItem(BaseModel):
    id: str
    score: float
    payload: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
    total: int


class PopularResponse(BaseModel):
    posts: list[dict[str, Any]]


class AuthorsResponse(BaseModel):
    authors: list[dict[str, Any]]


class ActivityResponse(BaseModel):
    total_messages: int = 0
    total_sources: int = 0
    by_hour: dict[str, int] = Field(default_factory=dict)
    by_weekday: dict[str, int] = Field(default_factory=dict)
    recent_daily: list[dict[str, Any]] = Field(default_factory=list)


class FolderItem(BaseModel):
    id: int
    title: str


# ── Helpers ──────────────────────────────────────────────────────────────────


def _get_fernet():
    from cryptography.fernet import Fernet

    encryption_key = settings.telegram_encryption_key
    if not encryption_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Telegram encryption not configured",
        )
    return Fernet(encryption_key.encode())


def _source_to_dict(source: ExportSource) -> dict:
    return {
        "id": str(source.id),
        "telegram_id": source.telegram_id,
        "telegram_type": source.telegram_type.value,
        "username": source.username,
        "title": source.title,
        "auto_export": source.auto_export,
        "total_messages": source.total_messages,
        "total_chunks": source.total_chunks,
        "total_authors": source.total_authors,
        "last_export_at": source.last_export_at.isoformat() if source.last_export_at else None,
        "created_at": source.created_at.isoformat() if source.created_at else None,
    }


def _job_to_dict(job: ExportJob) -> dict:
    return {
        "id": str(job.id),
        "source_id": str(job.source_id) if job.source_id else None,
        "source_name": job.source_name,
        "source_type": job.source_type.value,
        "status": job.status.value,
        "total_messages": job.total_messages,
        "processed_messages": job.processed_messages,
        "total_chunks": job.total_chunks,
        "error_message": job.error_message,
        "config": job.config or {},
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


async def _get_active_session(user_id: uuid.UUID, db: AsyncSession) -> TelegramSession:
    """Get the user's active Telegram session or raise 400."""
    result = await db.execute(
        select(TelegramSession).where(
            TelegramSession.user_id == user_id,
            TelegramSession.is_active.is_(True),
        ).order_by(TelegramSession.created_at.desc())
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active Telegram session. Use /connect first.",
        )
    return session


# ── POST /connect — Init Telethon session ────────────────────────────────────


@router.post("/connect", response_model=ConnectResponse)
async def connect_telegram(
    body: ConnectRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Initialize a Telegram session. Encrypts api_hash and stores in DB.

    Sends a verification code to the user's phone via Telethon.
    """
    fernet = _get_fernet()
    encrypted_hash = fernet.encrypt(body.api_hash.encode()).decode()

    # Deactivate any existing sessions
    existing = await db.execute(
        select(TelegramSession).where(
            TelegramSession.user_id == user.id,
            TelegramSession.is_active.is_(True),
        )
    )
    for old_session in existing.scalars().all():
        old_session.is_active = False

    session = TelegramSession(
        user_id=user.id,
        phone=body.phone,
        api_id=body.api_id,
        api_hash_encrypted=encrypted_hash,
    )
    db.add(session)
    await db.flush()

    # Send verification code via Telethon
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        client = TelegramClient(StringSession(), body.api_id, body.api_hash)
        await client.connect()
        sent_code = await client.send_code_request(body.phone)

        # Store phone_code_hash temporarily (encrypted) for verify step
        phone_code_hash = sent_code.phone_code_hash
        session.session_string_encrypted = fernet.encrypt(
            f"pending:{phone_code_hash}".encode()
        ).decode()
        await db.flush()

        await client.disconnect()
    except Exception as e:
        logger.exception("Failed to send Telegram verification code")
        await db.delete(session)
        await db.flush()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to connect to Telegram: {str(e)[:200]}",
        )

    return {"session_id": str(session.id), "status": "code_required"}


# ── POST /verify — Verify code / 2FA ────────────────────────────────────────


@router.post("/verify", response_model=VerifyResponse)
async def verify_telegram(
    body: VerifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Verify the Telegram code (and optional 2FA password).

    On success, stores the encrypted StringSession for future use.
    """
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

    fernet = _get_fernet()
    api_hash = fernet.decrypt(tg_session.api_hash_encrypted.encode()).decode()

    # Decrypt pending phone_code_hash
    pending_data = ""
    if tg_session.session_string_encrypted:
        pending_data = fernet.decrypt(tg_session.session_string_encrypted.encode()).decode()

    phone_code_hash = pending_data.replace("pending:", "") if pending_data.startswith("pending:") else ""

    try:
        from telethon import TelegramClient
        from telethon.errors import SessionPasswordNeededError
        from telethon.sessions import StringSession

        client = TelegramClient(StringSession(), tg_session.api_id, api_hash)
        await client.connect()

        if body.password_2fa:
            # 2FA step
            await client.sign_in(password=body.password_2fa)
        else:
            try:
                await client.sign_in(
                    phone=tg_session.phone,
                    code=body.code,
                    phone_code_hash=phone_code_hash,
                )
            except SessionPasswordNeededError:
                await client.disconnect()
                return {
                    "status": "2fa_required",
                    "requires_2fa": True,
                    "message": "Two-factor authentication required",
                }

        # Save the authenticated session string (encrypted)
        session_string = client.session.save()
        tg_session.session_string_encrypted = fernet.encrypt(
            session_string.encode()
        ).decode()
        tg_session.is_active = True
        tg_session.last_used_at = datetime.utcnow()
        await db.flush()

        await client.disconnect()

    except SessionPasswordNeededError:
        return {
            "status": "2fa_required",
            "requires_2fa": True,
            "message": "Two-factor authentication required",
        }
    except Exception as e:
        logger.exception("Failed to verify Telegram session")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Verification failed: {str(e)[:200]}",
        )

    return {
        "status": "connected",
        "requires_2fa": False,
        "message": "Telegram account connected successfully",
    }


# ── GET /sources — List export sources ───────────────────────────────────────


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
    return [_source_to_dict(s) for s in result.scalars().all()]


# ── POST /sources — Add export source ───────────────────────────────────────


@router.post("/sources", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def add_source(
    body: SourceCreateRequest,
    user: User = Depends(get_current_user),
    subscription: Subscription = Depends(get_active_subscription),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Register a new Telegram source for export.

    Resolves the username/ID via the user's connected Telethon session
    to get the entity title and numeric Telegram ID.
    """
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

    # Get active Telegram session for entity resolution
    tg_session = await _get_active_session(user.id, db)
    fernet = _get_fernet()
    api_hash = fernet.decrypt(tg_session.api_hash_encrypted.encode()).decode()
    session_string_raw = fernet.decrypt(tg_session.session_string_encrypted.encode()).decode()

    # Resolve entity via Telethon
    tg_input = body.telegram_id_or_username.lstrip("@")
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        client = TelegramClient(StringSession(session_string_raw), tg_session.api_id, api_hash)
        await client.connect()

        identifier: int | str = tg_input
        if tg_input.lstrip("-").isdigit():
            identifier = int(tg_input)

        entity = await client.get_entity(identifier)
        telegram_id = entity.id
        title = getattr(entity, "title", None) or getattr(entity, "first_name", "") or str(telegram_id)
        username = getattr(entity, "username", None)

        await client.disconnect()
    except Exception as e:
        logger.exception("Failed to resolve Telegram entity")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not find Telegram entity: {str(e)[:200]}",
        )

    # Check for duplicates
    existing = await db.execute(
        select(ExportSource).where(
            ExportSource.user_id == user.id,
            ExportSource.telegram_id == telegram_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This source is already added.",
        )

    source = ExportSource(
        user_id=user.id,
        telegram_id=telegram_id,
        telegram_type=body.type,
        username=username,
        title=body.title or title,
    )
    db.add(source)
    await db.flush()

    return _source_to_dict(source)


# ── DELETE /sources/{source_id} — Delete source + Qdrant data ────────────────


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete source and clean up associated Qdrant vectors and message metadata."""
    result = await db.execute(
        select(ExportSource).where(
            ExportSource.id == source_id,
            ExportSource.user_id == user.id,
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    # Clean up Qdrant vectors for this source
    try:
        from app.services.vectordb.qdrant_client import QdrantService

        qdrant = QdrantService(collection=source.qdrant_collection)
        import httpx

        async with httpx.AsyncClient(timeout=15) as http_client:
            await http_client.post(
                f"{qdrant.url}/collections/{qdrant.collection}/points/delete",
                headers=qdrant._headers,
                json={
                    "filter": {
                        "must": [
                            {"key": "source_id", "match": {"value": str(source_id)}},
                        ]
                    }
                },
            )
        logger.info("Deleted Qdrant points for source %s", source_id)
    except Exception:
        logger.exception("Failed to clean up Qdrant data for source %s", source_id)

    # Delete associated message metadata
    from sqlalchemy import delete

    await db.execute(
        delete(MessageMeta).where(MessageMeta.source_id == source_id)
    )

    await db.delete(source)


# ── POST /jobs — Start export ────────────────────────────────────────────────


@router.post("/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def start_export(
    body: JobCreateRequest,
    user: User = Depends(get_current_user),
    subscription: Subscription = Depends(get_active_subscription),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Start a new export job for the given source.

    Validates plan limits, checks for running exports, and dispatches
    the job to the Celery worker queue.
    """
    # Check weekly export limit
    weekly_limit = EXPORT_WEEKLY_LIMITS.get(subscription.plan, 1)
    week_ago = datetime.utcnow() - timedelta(days=7)
    count_result = await db.execute(
        select(func.count(ExportJob.id)).where(
            ExportJob.user_id == user.id,
            ExportJob.created_at >= week_ago,
        )
    )
    weekly_count = count_result.scalar() or 0
    if weekly_count >= weekly_limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Export limit reached ({weekly_limit}/week). Upgrade your plan.",
        )

    # Check for too many running exports
    running_result = await db.execute(
        select(func.count(ExportJob.id)).where(
            ExportJob.user_id == user.id,
            ExportJob.status.in_([
                ExportJobStatus.PROCESSING,
                ExportJobStatus.CHUNKING,
                ExportJobStatus.EMBEDDING,
            ]),
        )
    )
    running_count = running_result.scalar() or 0
    if running_count >= 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many running exports (max 3). Wait for completion.",
        )

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

    # Ensure user has a connected Telegram session
    tg_session = await _get_active_session(user.id, db)

    job = ExportJob(
        user_id=user.id,
        session_id=tg_session.id,
        source_id=source.id,
        source_type=source.telegram_type,
        source_tg_id=source.username or str(source.telegram_id),
        source_name=source.title,
        config=body.config,
        status=ExportJobStatus.PENDING,
    )
    db.add(job)
    await db.flush()

    # Dispatch to Celery worker
    try:
        from app.workers.celery_app import celery_app

        celery_app.send_task(
            "app.workers.tasks.run_export",
            kwargs={"job_id": str(job.id)},
        )
        logger.info("Dispatched export job %s to Celery", job.id)
    except Exception:
        logger.exception("Failed to dispatch export job %s to Celery", job.id)

    return _job_to_dict(job)


# ── GET /jobs — List export jobs ─────────────────────────────────────────────


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """List export jobs (history + active)."""
    result = await db.execute(
        select(ExportJob)
        .where(ExportJob.user_id == user.id)
        .order_by(ExportJob.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return [_job_to_dict(j) for j in result.scalars().all()]


# ── GET /jobs/{job_id} — Get job details ─────────────────────────────────────


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get export job details + progress."""
    result = await db.execute(
        select(ExportJob).where(ExportJob.id == job_id, ExportJob.user_id == user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_dict(job)


# ── POST /jobs/{job_id}/cancel — Cancel export ──────────────────────────────


@router.post("/jobs/{job_id}/cancel")
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

    active_statuses = (
        ExportJobStatus.PENDING,
        ExportJobStatus.PROCESSING,
        ExportJobStatus.CHUNKING,
        ExportJobStatus.EMBEDDING,
    )
    if job.status not in active_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job with status '{job.status.value}'",
        )

    job.status = ExportJobStatus.CANCELLED
    job.completed_at = datetime.utcnow()
    await db.flush()

    # Try to revoke Celery task
    try:
        from app.workers.celery_app import celery_app

        celery_app.control.revoke(str(job.id), terminate=True)
    except Exception:
        logger.exception("Failed to revoke Celery task for job %s", job.id)

    return _job_to_dict(job)


# ── POST /search — Semantic search ──────────────────────────────────────────


@router.post("/search", response_model=SearchResponse)
async def semantic_search(
    body: SearchRequest,
    user: User = Depends(get_current_user),
    subscription: Subscription = Depends(get_active_subscription),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Semantic search over exported Telegram data via RAG.

    Embeds the query, then searches Qdrant with optional metadata filters
    (source, date range, minimum reactions).
    """
    # Get user's sources for filtering
    source_query = select(ExportSource).where(ExportSource.user_id == user.id)
    if body.source_ids:
        source_uuids = [uuid.UUID(sid) for sid in body.source_ids]
        source_query = source_query.where(ExportSource.id.in_(source_uuids))
    source_result = await db.execute(source_query)
    sources = list(source_result.scalars().all())

    if not sources:
        return {"query": body.query, "results": [], "total": 0}

    source_id_strs = [str(s.id) for s in sources]

    # Build Qdrant filter
    must_conditions: list[dict[str, Any]] = [
        {"key": "source_id", "match": {"any": source_id_strs}},
    ]
    if body.date_from:
        must_conditions.append({"key": "date", "range": {"gte": body.date_from}})
    if body.date_to:
        must_conditions.append({"key": "date", "range": {"lte": body.date_to}})
    if body.min_reactions is not None:
        must_conditions.append({"key": "reactions_count", "range": {"gte": body.min_reactions}})

    # Generate embedding for the query
    try:
        from app.services.vectordb.embeddings import EmbeddingService

        embedding_svc = EmbeddingService()
        vectors = await embedding_svc.embed_texts([body.query])
        query_vector = vectors[0] if vectors else []
    except Exception:
        logger.exception("Failed to generate query embedding")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate search embedding",
        )

    if not query_vector:
        return {"query": body.query, "results": [], "total": 0}

    # Search Qdrant
    from app.services.vectordb.qdrant_client import QdrantService

    qdrant = QdrantService(collection="telegram_messages")
    results = await qdrant.search(
        vector=query_vector,
        limit=body.limit,
        filter_conditions={"must": must_conditions},
    )

    hits = [
        {
            "id": r["id"],
            "score": r["score"],
            "payload": r.get("payload", {}),
        }
        for r in results
    ]

    return {"query": body.query, "results": hits, "total": len(hits)}


# ── GET /analytics/popular — Popular posts ───────────────────────────────────


@router.get("/analytics/popular", response_model=PopularResponse)
async def analytics_popular(
    source_id: str | None = Query(default=None),
    min_reactions: int = Query(default=1, ge=0),
    limit: int = Query(default=10, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get the most popular messages sorted by reactions count."""
    base_filter = [ExportSource.user_id == user.id]
    if source_id:
        base_filter.append(MessageMeta.source_id == uuid.UUID(source_id))

    query = (
        select(MessageMeta)
        .join(ExportSource, MessageMeta.source_id == ExportSource.id)
        .where(*base_filter, MessageMeta.reactions_count >= min_reactions)
        .order_by(MessageMeta.reactions_count.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    messages = result.scalars().all()

    # Fetch source titles for display
    source_ids = list({m.source_id for m in messages})
    if source_ids:
        sources_result = await db.execute(
            select(ExportSource).where(ExportSource.id.in_(source_ids))
        )
        source_map = {s.id: s.title for s in sources_result.scalars().all()}
    else:
        source_map = {}

    posts = []
    for msg in messages:
        posts.append({
            "id": str(msg.id),
            "source_name": source_map.get(msg.source_id, "—"),
            "author_name": msg.author_name or msg.author_username or "—",
            "date": msg.date.isoformat() if msg.date else None,
            "reactions_count": msg.reactions_count,
            "views_count": msg.views_count,
            "forwards_count": msg.forwards_count,
            "replies_count": msg.replies_count,
            "text_preview": "",
            "has_media": msg.has_media,
        })

    return {"posts": posts}


# ── GET /analytics/authors — Top authors ─────────────────────────────────────


@router.get("/analytics/authors", response_model=AuthorsResponse)
async def analytics_authors(
    source_id: str | None = Query(default=None),
    export_job_id: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    user: User = Depends(get_current_user),
    subscription: Subscription = Depends(get_active_subscription),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get top authors by message count with aggregate stats."""
    base_filter = [
        ExportSource.user_id == user.id,
        MessageMeta.author_telegram_id.isnot(None),
    ]
    if source_id:
        base_filter.append(MessageMeta.source_id == uuid.UUID(source_id))
    if export_job_id:
        base_filter.append(MessageMeta.export_job_id == uuid.UUID(export_job_id))

    query = (
        select(
            MessageMeta.author_telegram_id,
            MessageMeta.author_username,
            MessageMeta.author_name,
            func.count().label("message_count"),
            func.avg(MessageMeta.reactions_count).label("avg_reactions"),
            func.sum(MessageMeta.views_count).label("total_views"),
        )
        .join(ExportSource, MessageMeta.source_id == ExportSource.id)
        .where(*base_filter)
        .group_by(
            MessageMeta.author_telegram_id,
            MessageMeta.author_username,
            MessageMeta.author_name,
        )
        .order_by(func.count().desc())
        .limit(limit)
    )

    result = await db.execute(query)
    rows = result.all()

    authors = []
    for row in rows:
        authors.append({
            "author_telegram_id": row.author_telegram_id,
            "author_username": row.author_username,
            "author_name": row.author_name or "Неизвестный",
            "message_count": row.message_count,
            "avg_reactions": round(float(row.avg_reactions or 0), 2),
            "total_views": int(row.total_views or 0),
        })

    return {"authors": authors}


# ── GET /analytics/activity — Activity stats ─────────────────────────────────


@router.get("/analytics/activity", response_model=ActivityResponse)
async def analytics_activity(
    source_id: str | None = Query(default=None),
    export_job_id: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    subscription: Subscription = Depends(get_active_subscription),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get activity distribution by hour, weekday, and recent daily trend."""
    base_filter = [ExportSource.user_id == user.id]
    if source_id:
        base_filter.append(MessageMeta.source_id == uuid.UUID(source_id))
    if export_job_id:
        base_filter.append(MessageMeta.export_job_id == uuid.UUID(export_job_id))

    # Total messages
    total_result = await db.execute(
        select(func.count())
        .select_from(MessageMeta)
        .join(ExportSource, MessageMeta.source_id == ExportSource.id)
        .where(*base_filter)
    )
    total_messages = total_result.scalar() or 0

    # Total sources
    sources_result = await db.execute(
        select(func.count(func.distinct(ExportSource.id)))
        .select_from(ExportSource)
        .where(ExportSource.user_id == user.id)
    )
    total_sources = sources_result.scalar() or 0

    # Activity by hour
    hour_query = (
        select(
            func.extract("hour", MessageMeta.date).label("hour"),
            func.count().label("count"),
        )
        .join(ExportSource, MessageMeta.source_id == ExportSource.id)
        .where(*base_filter)
        .group_by(func.extract("hour", MessageMeta.date))
        .order_by(func.extract("hour", MessageMeta.date))
    )
    hour_result = await db.execute(hour_query)
    by_hour = {str(int(row.hour)): row.count for row in hour_result.all()}

    # Activity by weekday (0 = Sunday in PG extract(dow), adjust to 0 = Monday)
    weekday_query = (
        select(
            func.extract("dow", MessageMeta.date).label("dow"),
            func.count().label("count"),
        )
        .join(ExportSource, MessageMeta.source_id == ExportSource.id)
        .where(*base_filter)
        .group_by(func.extract("dow", MessageMeta.date))
        .order_by(func.extract("dow", MessageMeta.date))
    )
    weekday_result = await db.execute(weekday_query)
    by_weekday = {str(int(row.dow)): row.count for row in weekday_result.all()}

    # Recent daily activity (last 14 days)
    two_weeks_ago = datetime.utcnow() - timedelta(days=14)
    daily_query = (
        select(
            func.date_trunc("day", MessageMeta.date).label("day"),
            func.count().label("count"),
        )
        .join(ExportSource, MessageMeta.source_id == ExportSource.id)
        .where(*base_filter, MessageMeta.date >= two_weeks_ago)
        .group_by(func.date_trunc("day", MessageMeta.date))
        .order_by(func.date_trunc("day", MessageMeta.date).desc())
    )
    daily_result = await db.execute(daily_query)
    recent_daily = [
        {"date": row.day.isoformat() if row.day else "", "count": row.count}
        for row in daily_result.all()
    ]

    return {
        "total_messages": total_messages,
        "total_sources": total_sources,
        "by_hour": by_hour,
        "by_weekday": by_weekday,
        "recent_daily": recent_daily,
    }


# ── GET /folders — List Telegram folders ─────────────────────────────────────


@router.get("/folders", response_model=list[FolderItem])
async def list_folders(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List Telegram dialog folders for the connected account."""
    tg_session = await _get_active_session(user.id, db)
    fernet = _get_fernet()

    api_hash = fernet.decrypt(tg_session.api_hash_encrypted.encode()).decode()
    session_string = fernet.decrypt(tg_session.session_string_encrypted.encode()).decode()

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.tl.functions.messages import GetDialogFiltersRequest

        client = TelegramClient(StringSession(session_string), tg_session.api_id, api_hash)
        await client.connect()

        result = await client(GetDialogFiltersRequest())
        folders = []
        for f in result:
            if hasattr(f, "title") and hasattr(f, "id"):
                folders.append({"id": f.id, "title": f.title})

        await client.disconnect()
        return folders
    except Exception as e:
        logger.exception("Failed to list Telegram folders")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to list folders: {str(e)[:200]}",
        )
