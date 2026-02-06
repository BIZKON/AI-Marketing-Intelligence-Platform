"""AmoCRM integration service — sync contacts and log training activities."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.crm_client import CRMClient

logger = logging.getLogger(__name__)
settings = get_settings()


class CRMService:
    """Manage AmoCRM integration — contact sync and activity logging."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def sync_contacts(self, amo_domain: str, access_token: str) -> int:
        """Sync contacts from AmoCRM. Returns count of synced contacts."""
        synced = 0
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"https://{amo_domain}/api/v4/contacts",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"limit": 250},
                )
                resp.raise_for_status()
                data = resp.json()

            contacts = data.get("_embedded", {}).get("contacts", [])
            for contact in contacts:
                phone = None
                email = None
                tags = []

                # Extract phone and email from custom fields
                for field in contact.get("custom_fields_values", []):
                    if field.get("field_code") == "PHONE":
                        phone = field["values"][0]["value"] if field.get("values") else None
                    elif field.get("field_code") == "EMAIL":
                        email = field["values"][0]["value"] if field.get("values") else None

                for tag in contact.get("_embedded", {}).get("tags", []):
                    tags.append(tag.get("name", ""))

                # Upsert
                existing = await self.db.execute(
                    select(CRMClient).where(CRMClient.amocrm_contact_id == contact["id"])
                )
                crm_client = existing.scalar_one_or_none()

                if crm_client:
                    crm_client.name = contact.get("name", crm_client.name)
                    crm_client.phone = phone or crm_client.phone
                    crm_client.email = email or crm_client.email
                    crm_client.tags = tags if tags else crm_client.tags
                else:
                    crm_client = CRMClient(
                        amocrm_contact_id=contact["id"],
                        name=contact.get("name", "Unknown"),
                        phone=phone,
                        email=email,
                        tags=tags,
                    )
                    self.db.add(crm_client)
                synced += 1

            await self.db.flush()
            logger.info("Synced %d contacts from AmoCRM", synced)
        except Exception:
            logger.exception("AmoCRM sync failed")
        return synced

    async def list_clients(self, limit: int = 50) -> list[CRMClient]:
        result = await self.db.execute(
            select(CRMClient).order_by(CRMClient.name).limit(limit)
        )
        return list(result.scalars().all())

    async def get_client(self, client_id: str) -> CRMClient | None:
        import uuid
        result = await self.db.execute(
            select(CRMClient).where(CRMClient.id == uuid.UUID(client_id))
        )
        return result.scalar_one_or_none()

    async def log_training_to_crm(
        self, amo_domain: str, access_token: str,
        contact_id: int, score: int
    ) -> bool:
        """Log a training activity as a task in AmoCRM."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                import time
                resp = await client.post(
                    f"https://{amo_domain}/api/v4/tasks",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    json=[{
                        "text": f"Training completed: score {score}/100",
                        "entity_id": contact_id,
                        "entity_type": "contacts",
                        "complete_till": int(time.time()) + 86400,
                    }],
                )
                return resp.status_code in (200, 201)
        except Exception:
            logger.exception("Failed to log training to CRM")
            return False

    @staticmethod
    def build_personalized_prompt(client: CRMClient) -> str:
        """Build a system prompt personalized with CRM client data."""
        parts = [f"You are {client.name}, a real client from our CRM system."]
        if client.phone:
            parts.append(f"Your phone: {client.phone}")
        if client.tags:
            parts.append(f"Your interests/tags: {', '.join(client.tags)}")
        if client.custom_fields:
            notes = client.custom_fields.get("notes", "")
            if notes:
                parts.append(f"Background: {notes}")
        parts.append(
            "\nAct naturally based on this information. If the admin mentions "
            "your name or past interactions, acknowledge them."
        )
        return "\n".join(parts)
