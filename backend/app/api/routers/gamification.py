"""Gamification v2 routes — levels, coins, streaks, challenges, shop."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.gamification_service import GamificationService, LEVELS, SHOP_ITEMS

router = APIRouter()


@router.get("/profile")
async def get_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get user's gamification profile."""
    svc = GamificationService(db)
    profile = await svc.get_or_create_profile(user.id)
    return {
        "level": profile.level,
        "xp": profile.xp,
        "coins": profile.coins,
        "current_streak": profile.current_streak,
        "longest_streak": profile.longest_streak,
        "last_active_date": profile.last_active_date.isoformat() if profile.last_active_date else None,
    }


@router.get("/levels")
async def get_levels() -> list[dict]:
    """Get all level definitions."""
    return LEVELS


@router.get("/challenges")
async def get_challenges(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Get today's challenges for the user."""
    svc = GamificationService(db)
    # Generate if needed
    await svc.generate_daily_challenge(user.id)
    challenges = await svc.get_today_challenges(user.id)
    return [
        {
            "id": str(c.id),
            "type": c.challenge_type,
            "label": c.label,
            "target": c.target,
            "progress": c.progress,
            "reward_coins": c.reward_coins,
            "is_completed": c.is_completed,
        }
        for c in challenges
    ]


@router.post("/challenges/{challenge_id}/complete")
async def complete_challenge(
    challenge_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mark a challenge as completed."""
    svc = GamificationService(db)
    challenge = await svc.complete_challenge(uuid.UUID(challenge_id))
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return {
        "id": str(challenge.id),
        "is_completed": challenge.is_completed,
        "reward_coins": challenge.reward_coins,
    }


@router.get("/shop")
async def get_shop() -> list[dict]:
    """Get available shop items."""
    return SHOP_ITEMS


@router.post("/shop/{item_id}/purchase")
async def purchase_item(
    item_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Purchase an item from the shop."""
    svc = GamificationService(db)
    result = await svc.purchase_item(user.id, item_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/leaderboard")
async def get_leaderboard(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Get XP leaderboard."""
    from sqlalchemy import select, desc
    from app.models.user_gamification import UserGamification
    from app.models.user import User as UserModel

    result = await db.execute(
        select(UserGamification, UserModel.full_name, UserModel.email)
        .join(UserModel, UserGamification.user_id == UserModel.id)
        .order_by(desc(UserGamification.xp))
        .limit(limit)
    )
    rows = result.all()
    return [
        {
            "user_name": row[1] or row[2] or "Anonymous",
            "level": row[0].level,
            "xp": row[0].xp,
            "current_streak": row[0].current_streak,
        }
        for row in rows
    ]
