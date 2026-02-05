import uuid

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = None
    timezone: str = "UTC"
    language: str = "ru"


class UserCreate(UserBase):
    telegram_id: int | None = None
    password: str | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    timezone: str | None = None
    language: str | None = None
    brand_name: str | None = None
    brand_description: str | None = None
    tone_of_voice: str | None = None


class UserResponse(UserBase):
    id: uuid.UUID
    telegram_id: int | None = None
    telegram_username: str | None = None
    is_active: bool
    brand_name: str | None = None

    model_config = {"from_attributes": True}
