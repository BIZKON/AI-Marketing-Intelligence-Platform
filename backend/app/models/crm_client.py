"""CRM client model — synced contacts from AmoCRM."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CRMClient(Base):
    __tablename__ = "crm_clients"

    amocrm_contact_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, nullable=True,
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(320))
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)))
    custom_fields: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    last_sync_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<CRMClient {self.id} name={self.name!r}>"
