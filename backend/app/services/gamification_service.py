"""Gamification v2 service — challenges, streaks, levels, coins, shop."""

from __future__ import annotations

import logging
import random
import uuid
from datetime import date, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_challenge import DailyChallenge
from app.models.user_gamification import UserGamification

logger = logging.getLogger(__name__)

# Level progression
LEVELS = [
    {"name": "trainee", "min_xp": 0, "label": "Trainee"},
    {"name": "junior", "min_xp": 100, "label": "Junior"},
    {"name": "senior", "min_xp": 500, "label": "Senior"},
    {"name": "expert", "min_xp": 1500, "label": "Expert"},
    {"name": "master", "min_xp": 5000, "label": "Master"},
]

# Challenge templates
CHALLENGE_TEMPLATES = [
    {"type": "sessions", "target": 3, "reward": 20, "label": "Complete 3 training sessions today"},
    {"type": "sessions", "target": 5, "reward": 35, "label": "Complete 5 training sessions today"},
    {"type": "avg_score", "target": 75, "reward": 30, "label": "Get an average score of 75+ today"},
    {"type": "avg_score", "target": 85, "reward": 50, "label": "Get an average score of 85+ today"},
    {"type": "scenario_type", "target": 1, "reward": 25, "label": "Practice a partner pitch scenario"},
    {"type": "perfect_criteria", "target": 1, "reward": 40, "label": "Score 90+ on any single criterion"},
]

# Shop items
SHOP_ITEMS = [
    {"id": "avatar_pro", "name": "Professional Avatar", "price": 200, "type": "avatar"},
    {"id": "theme_dark", "name": "Dark Theme Pro", "price": 150, "type": "theme"},
    {"id": "badge_star", "name": "Star Badge", "price": 100, "type": "badge"},
    {"id": "badge_fire", "name": "Fire Badge", "price": 100, "type": "badge"},
    {"id": "scenario_slot", "name": "Custom Scenario Slot", "price": 300, "type": "feature"},
    {"id": "hint_pack", "name": "AI Hint Pack (5 uses)", "price": 75, "type": "consumable"},
]


class GamificationService:
    """Manage gamification features: levels, coins, streaks, challenges."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_create_profile(self, user_id: uuid.UUID) -> UserGamification:
        result = await self.db.execute(
            select(UserGamification).where(UserGamification.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            profile = UserGamification(user_id=user_id)
            self.db.add(profile)
            await self.db.flush()
            await self.db.refresh(profile)
        return profile

    async def add_xp(self, user_id: uuid.UUID, amount: int) -> UserGamification:
        profile = await self.get_or_create_profile(user_id)
        profile.xp += amount

        # Check level up
        for level in reversed(LEVELS):
            if profile.xp >= level["min_xp"]:
                profile.level = level["name"]
                break

        await self.db.flush()
        return profile

    async def add_coins(self, user_id: uuid.UUID, amount: int) -> UserGamification:
        profile = await self.get_or_create_profile(user_id)
        profile.coins += amount
        await self.db.flush()
        return profile

    async def spend_coins(self, user_id: uuid.UUID, amount: int) -> bool:
        profile = await self.get_or_create_profile(user_id)
        if profile.coins < amount:
            return False
        profile.coins -= amount
        await self.db.flush()
        return True

    async def update_streak(self, user_id: uuid.UUID) -> UserGamification:
        profile = await self.get_or_create_profile(user_id)
        today = date.today()

        if profile.last_active_date == today:
            return profile  # Already counted today

        if profile.last_active_date == today - timedelta(days=1):
            profile.current_streak += 1
        else:
            profile.current_streak = 1

        if profile.current_streak > profile.longest_streak:
            profile.longest_streak = profile.current_streak

        profile.last_active_date = today
        await self.db.flush()
        return profile

    async def generate_daily_challenge(self, user_id: uuid.UUID) -> DailyChallenge | None:
        today = date.today()

        # Check if already generated
        existing = await self.db.execute(
            select(DailyChallenge).where(
                DailyChallenge.user_id == user_id,
                DailyChallenge.challenge_date == today,
            )
        )
        if existing.scalar_one_or_none():
            return None

        template = random.choice(CHALLENGE_TEMPLATES)
        challenge = DailyChallenge(
            user_id=user_id,
            challenge_type=template["type"],
            target=template["target"],
            reward_coins=template["reward"],
            label=template["label"],
            challenge_date=today,
        )
        self.db.add(challenge)
        await self.db.flush()
        await self.db.refresh(challenge)
        return challenge

    async def get_today_challenges(self, user_id: uuid.UUID) -> list[DailyChallenge]:
        result = await self.db.execute(
            select(DailyChallenge).where(
                DailyChallenge.user_id == user_id,
                DailyChallenge.challenge_date == date.today(),
            )
        )
        return list(result.scalars().all())

    async def complete_challenge(self, challenge_id: uuid.UUID) -> DailyChallenge | None:
        result = await self.db.execute(
            select(DailyChallenge).where(DailyChallenge.id == challenge_id)
        )
        challenge = result.scalar_one_or_none()
        if challenge and not challenge.is_completed:
            challenge.is_completed = True
            await self.add_coins(challenge.user_id, challenge.reward_coins)
            await self.db.flush()
        return challenge

    @staticmethod
    def get_shop_items() -> list[dict]:
        return SHOP_ITEMS

    async def purchase_item(self, user_id: uuid.UUID, item_id: str) -> dict:
        item = next((i for i in SHOP_ITEMS if i["id"] == item_id), None)
        if not item:
            return {"error": "Item not found"}

        success = await self.spend_coins(user_id, item["price"])
        if not success:
            return {"error": "Not enough coins"}

        return {"success": True, "item": item}

    async def record_session_completion(self, user_id: uuid.UUID, score: int) -> dict:
        """Call after each completed session to update gamification."""
        # Update streak
        profile = await self.update_streak(user_id)

        # Add XP: base 10 + score bonus
        xp_gain = 10 + score // 10
        await self.add_xp(user_id, xp_gain)

        # Add coins
        coin_gain = 5 + (score // 20)
        await self.add_coins(user_id, coin_gain)

        return {
            "xp_gained": xp_gain,
            "coins_gained": coin_gain,
            "current_streak": profile.current_streak,
            "level": profile.level,
        }
