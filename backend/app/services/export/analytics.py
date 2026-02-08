"""Export analytics — aggregate message metadata for insights and summaries.

Provides top posts, top authors, activity timelines, and export
summaries backed by PostgreSQL queries on the MessageMeta table.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.export import ExportJob, ExportSource, MessageMeta

logger = logging.getLogger(__name__)


class ExportAnalytics:
    """Aggregate analytics over exported message metadata."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_top_posts(
        self,
        source_id: uuid.UUID,
        limit: int = 50,
        min_reactions: int = 5,
    ) -> list[dict[str, Any]]:
        """Return the top posts by reaction count for a given source.

        Parameters
        ----------
        source_id:
            The ``ExportSource.id`` to filter by.
        limit:
            Maximum number of posts to return.
        min_reactions:
            Minimum reaction count threshold.

        Returns
        -------
        list[dict]
            Sorted by ``reactions_count`` descending. Each dict contains:
            ``message_id``, ``telegram_message_id``, ``date``, ``author_name``,
            ``author_username``, ``reactions_count``, ``views_count``,
            ``forwards_count``, ``has_media``, ``media_type``, ``text_length``.
        """
        stmt = (
            select(MessageMeta)
            .where(
                MessageMeta.source_id == source_id,
                MessageMeta.reactions_count >= min_reactions,
            )
            .order_by(MessageMeta.reactions_count.desc())
            .limit(limit)
        )

        result = await self._db.execute(stmt)
        rows = result.scalars().all()

        return [
            {
                "message_id": str(row.id),
                "telegram_message_id": row.telegram_message_id,
                "date": row.date.isoformat() if row.date else None,
                "author_name": row.author_name,
                "author_username": row.author_username,
                "reactions_count": row.reactions_count,
                "views_count": row.views_count,
                "forwards_count": row.forwards_count,
                "has_media": row.has_media,
                "media_type": row.media_type,
                "text_length": row.text_length,
            }
            for row in rows
        ]

    async def get_top_authors(
        self,
        source_id: uuid.UUID,
        export_job_id: uuid.UUID | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Aggregate message statistics by author.

        Parameters
        ----------
        source_id:
            The ``ExportSource.id`` to filter by.
        export_job_id:
            Optionally restrict to a single export job.
        limit:
            Maximum number of authors to return.

        Returns
        -------
        list[dict]
            Sorted by ``total_reactions`` descending. Each dict contains:
            ``author_telegram_id``, ``author_username``, ``author_name``,
            ``message_count``, ``total_reactions``, ``avg_reactions``,
            ``first_message_date``, ``last_message_date``.
        """
        filters = [MessageMeta.source_id == source_id]
        if export_job_id is not None:
            filters.append(MessageMeta.export_job_id == export_job_id)

        stmt = (
            select(
                MessageMeta.author_telegram_id,
                MessageMeta.author_username,
                MessageMeta.author_name,
                func.count(MessageMeta.id).label("message_count"),
                func.sum(MessageMeta.reactions_count).label("total_reactions"),
                func.avg(MessageMeta.reactions_count).label("avg_reactions"),
                func.min(MessageMeta.date).label("first_message_date"),
                func.max(MessageMeta.date).label("last_message_date"),
            )
            .where(*filters)
            .group_by(
                MessageMeta.author_telegram_id,
                MessageMeta.author_username,
                MessageMeta.author_name,
            )
            .order_by(func.sum(MessageMeta.reactions_count).desc())
            .limit(limit)
        )

        result = await self._db.execute(stmt)
        rows = result.all()

        return [
            {
                "author_telegram_id": row.author_telegram_id,
                "author_username": row.author_username,
                "author_name": row.author_name,
                "message_count": row.message_count,
                "total_reactions": int(row.total_reactions or 0),
                "avg_reactions": round(float(row.avg_reactions or 0), 2),
                "first_message_date": (
                    row.first_message_date.isoformat()
                    if row.first_message_date
                    else None
                ),
                "last_message_date": (
                    row.last_message_date.isoformat()
                    if row.last_message_date
                    else None
                ),
            }
            for row in rows
        ]

    async def get_activity_stats(
        self,
        source_id: uuid.UUID,
        export_job_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Compute per-day activity statistics.

        Parameters
        ----------
        source_id:
            The ``ExportSource.id`` to filter by.
        export_job_id:
            Optionally restrict to a single export job.

        Returns
        -------
        dict
            Keys: ``messages_per_day`` (list of ``{date, count}``),
            ``peak_days`` (top 5 busiest days), ``total_messages``,
            ``active_days``, ``avg_messages_per_day``.
        """
        filters = [MessageMeta.source_id == source_id]
        if export_job_id is not None:
            filters.append(MessageMeta.export_job_id == export_job_id)

        # Group by calendar date
        date_trunc = func.date_trunc("day", MessageMeta.date).label("day")
        stmt = (
            select(
                date_trunc,
                func.count(MessageMeta.id).label("count"),
            )
            .where(*filters)
            .group_by(date_trunc)
            .order_by(date_trunc)
        )

        result = await self._db.execute(stmt)
        daily_rows = result.all()

        messages_per_day = [
            {
                "date": row.day.isoformat() if row.day else None,
                "count": row.count,
            }
            for row in daily_rows
        ]

        total_messages = sum(row.count for row in daily_rows)
        active_days = len(daily_rows)
        avg_messages_per_day = (
            round(total_messages / active_days, 2) if active_days > 0 else 0.0
        )

        # Peak days: top 5 by message count
        sorted_days = sorted(
            messages_per_day,
            key=lambda d: d["count"],
            reverse=True,
        )
        peak_days = sorted_days[:5]

        return {
            "messages_per_day": messages_per_day,
            "peak_days": peak_days,
            "total_messages": total_messages,
            "active_days": active_days,
            "avg_messages_per_day": avg_messages_per_day,
        }

    async def get_export_summary(
        self,
        export_job_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Build a summary of a completed export job.

        Parameters
        ----------
        export_job_id:
            The ``ExportJob.id`` to summarize.

        Returns
        -------
        dict
            Keys: ``total_messages``, ``total_chunks``, ``unique_authors``,
            ``date_range`` (``{from, to}``), ``top_reactions``
            (top 10 posts by reactions).
        """
        filters = [MessageMeta.export_job_id == export_job_id]

        # Aggregate counts
        agg_stmt = select(
            func.count(MessageMeta.id).label("total_messages"),
            func.sum(MessageMeta.chunks_count).label("total_chunks"),
            func.count(
                distinct(MessageMeta.author_telegram_id),
            ).label("unique_authors"),
            func.min(MessageMeta.date).label("date_from"),
            func.max(MessageMeta.date).label("date_to"),
        ).where(*filters)

        agg_result = await self._db.execute(agg_stmt)
        agg = agg_result.one_or_none()

        if agg is None or agg.total_messages == 0:
            return {
                "total_messages": 0,
                "total_chunks": 0,
                "unique_authors": 0,
                "date_range": {"from": None, "to": None},
                "top_reactions": [],
            }

        # Top 10 posts by reactions
        top_stmt = (
            select(
                MessageMeta.telegram_message_id,
                MessageMeta.author_name,
                MessageMeta.reactions_count,
                MessageMeta.date,
            )
            .where(*filters)
            .order_by(MessageMeta.reactions_count.desc())
            .limit(10)
        )

        top_result = await self._db.execute(top_stmt)
        top_rows = top_result.all()

        return {
            "total_messages": agg.total_messages,
            "total_chunks": int(agg.total_chunks or 0),
            "unique_authors": agg.unique_authors,
            "date_range": {
                "from": (
                    agg.date_from.isoformat() if agg.date_from else None
                ),
                "to": agg.date_to.isoformat() if agg.date_to else None,
            },
            "top_reactions": [
                {
                    "telegram_message_id": row.telegram_message_id,
                    "author_name": row.author_name,
                    "reactions_count": row.reactions_count,
                    "date": row.date.isoformat() if row.date else None,
                }
                for row in top_rows
            ],
        }
