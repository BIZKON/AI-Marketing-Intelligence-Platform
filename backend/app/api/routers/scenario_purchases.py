"""Scenario purchases API — buy premium training scenarios via Stripe."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.scenario_purchase_service import ScenarioPurchaseService
from app.services.training_service import TrainingService

settings = get_settings()
router = APIRouter()


class PurchaseCheckoutRequest(BaseModel):
    scenario_id: uuid.UUID


class PurchaseCheckoutResponse(BaseModel):
    checkout_url: str


class PremiumScenarioResponse(BaseModel):
    id: str
    title: str
    description: str | None = None
    difficulty: str
    price_cents: int
    tags: list[str] | None = None


class PurchaseResponse(BaseModel):
    id: uuid.UUID
    scenario_id: uuid.UUID
    amount_cents: int
    currency: str
    created_at: str | None = None


@router.get("/premium-scenarios", response_model=list[PremiumScenarioResponse])
async def list_premium_scenarios(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PremiumScenarioResponse]:
    """List all premium training scenarios available for purchase."""
    svc = ScenarioPurchaseService(db)
    data = await svc.list_premium_scenarios()
    return [PremiumScenarioResponse(**s) for s in data]


@router.get("/my-purchases", response_model=list[PurchaseResponse])
async def my_purchases(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PurchaseResponse]:
    """List all scenarios purchased by the current user."""
    svc = ScenarioPurchaseService(db)
    purchases = await svc.get_user_purchases(user.id)
    return [
        PurchaseResponse(
            id=p.id,
            scenario_id=p.scenario_id,
            amount_cents=p.amount_cents,
            currency=p.currency,
            created_at=p.created_at.isoformat() if p.created_at else None,
        )
        for p in purchases
    ]


@router.post("/checkout", response_model=PurchaseCheckoutResponse)
async def create_purchase_checkout(
    body: PurchaseCheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PurchaseCheckoutResponse:
    """Create a Stripe Checkout session for a one-time scenario purchase."""
    training_svc = TrainingService(db)
    scenario = await training_svc.get_scenario(body.scenario_id)
    if not scenario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found")

    svc = ScenarioPurchaseService(db)
    try:
        checkout_url = await svc.create_checkout(
            user=user,
            scenario=scenario,
            success_url=f"{settings.cors_origins.split(',')[0]}/training?purchased=true",
            cancel_url=f"{settings.cors_origins.split(',')[0]}/training?cancelled=true",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    await db.commit()
    return PurchaseCheckoutResponse(checkout_url=checkout_url)


@router.get("/check/{scenario_id}")
async def check_purchase(
    scenario_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Check if the current user has purchased a specific scenario."""
    svc = ScenarioPurchaseService(db)
    purchased = await svc.has_purchased(user.id, scenario_id)
    return {"purchased": purchased}
