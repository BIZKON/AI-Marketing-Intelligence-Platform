"""Push notifications API — subscribe/unsubscribe for Web Push, test delivery."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.push_service import PushService

settings = get_settings()
router = APIRouter()


class PushSubscribeRequest(BaseModel):
    endpoint: str
    p256dh_key: str
    auth_key: str


class PushSubscribeResponse(BaseModel):
    id: uuid.UUID
    endpoint: str


class VapidKeyResponse(BaseModel):
    public_key: str


class PushTestResponse(BaseModel):
    web_push_sent: int
    telegram_sent: bool


@router.get("/vapid-key", response_model=VapidKeyResponse)
async def get_vapid_public_key() -> VapidKeyResponse:
    """Get the VAPID public key for Web Push subscription."""
    return VapidKeyResponse(public_key=settings.vapid_public_key)


@router.post("/subscribe", response_model=PushSubscribeResponse)
async def subscribe_push(
    body: PushSubscribeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PushSubscribeResponse:
    """Register a Web Push subscription for the current user."""
    svc = PushService(db)
    sub = await svc.subscribe(
        user_id=user.id,
        endpoint=body.endpoint,
        p256dh_key=body.p256dh_key,
        auth_key=body.auth_key,
    )
    await db.commit()
    return PushSubscribeResponse(id=sub.id, endpoint=sub.endpoint)


@router.post("/unsubscribe")
async def unsubscribe_push(
    body: PushSubscribeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Remove a Web Push subscription."""
    svc = PushService(db)
    removed = await svc.unsubscribe(user.id, body.endpoint)
    await db.commit()
    return {"removed": removed}


@router.post("/test", response_model=PushTestResponse)
async def test_push(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PushTestResponse:
    """Send a test push notification to the current user (Web + Telegram)."""
    svc = PushService(db)
    result = await svc.notify_evaluation_complete(
        user_id=user.id,
        telegram_id=user.telegram_id,
        overall_score=85,
        session_id=uuid.uuid4(),
    )
    return PushTestResponse(
        web_push_sent=result["web_push_sent"],
        telegram_sent=result["telegram_sent"],
    )
