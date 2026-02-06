"""Report generation service — weekly digests, alerts, and formatted reports.

Orchestrates AI agents to produce structured reports from competitor data.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.competitor import Competitor
from app.models.competitor_post import CompetitorPost
from app.models.report import Report, ReportType
from app.models.user import User
from app.services.agents.analyst import AnalystAgent
from app.services.agents.marketer import MarketerAgent

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generate various types of reports using AI agents."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.analyst = AnalystAgent()
        self.marketer = MarketerAgent()

    # ── Weekly Digest ────────────────────────────────────────────────────────

    async def generate_digest(
        self,
        user: User,
        competitor_ids: list[str] | None = None,
        days: int = 7,
    ) -> Report:
        """Generate a weekly competitive intelligence digest.

        Flow:
        1. Gather competitor activity stats for the period
        2. Run AnalystAgent with RAG for insights
        3. Format into a structured report
        4. Save as Report record
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        # Fetch competitors — cast string IDs to UUID (#037)
        if competitor_ids:
            uuid_ids = [uuid.UUID(cid) if not isinstance(cid, uuid.UUID) else cid for cid in competitor_ids]
            competitors = (await self.db.execute(
                select(Competitor).where(
                    Competitor.id.in_(uuid_ids),
                    Competitor.user_id == user.id,
                )
            )).scalars().all()
        else:
            competitors = (await self.db.execute(
                select(Competitor).where(
                    Competitor.user_id == user.id,
                    Competitor.is_active.is_(True),
                )
            )).scalars().all()

        if not competitors:
            return await self._create_empty_report(
                user, ReportType.DIGEST, "Нет активных конкурентов для анализа."
            )

        # Gather statistics
        stats = await self._gather_period_stats(competitors, since)
        stats_context = self._format_stats_context(stats)

        # Brand info for personalization
        brand_info = ""
        if user.brand_name:
            brand_info = f"Бренд: {user.brand_name}"
            if user.brand_industry:
                brand_info += f", Индустрия: {user.brand_industry}"
            if user.brand_description:
                brand_info += f"\nОписание: {user.brand_description}"

        # Run Analyst Agent
        comp_ids = [str(c.id) for c in competitors]
        analyst_result = await self.analyst.run(
            query="Создай еженедельный дайджест конкурентной разведки. "
                  "Выяви ключевые тренды, лучший контент, изменения в стратегиях конкурентов.",
            user_id=str(user.id),
            competitor_ids=comp_ids,
            extra_context=stats_context,
            brand_info=brand_info,
            period=f"последние {days} дней",
        )

        # Build report content
        report_content = {
            "period_days": days,
            "period_start": since.isoformat(),
            "period_end": datetime.now(timezone.utc).isoformat(),
            "competitors_analyzed": len(competitors),
            "total_posts": sum(s["post_count"] for s in stats.values()),
            "stats": stats,
            "ai_analysis": analyst_result.content,
            "structured_insights": analyst_result.structured_data,
            "sources_used": analyst_result.sources_used,
            "tokens_used": analyst_result.tokens_used,
        }

        # Format markdown
        markdown = self._format_digest_markdown(
            stats, analyst_result.content, competitors, days
        )

        report = Report(
            user_id=user.id,
            type=ReportType.DIGEST,
            title=f"Дайджест за {days} дн. ({datetime.now(timezone.utc).strftime('%d.%m.%Y')})",
            content=report_content,
            content_markdown=markdown,
        )
        self.db.add(report)
        await self.db.flush()

        logger.info("Generated digest report %s for user %s", report.id, user.id)
        return report

    # ── Alerts ───────────────────────────────────────────────────────────────

    async def check_alerts(
        self,
        user: User,
        hours: int = 24,
    ) -> list[Report]:
        """Check for alert-worthy events in the last N hours.

        Triggers:
        - Viral post (engagement > 3x average)
        - New competitor activity after silence (>7 days)
        - Significant engagement spike
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        alerts: list[Report] = []

        competitors = (await self.db.execute(
            select(Competitor).where(
                Competitor.user_id == user.id,
                Competitor.is_active.is_(True),
            )
        )).scalars().all()

        for competitor in competitors:
            # Get recent posts
            recent_posts = (await self.db.execute(
                select(CompetitorPost).where(
                    CompetitorPost.competitor_id == competitor.id,
                    CompetitorPost.published_at >= since,
                )
            )).scalars().all()

            if not recent_posts:
                continue

            # Get baseline engagement for this competitor
            avg_engagement = await self._get_avg_engagement(competitor.id)

            for post in recent_posts:
                total = post.likes + post.comments + post.shares
                if avg_engagement > 0 and total > avg_engagement * 3:
                    # Viral post detected
                    alert = Report(
                        user_id=user.id,
                        type=ReportType.ALERT,
                        title=f"🔥 Вирусный пост: {competitor.name}",
                        content={
                            "alert_type": "viral_post",
                            "competitor_id": str(competitor.id),
                            "competitor_name": competitor.name,
                            "post_id": str(post.id),
                            "post_url": post.url,
                            "engagement": total,
                            "avg_engagement": avg_engagement,
                            "multiplier": round(total / avg_engagement, 1),
                        },
                        content_markdown=(
                            f"**Вирусный пост у {competitor.name}**\n\n"
                            f"Вовлечённость: {total} (x{total / avg_engagement:.1f} от среднего)\n"
                            f"Платформа: {post.platform.value}\n"
                            f"Ссылка: {post.url or 'N/A'}\n\n"
                            f"Текст: {(post.text_content or '')[:300]}..."
                        ),
                    )
                    self.db.add(alert)
                    alerts.append(alert)

        if alerts:
            await self.db.flush()
            logger.info("Generated %d alerts for user %s", len(alerts), user.id)

        return alerts

    # ── Content Plan Generation ──────────────────────────────────────────────

    async def generate_content_plan(
        self,
        user: User,
        period: str = "weekly",
    ) -> dict:
        """Generate an AI-powered content plan using MarketerAgent.

        Returns structured content plan data.
        """
        competitors = (await self.db.execute(
            select(Competitor).where(
                Competitor.user_id == user.id,
                Competitor.is_active.is_(True),
            )
        )).scalars().all()

        brand_info = ""
        if user.brand_name:
            brand_info = f"Бренд: {user.brand_name}"
            if user.brand_industry:
                brand_info += f", Индустрия: {user.brand_industry}"
            if user.brand_description:
                brand_info += f"\nОписание: {user.brand_description}"

        comp_ids = [str(c.id) for c in competitors]
        target_platforms = list({p for c in competitors for p in c.platforms})

        result = await self.marketer.run(
            query=f"Создай {period} контент-план на основе анализа конкурентов.",
            user_id=str(user.id),
            competitor_ids=comp_ids,
            brand_info=brand_info,
            period=period,
            target_platforms=target_platforms,
        )

        return {
            "content": result.content,
            "structured_data": result.structured_data,
            "sources_used": result.sources_used,
        }

    # ── Helpers ──────────────────────────────────────────────────────────────

    async def _gather_period_stats(
        self,
        competitors: list[Competitor],
        since: datetime,
    ) -> dict[str, Any]:
        """Gather engagement statistics for each competitor in the period."""
        stats = {}
        for competitor in competitors:
            result = await self.db.execute(
                select(
                    func.count(CompetitorPost.id),
                    func.coalesce(func.sum(CompetitorPost.views), 0),
                    func.coalesce(func.sum(CompetitorPost.likes), 0),
                    func.coalesce(func.sum(CompetitorPost.comments), 0),
                    func.coalesce(func.sum(CompetitorPost.shares), 0),
                    func.coalesce(func.avg(CompetitorPost.engagement_rate), 0),
                ).where(
                    CompetitorPost.competitor_id == competitor.id,
                    CompetitorPost.published_at >= since,
                )
            )
            row = result.one()
            stats[str(competitor.id)] = {
                "name": competitor.name,
                "platforms": competitor.platforms,
                "post_count": row[0],
                "total_views": int(row[1]),
                "total_likes": int(row[2]),
                "total_comments": int(row[3]),
                "total_shares": int(row[4]),
                "avg_engagement_rate": float(row[5]),
            }
        return stats

    async def _get_avg_engagement(self, competitor_id: uuid.UUID) -> float:
        """Get average engagement for the last 30 posts."""
        # Use subquery to first select last 30 posts, then average their engagement
        subq = (
            select(
                (CompetitorPost.likes + CompetitorPost.comments + CompetitorPost.shares).label("total_engagement"),
            )
            .where(CompetitorPost.competitor_id == competitor_id)
            .order_by(CompetitorPost.published_at.desc())
            .limit(30)
            .subquery()
        )
        result = await self.db.execute(select(func.avg(subq.c.total_engagement)))
        avg = result.scalar()
        return float(avg) if avg else 0.0

    @staticmethod
    def _format_stats_context(stats: dict[str, Any]) -> str:
        """Format stats into readable context for the AI agent."""
        lines = ["Статистика конкурентов за период:\n"]
        for cid, s in stats.items():
            lines.append(
                f"• {s['name']} ({', '.join(s['platforms'])}): "
                f"{s['post_count']} постов, "
                f"{s['total_views']} просмотров, "
                f"{s['total_likes']} лайков, "
                f"{s['total_comments']} комментов, "
                f"{s['total_shares']} репостов, "
                f"ER: {s['avg_engagement_rate']:.4f}"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_digest_markdown(
        stats: dict,
        ai_analysis: str,
        competitors: list,
        days: int,
    ) -> str:
        """Format the digest as Markdown."""
        lines = [
            f"# Дайджест конкурентной разведки ({days} дн.)\n",
            f"**Дата:** {datetime.now(timezone.utc).strftime('%d.%m.%Y')}\n",
            f"**Конкурентов проанализировано:** {len(competitors)}\n",
            "---\n",
            "## Общая статистика\n",
        ]

        total_posts = sum(s["post_count"] for s in stats.values())
        total_views = sum(s["total_views"] for s in stats.values())
        lines.append(f"- Всего постов: **{total_posts}**")
        lines.append(f"- Суммарные просмотры: **{total_views:,}**\n")

        lines.append("| Конкурент | Посты | Просмотры | Лайки | ER |")
        lines.append("|-----------|-------|-----------|-------|----|")
        for s in stats.values():
            er = f"{s['avg_engagement_rate']:.4f}"
            lines.append(
                f"| {s['name']} | {s['post_count']} | {s['total_views']:,} | {s['total_likes']:,} | {er} |"
            )

        lines.append("\n---\n")
        lines.append("## AI Анализ\n")
        lines.append(ai_analysis)

        return "\n".join(lines)

    async def _create_empty_report(
        self,
        user: User,
        report_type: ReportType,
        message: str,
    ) -> Report:
        """Create a report with an informational message when no data is available."""
        report = Report(
            user_id=user.id,
            type=report_type,
            title="Отчёт",
            content={"status": "empty", "message": message},
            content_markdown=f"**{message}**\n\nДобавьте конкурентов через /add и подождите сбора данных.",
        )
        self.db.add(report)
        await self.db.flush()
        return report
