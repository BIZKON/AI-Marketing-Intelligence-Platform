"""User service: manages users, authentication, and profile operations."""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.subscription import PlanType, Subscription, SubscriptionStatus
from app.models.user import User

settings = get_settings()


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.db.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def register_email(self, email: str, password: str, full_name: str | None = None) -> tuple[User, str]:
        """Register a new user by email + password. Returns (user, access_token)."""
        existing = await self.get_by_email(email)
        if existing:
            raise ValueError("Email already registered")

        user = User(
            email=email,
            hashed_password=get_password_hash(password),
            full_name=full_name,
        )
        self.db.add(user)
        await self.db.flush()

        # Auto-create a free Monitor subscription
        await self._create_default_subscription(user.id)

        token = create_access_token(data={"sub": str(user.id)})
        return user, token

    async def authenticate_email(self, email: str, password: str) -> tuple[User, str]:
        """Authenticate by email + password. Returns (user, access_token)."""
        user = await self.get_by_email(email)
        if not user or not user.hashed_password or not verify_password(password, user.hashed_password):
            raise ValueError("Invalid credentials")
        if not user.is_active:
            raise ValueError("User account is deactivated")

        token = create_access_token(data={"sub": str(user.id)})
        return user, token

    async def authenticate_telegram(
        self,
        telegram_id: int,
        username: str | None = None,
        full_name: str | None = None,
        auth_date: int | None = None,
        hash_value: str | None = None,
        **extra_fields: str,
    ) -> tuple[User, str, bool]:
        """Authenticate via Telegram. Returns (user, access_token, is_new_user).

        Hash verification is mandatory — requests without hash/auth_date are rejected.
        """
        if not hash_value or not auth_date:
            raise ValueError("Telegram authentication requires hash and auth_date")
        if not settings.telegram_bot_token:
            raise ValueError("Telegram bot token is not configured")

        # Reject stale auth data (older than 5 minutes)
        if abs(time.time() - auth_date) > 300:
            raise ValueError("Telegram authentication data is expired")

        self._verify_telegram_hash(
            telegram_id=telegram_id,
            username=username,
            first_name=extra_fields.get("first_name"),
            last_name=extra_fields.get("last_name"),
            photo_url=extra_fields.get("photo_url"),
            auth_date=auth_date,
            hash_value=hash_value,
        )

        user = await self.get_by_telegram_id(telegram_id)
        is_new = user is None

        if is_new:
            user = User(
                telegram_id=telegram_id,
                telegram_username=username,
                full_name=full_name,
            )
            self.db.add(user)
            await self.db.flush()
            await self._create_default_subscription(user.id)
        else:
            # Update username if changed
            if username and user.telegram_username != username:
                user.telegram_username = username

        token = create_access_token(data={"sub": str(user.id)})
        return user, token, is_new

    async def update_profile(self, user: User, **kwargs: str | None) -> User:
        """Update user profile fields."""
        allowed = {
            "full_name", "timezone", "language",
            "brand_name", "brand_description", "tone_of_voice",
        }
        for field, value in kwargs.items():
            if field in allowed and value is not None:
                setattr(user, field, value)
        await self.db.flush()
        return user

    async def link_telegram(self, user: User, telegram_id: int, username: str | None = None) -> User:
        """Link a Telegram account to an existing user."""
        existing = await self.get_by_telegram_id(telegram_id)
        if existing and existing.id != user.id:
            raise ValueError("This Telegram account is already linked to another user")
        user.telegram_id = telegram_id
        user.telegram_username = username
        await self.db.flush()
        return user

    async def _create_default_subscription(self, user_id: uuid.UUID) -> Subscription:
        """Create a default Monitor plan subscription for a new user."""
        sub = Subscription(
            user_id=user_id,
            plan=PlanType.MONITOR,
            status=SubscriptionStatus.ACTIVE,
        )
        self.db.add(sub)
        await self.db.flush()
        return sub

    @staticmethod
    def _verify_telegram_hash(
        telegram_id: int,
        auth_date: int,
        hash_value: str,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        photo_url: str | None = None,
    ) -> None:
        """Verify Telegram Login Widget data using HMAC-SHA256."""
        data_check: dict[str, str] = {"id": str(telegram_id), "auth_date": str(auth_date)}
        if username:
            data_check["username"] = username
        if first_name:
            data_check["first_name"] = first_name
        if last_name:
            data_check["last_name"] = last_name
        if photo_url:
            data_check["photo_url"] = photo_url

        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data_check.items()))
        secret_key = hashlib.sha256(settings.telegram_bot_token.encode()).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(computed_hash, hash_value):
            raise ValueError("Invalid Telegram authentication data")
