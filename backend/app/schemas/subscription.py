import uuid

from pydantic import BaseModel

from app.models.subscription import PlanType, SubscriptionStatus


class SubscriptionResponse(BaseModel):
    id: uuid.UUID
    plan: PlanType
    status: SubscriptionStatus
    stripe_subscription_id: str | None = None

    model_config = {"from_attributes": True}


class CheckoutRequest(BaseModel):
    plan: PlanType


class CheckoutResponse(BaseModel):
    checkout_url: str
