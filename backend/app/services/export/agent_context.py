"""Agent Context Provider — supplies RAG-powered context to AI agents (L2).

Replaces full-dump approach with semantic retrieval:
- Agents receive only relevant chunks instead of entire chat history
- 60-70% token savings on Claude API calls
- Better signal-to-noise ratio for analysis
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.export import ExportSource, MessageMeta
from app.services.rag.ingestion import RAGIngestionPipeline
from app.services.vectordb.embeddings import EmbeddingService
from app.services.vectordb.qdrant_client import QdrantService

logger = logging.getLogger(__name__)

# Period mapping
PERIOD_MAP = {
    "7d": 7,
    "14d": 14,
    "30d": 30,
    "90d": 90,
}


class AgentContextProvider:
    """Provides RAG-powered context for AI agents.

    Used by L2 agents (AnalystAgent, MarketerAgent, SalesAgent) to retrieve
    relevant content from exported Telegram channels instead of receiving
    raw data dumps.
    """

    def __init__(
        self,
        db: AsyncSession,
        rag_pipeline: RAGIngestionPipeline | None = None,
    ) -> None:
        self.db = db
        self.rag = rag_pipeline or RAGIngestionPipeline(
            embeddings=EmbeddingService(),
            qdrant=QdrantService(collection="telegram_messages"),
            db=db,
        )

    async def get_context_for_agent(
        self,
        agent_role: str,
        user_id: str,
        source_ids: list[str] | None = None,
        topic: str | None = None,
        time_period: str = "7d",
        max_chunks: int = 20,
    ) -> dict[str, Any]:
        """Retrieve relevant context for an AI agent via RAG.

        Args:
            agent_role: Agent type (analyst, marketer, sales, strategist, cx).
            user_id: MarketPulse user UUID.
            source_ids: Filter to specific export sources.
            topic: Optional topic to focus the semantic search.
            time_period: Time window (7d, 14d, 30d, 90d).
            max_chunks: Maximum chunks to include in context.

        Returns:
            Dict with 'context_text', 'metadata', 'sources_count'.
        """
        # Build a role-aware query
        query = self._build_role_query(agent_role, topic)

        # Calculate date range
        days = PERIOD_MAP.get(time_period, 7)
        date_from = datetime.now(timezone.utc) - timedelta(days=days)

        # Semantic search via RAG pipeline
        search_results = await self.rag.search(
            query=query,
            user_id=user_id,
            source_ids=source_ids,
            date_from=date_from,
            limit=max_chunks,
        )

        # Get analytics summary for richer context
        analytics_summary = await self._get_analytics_summary(
            user_id, source_ids, date_from,
        )

        # Format context for the agent
        context_pieces: list[str] = []

        if analytics_summary:
            context_pieces.append(f"--- Сводка аналитики ({time_period}) ---")
            context_pieces.append(analytics_summary)
            context_pieces.append("")

        if search_results:
            context_pieces.append("--- Релевантный контент из Telegram ---")
            for i, result in enumerate(search_results, 1):
                payload = result.get("payload", {})
                score = result.get("score", 0)
                text = payload.get("text", "")
                source_name = payload.get("source_name", "Unknown")
                date_str = payload.get("date", "")[:10] if payload.get("date") else ""
                reactions = payload.get("reactions_count", 0)
                views = payload.get("views_count", 0)

                header = f"[{i}] {source_name}"
                if date_str:
                    header += f" | {date_str}"
                if reactions:
                    header += f" | {reactions} реакций"
                if views:
                    header += f" | {views} просмотров"
                header += f" (релевантность: {score:.2f})"

                context_pieces.append(header)
                context_pieces.append(text[:500])
                context_pieces.append("")
        else:
            context_pieces.append("Данные из Telegram-экспорта не найдены.")

        context_text = "\n".join(context_pieces)

        return {
            "context_text": context_text,
            "chunks_used": len(search_results),
            "sources_count": len({r.get("payload", {}).get("source_id") for r in search_results}),
            "period": time_period,
            "agent_role": agent_role,
        }

    async def find_content_gaps(
        self,
        user_id: str,
        user_source_ids: list[str],
        competitor_source_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Find topics covered by competitors but not by the user.

        Used by L3 Content Planner.
        """
        # Get competitor top topics
        competitor_results = await self.rag.search(
            query="популярные темы, топ контент, вовлечённость",
            user_id=user_id,
            source_ids=competitor_source_ids,
            min_reactions=5,
            limit=30,
        )

        # Get user's own topics
        user_results = await self.rag.search(
            query="популярные темы, топ контент, вовлечённость",
            user_id=user_id,
            source_ids=user_source_ids,
            limit=30,
        )

        user_texts = {r.get("payload", {}).get("text", "")[:100] for r in user_results}

        gaps = []
        for result in competitor_results:
            payload = result.get("payload", {})
            text_preview = payload.get("text", "")[:100]
            # Simple heuristic: if user doesn't have similar content
            if text_preview and text_preview not in user_texts:
                gaps.append({
                    "topic_preview": payload.get("text", "")[:300],
                    "source_name": payload.get("source_name", ""),
                    "reactions": payload.get("reactions_count", 0),
                    "relevance_score": result.get("score", 0),
                })

        return gaps[:20]

    async def get_trending_topics(
        self,
        user_id: str,
        source_ids: list[str] | None = None,
        period: str = "7d",
    ) -> list[dict[str, Any]]:
        """Detect trending topics by comparing recent vs older content.

        Used by L3 Content Planner.
        """
        days = PERIOD_MAP.get(period, 7)
        recent_from = datetime.now(timezone.utc) - timedelta(days=days)
        older_from = datetime.now(timezone.utc) - timedelta(days=days * 3)

        # Recent popular content
        recent = await self.rag.search(
            query="тренды, вирусный контент, популярное",
            user_id=user_id,
            source_ids=source_ids,
            date_from=recent_from,
            min_reactions=3,
            limit=20,
        )

        # Older content for comparison
        older = await self.rag.search(
            query="тренды, вирусный контент, популярное",
            user_id=user_id,
            source_ids=source_ids,
            date_from=older_from,
            date_to=recent_from,
            limit=20,
        )

        # Extract trending: topics in recent that score higher than baseline
        older_avg_reactions = 0
        if older:
            older_avg_reactions = sum(
                r.get("payload", {}).get("reactions_count", 0) for r in older
            ) / len(older)

        trending = []
        for result in recent:
            payload = result.get("payload", {})
            reactions = payload.get("reactions_count", 0)
            if reactions > older_avg_reactions * 1.5:
                trending.append({
                    "topic_preview": payload.get("text", "")[:300],
                    "source_name": payload.get("source_name", ""),
                    "reactions": reactions,
                    "growth_vs_baseline": (
                        round(reactions / older_avg_reactions, 1) if older_avg_reactions else 0
                    ),
                    "date": payload.get("date", ""),
                })

        return sorted(trending, key=lambda t: t["reactions"], reverse=True)[:15]

    # ── Private helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _build_role_query(agent_role: str, topic: str | None) -> str:
        """Build a search query tailored to the agent's role."""
        role_queries = {
            "analyst": "конкурентный анализ, тренды, метрики, вовлечённость аудитории",
            "marketer": "контент стратегия, темы постов, форматы, вовлечённость подписчиков",
            "sales": "продажи, воронка, оффер, акция, CTA, промо, конверсия",
            "strategist": "стратегия, позиционирование, бренд, миссия, ценности",
            "cx": "обратная связь, жалобы, отзывы, клиентский опыт, NPS",
        }

        base_query = role_queries.get(agent_role, "маркетинг, контент, аналитика")
        if topic:
            return f"{topic}. {base_query}"
        return base_query

    async def _get_analytics_summary(
        self,
        user_id: str,
        source_ids: list[str] | None,
        date_from: datetime,
    ) -> str:
        """Build a text summary of analytics from PostgreSQL metadata."""
        from app.models.export import ExportSource, MessageMeta

        query = select(
            ExportSource.title,
            func.count(MessageMeta.id).label("msg_count"),
            func.coalesce(func.sum(MessageMeta.reactions_count), 0).label("total_reactions"),
            func.coalesce(func.sum(MessageMeta.views_count), 0).label("total_views"),
            func.coalesce(func.avg(MessageMeta.reactions_count), 0).label("avg_reactions"),
        ).join(
            MessageMeta, MessageMeta.source_id == ExportSource.id,
        ).where(
            ExportSource.user_id == user_id,
            MessageMeta.date >= date_from,
        )

        if source_ids:
            query = query.where(ExportSource.id.in_(source_ids))

        query = query.group_by(ExportSource.title)

        try:
            result = await self.db.execute(query)
            rows = result.all()
        except Exception:
            logger.exception("Failed to get analytics summary")
            return ""

        if not rows:
            return ""

        lines = []
        for row in rows:
            lines.append(
                f"• {row.title}: {row.msg_count} сообщений, "
                f"{int(row.total_views)} просмотров, "
                f"{int(row.total_reactions)} реакций "
                f"(ср. {float(row.avg_reactions):.1f}/пост)"
            )
        return "\n".join(lines)
