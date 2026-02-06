import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.subscription import PlanType
from app.models.user import User
from app.schemas.subscription import CheckoutRequest, CheckoutResponse, SubscriptionResponse
from app.services.billing_service import BillingService

settings = get_settings()
logger = logging.getLogger(__name__)
router = APIRouter()


class PortalResponse(BaseModel):
    portal_url: str


class SubscriptionDetailResponse(SubscriptionResponse):
    plan_display: str
    can_upgrade: bool


@router.get("/subscription", response_model=SubscriptionDetailResponse | None)
async def get_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict | None:
    svc = BillingService(db)
    sub = await svc.get_active_subscription(user.id)
    if not sub:
        return None
    return {
        "id": sub.id,
        "plan": sub.plan,
        "status": sub.status,
        "stripe_subscription_id": None,  # Don't leak internal Stripe IDs to client
        "plan_display": svc.get_plan_display_name(sub.plan),
        "can_upgrade": sub.plan != PlanType.ENTERPRISE,
    }


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CheckoutResponse:
    svc = BillingService(db)
    try:
        checkout_url = await svc.create_checkout_session(
            user=user,
            plan=body.plan,
            success_url=f"{settings.telegram_webhook_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.telegram_webhook_url}/billing/cancel",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except stripe.StripeError as e:
        logger.error("Stripe error creating checkout: %s", e)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Payment service error")

    return CheckoutResponse(checkout_url=checkout_url)


@router.post("/portal", response_model=PortalResponse)
async def create_portal(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortalResponse:
    """Create a Stripe Customer Portal session for managing subscription."""
    svc = BillingService(db)
    try:
        portal_url = await svc.create_portal_session(
            user=user,
            return_url=f"{settings.telegram_webhook_url}/billing",
        )
    except stripe.StripeError as e:
        logger.error("Stripe error creating portal: %s", e)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Payment service error")

    return PortalResponse(portal_url=portal_url)


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    event_type = event["type"]
    data = event["data"]["object"]
    svc = BillingService(db)

    logger.info("Stripe webhook received: %s", event_type)

    if event_type == "checkout.session.completed":
        await svc.handle_checkout_completed(data)

    elif event_type == "invoice.paid":
        await svc.handle_invoice_paid(data)

    elif event_type == "invoice.payment_failed":
        sub = await svc.handle_payment_failed(data)
        if sub:
            logger.warning("Payment failed for subscription %s", sub.id)

    elif event_type == "customer.subscription.deleted":
        await svc.handle_subscription_deleted(data)

    elif event_type == "customer.subscription.updated":
        await svc.handle_subscription_updated(data)

    return {"status": "ok"}
