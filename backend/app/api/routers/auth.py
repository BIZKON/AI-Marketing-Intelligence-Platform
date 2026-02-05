from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.user import UserResponse
from app.services.user_service import UserService

router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None


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
    auth_date: int | None = None
    hash: str | None = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    is_new_user: bool = False
    user: UserResponse


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> dict:
    svc = UserService(db)
    try:
        user, token = await svc.register_email(
            email=body.email, password=body.password, full_name=body.full_name
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    return {
        "access_token": token,
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

    return {
        "access_token": token,
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

    return {
        "access_token": token,
        "token_type": "bearer",
        "is_new_user": is_new,
        "user": user,
    }
