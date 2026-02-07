"""Scenario purchase service — Stripe one-time payments for premium training scenarios."""

from __future__ import annotations

import asyncio
import logging
import uuid

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.scenario_purchase import ScenarioPurchase
from app.models.training_scenario import TrainingScenario
from app.models.user import User

settings = get_settings()
logger = logging.getLogger(__name__)


class ScenarioPurchaseService:
    """Handles one-time Stripe purchases for premium training scenarios."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        stripe.api_key = settings.stripe_secret_key

    async def has_purchased(self, user_id: uuid.UUID, scenario_id: uuid.UUID) -> bool:
        """Check if a user already owns a premium scenario."""
        result = await self.db.execute(
            select(ScenarioPurchase.id).where(
                ScenarioPurchase.user_id == user_id,
                ScenarioPurchase.scenario_id == scenario_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_user_purchases(self, user_id: uuid.UUID) -> list[ScenarioPurchase]:
        """Get all scenario purchases for a user."""
        result = await self.db.execute(
            select(ScenarioPurchase).where(ScenarioPurchase.user_id == user_id)
            .order_by(ScenarioPurchase.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_checkout(
        self,
        user: User,
        scenario: TrainingScenario,
        success_url: str,
        cancel_url: str,
    ) -> str:
        """Create a Stripe Checkout session for a one-time scenario purchase. Returns checkout URL."""
        # Check if already purchased
        if await self.has_purchased(user.id, scenario.id):
            raise ValueError("Scenario already purchased")

        price_cents = scenario.success_criteria.get("price_cents", 999) if scenario.success_criteria else 999

        # Ensure Stripe customer exists
        from app.services.billing_service import BillingService
        billing = BillingService(self.db)
        customer_id = await billing.ensure_stripe_customer(user)

        session = await asyncio.to_thread(
            stripe.checkout.Session.create,
            customer=customer_id,
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "unit_amount": price_cents,
                    "product_data": {
                        "name": f"Training: {scenario.title}",
                        "description": scenario.description or "Premium training scenario",
                    },
                },
                "quantity": 1,
            }],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "type": "scenario_purchase",
                "user_id": str(user.id),
                "scenario_id": str(scenario.id),
                "amount_cents": str(price_cents),
            },
        )
        return session.url

    async def handle_purchase_completed(self, data: dict) -> ScenarioPurchase | None:
        """Handle checkout.session.completed webhook for scenario purchases."""
        metadata = data.get("metadata", {})
        if metadata.get("type") != "scenario_purchase":
            return None

        user_id = uuid.UUID(metadata["user_id"])
        scenario_id = uuid.UUID(metadata["scenario_id"])
        amount_cents = int(metadata.get("amount_cents", 0))
        payment_intent_id = data.get("payment_intent")

        # Idempotency check
        if payment_intent_id:
            existing = await self.db.execute(
                select(ScenarioPurchase).where(
                    ScenarioPurchase.stripe_payment_intent_id == payment_intent_id
                )
            )
            if existing.scalar_one_or_none():
                logger.info("Idempotent skip: purchase already recorded for %s", payment_intent_id)
                return None

        purchase = ScenarioPurchase(
            user_id=user_id,
            scenario_id=scenario_id,
            stripe_payment_intent_id=payment_intent_id,
            amount_cents=amount_cents,
        )
        self.db.add(purchase)
        await self.db.flush()
        logger.info("Scenario purchase recorded: user=%s scenario=%s", user_id, scenario_id)
        return purchase

    async def list_premium_scenarios(self) -> list[dict]:
        """List all premium (non-public) scenarios with pricing."""
        result = await self.db.execute(
            select(TrainingScenario).where(TrainingScenario.is_public.is_(False))
        )
        scenarios = result.scalars().all()
        return [
            {
                "id": str(s.id),
                "title": s.title,
                "description": s.description,
                "difficulty": s.difficulty.value if hasattr(s.difficulty, "value") else s.difficulty,
                "price_cents": s.success_criteria.get("price_cents", 999) if s.success_criteria else 999,
                "tags": s.tags,
            }
            for s in scenarios
        ]
