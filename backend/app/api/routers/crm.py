"""CRM integration routes — AmoCRM sync and client management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.crm_service import CRMService

router = APIRouter()


class SyncRequest(BaseModel):
    amo_domain: str
    access_token: str


@router.post("/sync")
async def sync_contacts(
    data: SyncRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Sync contacts from AmoCRM."""
    svc = CRMService(db)
    count = await svc.sync_contacts(data.amo_domain, data.access_token)
    return {"synced": count}


@router.get("/clients")
async def list_clients(
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List CRM clients."""
    svc = CRMService(db)
    clients = await svc.list_clients(limit)
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "phone": c.phone,
            "email": c.email,
            "tags": c.tags,
            "created_at": c.created_at.isoformat(),
        }
        for c in clients
    ]


@router.get("/clients/{client_id}")
async def get_client(
    client_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get CRM client details."""
    svc = CRMService(db)
    client = await svc.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return {
        "id": str(client.id),
        "name": client.name,
        "phone": client.phone,
        "email": client.email,
        "tags": client.tags,
        "custom_fields": client.custom_fields,
        "created_at": client.created_at.isoformat(),
    }


@router.get("/clients/{client_id}/prompt")
async def get_client_prompt(
    client_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a personalized training prompt based on CRM client data."""
    svc = CRMService(db)
    client = await svc.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    prompt = CRMService.build_personalized_prompt(client)
    return {"prompt": prompt, "client_name": client.name}
