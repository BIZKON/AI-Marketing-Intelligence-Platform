"""AI content generation service — draft creation and platform adaptation.

Uses MarketerAgent to generate post drafts, then adapts them per platform.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.competitor import Competitor
from app.models.content_plan import ContentPlan
from app.models.content_task import ContentTask, TaskStatus
from app.models.user import User
from app.services.agents.base import BaseAgent, AgentResult
from app.services.agents.marketer import MarketerAgent

logger = logging.getLogger(__name__)

# Platform-specific constraints
PLATFORM_LIMITS = {
    "telegram": {"max_chars": 4096, "supports_markdown": True, "supports_html": True},
    "vk": {"max_chars": 15000, "supports_markdown": False, "supports_html": False},
    "youtube": {"max_chars": 5000, "supports_markdown": False, "supports_html": False},
    "instagram": {"max_chars": 2200, "supports_markdown": False, "supports_html": False},
}


class ContentGenerator:
    """Generate and adapt content drafts using AI agents."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.marketer = MarketerAgent()

    async def generate_draft(
        self,
        task: ContentTask,
        user: User,
    ) -> ContentTask:
        """Generate an AI draft for a content task.

        Takes the task's topic/key_points and produces a ready-to-review draft.
        Updates task.body with generated content and sets status to IN_REVIEW.
        """
        # Gather brand info
        brand_info = self._build_brand_info(user)

        # Get competitor context
        competitors = (await self.db.execute(
            select(Competitor).where(
                Competitor.user_id == user.id,
                Competitor.is_active.is_(True),
            )
        )).scalars().all()
        comp_ids = [str(c.id) for c in competitors]

        # Build generation prompt from task metadata
        metadata = task.metadata_json or {}
        key_points = metadata.get("key_points", [])
        hashtags = metadata.get("hashtags", [])

        prompt = self._build_generation_prompt(
            title=task.title,
            platform=task.platform,
            content_type=task.content_type or "text",
            key_points=key_points,
            hashtags=hashtags,
        )

        # Run AI agent
        result = await self.marketer.run(
            query=prompt,
            user_id=str(user.id),
            competitor_ids=comp_ids,
            brand_info=brand_info,
            target_platforms=[task.platform],
        )

        # Extract the generated content
        generated = self._extract_post_content(result)

        # Adapt to platform limits
        adapted = self._adapt_to_platform(generated, task.platform)

        # Update task
        task.body = adapted
        task.status = TaskStatus.IN_REVIEW
        task.metadata_json = {
            **(task.metadata_json or {}),
            "ai_generated": True,
            "ai_tokens_used": result.tokens_used,
            "ai_sources_used": result.sources_used,
        }

        await self.db.flush()
        logger.info("Generated draft for task %s (platform=%s)", task.id, task.platform)
        return task

    async def generate_plan_drafts(
        self,
        plan: ContentPlan,
        user: User,
    ) -> list[ContentTask]:
        """Generate drafts for all pending tasks in a content plan."""
        tasks = (await self.db.execute(
            select(ContentTask).where(
                ContentTask.content_plan_id == plan.id,
                ContentTask.status == TaskStatus.PENDING,
            )
        )).scalars().all()

        generated = []
        for task in tasks:
            try:
                await self.generate_draft(task, user)
                generated.append(task)
            except Exception:
                logger.exception("Failed to generate draft for task %s", task.id)

        logger.info(
            "Generated %d/%d drafts for plan %s",
            len(generated), len(tasks), plan.id,
        )
        return generated

    async def regenerate_draft(
        self,
        task: ContentTask,
        user: User,
        instructions: str = "",
    ) -> ContentTask:
        """Regenerate a draft with optional user instructions for adjustment."""
        brand_info = self._build_brand_info(user)

        competitors = (await self.db.execute(
            select(Competitor).where(
                Competitor.user_id == user.id,
                Competitor.is_active.is_(True),
            )
        )).scalars().all()
        comp_ids = [str(c.id) for c in competitors]

        metadata = task.metadata_json or {}
        key_points = metadata.get("key_points", [])

        prompt = (
            f"Перепиши пост для платформы {task.platform}.\n\n"
            f"Тема: {task.title}\n"
        )
        if key_points:
            prompt += f"Ключевые тезисы: {', '.join(key_points)}\n"
        if task.body:
            prompt += f"\nПредыдущий вариант:\n{task.body}\n"
        if instructions:
            prompt += f"\nИнструкции по переработке:\n{instructions}\n"

        prompt += "\nНапиши улучшенный вариант поста, готовый к публикации."

        result = await self.marketer.run(
            query=prompt,
            user_id=str(user.id),
            competitor_ids=comp_ids,
            brand_info=brand_info,
            target_platforms=[task.platform],
        )

        generated = self._extract_post_content(result)
        adapted = self._adapt_to_platform(generated, task.platform)

        task.body = adapted
        task.status = TaskStatus.IN_REVIEW
        task.metadata_json = {
            **(task.metadata_json or {}),
            "regenerated": True,
            "regeneration_instructions": instructions,
        }

        await self.db.flush()
        return task

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _build_brand_info(user: User) -> str:
        parts = []
        if user.brand_name:
            parts.append(f"Бренд: {user.brand_name}")
        if user.brand_industry:
            parts.append(f"Индустрия: {user.brand_industry}")
        if user.brand_description:
            parts.append(f"Описание: {user.brand_description}")
        if user.tone_of_voice:
            parts.append(f"Tone of voice: {user.tone_of_voice}")
        return "\n".join(parts)

    @staticmethod
    def _build_generation_prompt(
        title: str,
        platform: str,
        content_type: str,
        key_points: list[str],
        hashtags: list[str],
    ) -> str:
        limits = PLATFORM_LIMITS.get(platform, {})
        max_chars = limits.get("max_chars", 4096)

        prompt = (
            f"Напиши пост для платформы {platform}.\n\n"
            f"Тема: {title}\n"
            f"Формат: {content_type}\n"
            f"Лимит символов: {max_chars}\n"
        )
        if key_points:
            prompt += f"Ключевые тезисы:\n" + "\n".join(f"- {p}" for p in key_points) + "\n"
        if hashtags:
            prompt += f"Хэштеги: {' '.join(hashtags)}\n"

        prompt += (
            "\nТребования:\n"
            "- Пост должен быть готов к публикации\n"
            "- Используй подходящий для платформы стиль\n"
            "- Добавь призыв к действию (CTA)\n"
            "- Текст должен быть вовлекающим и полезным\n"
            "\nВерни ТОЛЬКО текст поста, без пояснений."
        )
        return prompt

    @staticmethod
    def _extract_post_content(result: AgentResult) -> str:
        """Extract the actual post content from AI response."""
        text = result.content.strip()

        # Remove common AI wrapper text
        for prefix in ("Вот пост:", "Вот готовый пост:", "Готовый пост:", "```"):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        if text.endswith("```"):
            text = text[:-3].strip()

        return text

    @staticmethod
    def _adapt_to_platform(text: str, platform: str) -> str:
        """Truncate content to platform limits."""
        limits = PLATFORM_LIMITS.get(platform, {})
        max_chars = limits.get("max_chars", 4096)

        if len(text) <= max_chars:
            return text

        # Truncate at word boundary
        truncated = text[:max_chars - 3]
        last_space = truncated.rfind(" ")
        if last_space > max_chars * 0.8:
            truncated = truncated[:last_space]
        return truncated + "..."
