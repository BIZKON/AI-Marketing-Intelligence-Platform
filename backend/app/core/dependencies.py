import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import ALGORITHM
from app.models.subscription import PlanType, Subscription, SubscriptionStatus
from app.models.user import User

settings = get_settings()
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


async def get_active_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Subscription:
    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]),
        )
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active subscription")
    return subscription


def require_plan(min_plan: PlanType):
    """Dependency that checks if user has at least the specified plan level."""
    plan_order = {
        PlanType.MONITOR: 0,
        PlanType.CREATOR: 1,
        PlanType.AUTOPILOT: 2,
        PlanType.ENTERPRISE: 3,
    }

    async def _check(subscription: Subscription = Depends(get_active_subscription)) -> Subscription:
        if plan_order[subscription.plan] < plan_order[min_plan]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature requires {min_plan.value} plan or higher",
            )
        return subscription

    return _check
