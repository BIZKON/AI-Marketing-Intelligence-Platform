from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token, decode_refresh_token
from app.schemas.user import UserResponse
from app.services.user_service import UserService

router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TelegramAuthRequest(BaseModel):
    telegram_id: int
    username: str | None = None
    full_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    is_new_user: bool = False
    user: UserResponse


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> dict:
    svc = UserService(db)
    try:
        user, token = await svc.register_email(
            email=body.email, password=body.password, full_name=body.full_name
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    refresh = create_refresh_token({"sub": str(user.id)})
    return {
        "access_token": token,
        "refresh_token": refresh,
        "token_type": "bearer",
        "is_new_user": True,
        "user": user,
    }


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> dict:
    svc = UserService(db)
    try:
        user, token = await svc.authenticate_email(email=body.email, password=body.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    refresh = create_refresh_token({"sub": str(user.id)})
    return {
        "access_token": token,
        "refresh_token": refresh,
        "token_type": "bearer",
        "is_new_user": False,
        "user": user,
    }


@router.post("/telegram", response_model=AuthResponse)
async def telegram_auth(body: TelegramAuthRequest, db: AsyncSession = Depends(get_db)) -> dict:
    svc = UserService(db)
    try:
        user, token, is_new = await svc.authenticate_telegram(
            telegram_id=body.telegram_id,
            username=body.username,
            full_name=body.full_name,
            auth_date=body.auth_date,
            hash_value=body.hash,
            first_name=body.first_name or "",
            last_name=body.last_name or "",
            photo_url=body.photo_url or "",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    refresh = create_refresh_token({"sub": str(user.id)})
    return {
        "access_token": token,
        "refresh_token": refresh,
        "token_type": "bearer",
        "is_new_user": is_new,
        "user": user,
    }


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """Exchange a valid refresh token for a new access token."""
    try:
        payload = decode_refresh_token(body.refresh_token)
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Missing sub claim")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    import uuid
    from sqlalchemy import select
    from app.models.user import User

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    new_access = create_access_token({"sub": str(user.id)})
    return {"access_token": new_access, "token_type": "bearer"}
