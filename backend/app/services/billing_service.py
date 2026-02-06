"""Billing service: manages Stripe integration, subscriptions, and plan changes."""

from __future__ import annotations

import asyncio
import logging
import uuid

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.subscription import PlanType, Subscription, SubscriptionStatus
from app.models.user import User

settings = get_settings()
logger = logging.getLogger(__name__)

PRICE_MAP: dict[PlanType, str] = {
    PlanType.MONITOR: settings.stripe_price_monitor,
    PlanType.CREATOR: settings.stripe_price_creator,
    PlanType.AUTOPILOT: settings.stripe_price_autopilot,
    PlanType.ENTERPRISE: settings.stripe_price_enterprise,
}

PLAN_PRICES: dict[PlanType, int] = {
    PlanType.MONITOR: 149_00,
    PlanType.CREATOR: 499_00,
    PlanType.AUTOPILOT: 999_00,
    PlanType.ENTERPRISE: 2500_00,
}

PLAN_ORDER: dict[PlanType, int] = {
    PlanType.MONITOR: 0,
    PlanType.CREATOR: 1,
    PlanType.AUTOPILOT: 2,
    PlanType.ENTERPRISE: 3,
}

GRACE_PERIOD_DAYS = 3


class BillingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        stripe.api_key = settings.stripe_secret_key

    async def get_active_subscription(self, user_id: uuid.UUID) -> Subscription | None:
        result = await self.db.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]),
            )
            .order_by(Subscription.created_at.desc())
        )
        return result.scalar_one_or_none()

    async def get_subscription_by_stripe_id(self, stripe_sub_id: str) -> Subscription | None:
        result = await self.db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
        )
        return result.scalar_one_or_none()

    async def ensure_stripe_customer(self, user: User) -> str:
        """Ensure the user has a Stripe customer ID. Create one if missing."""
        if user.stripe_customer_id:
            return user.stripe_customer_id

        customer = await asyncio.to_thread(
            stripe.Customer.create,
            email=user.email,
            name=user.full_name,
            metadata={"user_id": str(user.id), "telegram_id": str(user.telegram_id or "")},
        )
        user.stripe_customer_id = customer.id
        await self.db.flush()
        return customer.id

    async def create_checkout_session(
        self,
        user: User,
        plan: PlanType,
        success_url: str,
        cancel_url: str,
        trial_days: int | None = None,
    ) -> str:
        """Create a Stripe Checkout Session. Returns checkout URL."""
        price_id = PRICE_MAP.get(plan)
        if not price_id:
            raise ValueError(f"No Stripe price configured for plan: {plan.value}")

        customer_id = await self.ensure_stripe_customer(user)

        params: dict = {
            "customer": customer_id,
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": {"user_id": str(user.id), "plan": plan.value},
            "allow_promotion_codes": True,
        }

        if trial_days:
            params["subscription_data"] = {"trial_period_days": trial_days}

        session = await asyncio.to_thread(stripe.checkout.Session.create, **params)
        return session.url

    async def create_portal_session(self, user: User, return_url: str) -> str:
        """Create a Stripe Customer Portal session. Returns portal URL."""
        customer_id = await self.ensure_stripe_customer(user)
        session = await asyncio.to_thread(
            stripe.billing_portal.Session.create,
            customer=customer_id,
            return_url=return_url,
        )
        return session.url

    async def handle_checkout_completed(self, data: dict) -> Subscription:
        """Handle checkout.session.completed webhook event (idempotent)."""
        user_id = uuid.UUID(data["metadata"]["user_id"])
        plan = PlanType(data["metadata"]["plan"])
        stripe_sub_id = data.get("subscription")

        # Idempotency: if this Stripe subscription already exists, skip creation
        if stripe_sub_id:
            existing = await self.get_subscription_by_stripe_id(stripe_sub_id)
            if existing:
                logger.info("Idempotent skip: subscription %s already exists", stripe_sub_id)
                return existing

        # Deactivate any existing subscriptions
        await self._deactivate_existing_subscriptions(user_id)

        # Retrieve the Stripe subscription to get the price_id (run in thread to avoid blocking)
        stripe_price_id = None
        if stripe_sub_id:
            stripe_sub = await asyncio.to_thread(stripe.Subscription.retrieve, stripe_sub_id)
            if stripe_sub.get("items", {}).get("data"):
                stripe_price_id = stripe_sub["items"]["data"][0]["price"]["id"]

        sub = Subscription(
            user_id=user_id,
            plan=plan,
            status=SubscriptionStatus.ACTIVE,
            stripe_subscription_id=stripe_sub_id,
            stripe_price_id=stripe_price_id,
        )
        self.db.add(sub)
        await self.db.flush()
        logger.info("Subscription activated: user=%s plan=%s", user_id, plan.value)
        return sub

    async def handle_invoice_paid(self, data: dict) -> None:
        """Handle invoice.paid webhook — renew subscription."""
        stripe_sub_id = data.get("subscription")
        if not stripe_sub_id:
            return
        sub = await self.get_subscription_by_stripe_id(stripe_sub_id)
        if sub and sub.status != SubscriptionStatus.ACTIVE:
            sub.status = SubscriptionStatus.ACTIVE
            logger.info("Subscription renewed: %s", sub.id)

    async def handle_payment_failed(self, data: dict) -> Subscription | None:
        """Handle invoice.payment_failed webhook — set grace period."""
        stripe_sub_id = data.get("subscription")
        if not stripe_sub_id:
            return None
        sub = await self.get_subscription_by_stripe_id(stripe_sub_id)
        if sub:
            sub.status = SubscriptionStatus.PAST_DUE
            logger.warning("Payment failed, grace period started: sub=%s", sub.id)
        return sub

    async def handle_subscription_deleted(self, data: dict) -> Subscription | None:
        """Handle customer.subscription.deleted webhook — cancel subscription."""
        stripe_sub_id = data.get("id")
        if not stripe_sub_id:
            return None
        sub = await self.get_subscription_by_stripe_id(stripe_sub_id)
        if sub:
            sub.status = SubscriptionStatus.CANCELED
            logger.info("Subscription canceled: %s", sub.id)

            # Create a fallback free Monitor plan
            fallback = Subscription(
                user_id=sub.user_id,
                plan=PlanType.MONITOR,
                status=SubscriptionStatus.ACTIVE,
            )
            self.db.add(fallback)
        return sub

    async def handle_subscription_updated(self, data: dict) -> Subscription | None:
        """Handle customer.subscription.updated webhook — plan change."""
        stripe_sub_id = data.get("id")
        if not stripe_sub_id:
            return None
        sub = await self.get_subscription_by_stripe_id(stripe_sub_id)
        if not sub:
            return None

        # Detect plan change from the price ID
        items = data.get("items", {}).get("data", [])
        if items:
            new_price_id = items[0].get("price", {}).get("id")
            new_plan = self._price_id_to_plan(new_price_id)
            if new_plan and new_plan != sub.plan:
                old_plan = sub.plan
                sub.plan = new_plan
                sub.stripe_price_id = new_price_id
                logger.info("Plan changed: sub=%s %s -> %s", sub.id, old_plan.value, new_plan.value)

        # Update status
        stripe_status = data.get("status")
        if stripe_status == "active":
            sub.status = SubscriptionStatus.ACTIVE
        elif stripe_status == "past_due":
            sub.status = SubscriptionStatus.PAST_DUE
        elif stripe_status == "trialing":
            sub.status = SubscriptionStatus.TRIALING
        elif stripe_status in ("canceled", "unpaid"):
            sub.status = SubscriptionStatus.CANCELED

        return sub

    async def _deactivate_existing_subscriptions(self, user_id: uuid.UUID) -> None:
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]),
            )
        )
        for sub in result.scalars().all():
            sub.status = SubscriptionStatus.CANCELED

    @staticmethod
    def _price_id_to_plan(price_id: str | None) -> PlanType | None:
        if not price_id:
            return None
        for plan, pid in PRICE_MAP.items():
            if pid == price_id:
                return plan
        return None

    @staticmethod
    def get_plan_display_name(plan: PlanType) -> str:
        names = {
            PlanType.MONITOR: "Monitor ($149/мес)",
            PlanType.CREATOR: "Creator ($499/мес)",
            PlanType.AUTOPILOT: "Autopilot ($999/мес)",
            PlanType.ENTERPRISE: "Enterprise ($2500+/мес)",
        }
        return names.get(plan, plan.value)
