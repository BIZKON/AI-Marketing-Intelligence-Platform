import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.subscription import PlanType, Subscription, SubscriptionStatus
from app.models.user import User
from app.schemas.subscription import CheckoutRequest, CheckoutResponse, SubscriptionResponse

settings = get_settings()
router = APIRouter()

PRICE_MAP = {
    PlanType.MONITOR: settings.stripe_price_monitor,
    PlanType.CREATOR: settings.stripe_price_creator,
    PlanType.AUTOPILOT: settings.stripe_price_autopilot,
    PlanType.ENTERPRISE: settings.stripe_price_enterprise,
}


@router.get("/subscription", response_model=SubscriptionResponse | None)
async def get_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Subscription | None:
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.created_at.desc())
    )
    return result.scalar_one_or_none()


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    user: User = Depends(get_current_user),
) -> CheckoutResponse:
    price_id = PRICE_MAP.get(body.plan)
    if not price_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid plan")

    stripe.api_key = settings.stripe_secret_key
    session = stripe.checkout.Session.create(
        customer=user.stripe_customer_id or None,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.telegram_webhook_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.telegram_webhook_url}/billing/cancel",
        metadata={"user_id": str(user.id), "plan": body.plan.value},
    )
    return CheckoutResponse(checkout_url=session.url)


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    stripe.api_key = settings.stripe_secret_key
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        user_id = data["metadata"]["user_id"]
        plan = PlanType(data["metadata"]["plan"])
        subscription = Subscription(
            user_id=user_id,
            plan=plan,
            status=SubscriptionStatus.ACTIVE,
            stripe_subscription_id=data.get("subscription"),
        )
        db.add(subscription)

    elif event_type == "invoice.paid":
        stripe_sub_id = data.get("subscription")
        if stripe_sub_id:
            result = await db.execute(
                select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
            )
            sub = result.scalar_one_or_none()
            if sub:
                sub.status = SubscriptionStatus.ACTIVE

    elif event_type == "invoice.payment_failed":
        stripe_sub_id = data.get("subscription")
        if stripe_sub_id:
            result = await db.execute(
                select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
            )
            sub = result.scalar_one_or_none()
            if sub:
                sub.status = SubscriptionStatus.PAST_DUE

    elif event_type == "customer.subscription.deleted":
        stripe_sub_id = data.get("id")
        if stripe_sub_id:
            result = await db.execute(
                select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
            )
            sub = result.scalar_one_or_none()
            if sub:
                sub.status = SubscriptionStatus.CANCELED

    return {"status": "ok"}
