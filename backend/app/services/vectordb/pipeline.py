"""Embedding pipeline: parse → deduplicate → embed → store in Qdrant + DB.

Orchestrates the full content ingestion flow for competitor monitoring.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.competitor import Competitor
from app.models.competitor_post import CompetitorPost, Platform
from app.services.deduplication import compute_simhash, is_near_duplicate
from app.services.parsers import get_parser
from app.services.parsers.base import ParsedPost
from app.services.vectordb.embeddings import EmbeddingService
from app.services.vectordb.qdrant_client import QdrantService

logger = logging.getLogger(__name__)

PLATFORM_MAP = {
    "telegram": Platform.TELEGRAM,
    "youtube": Platform.YOUTUBE,
    "vk": Platform.VK,
    "website": Platform.WEBSITE,
    "instagram": Platform.INSTAGRAM,
}


class IngestionPipeline:
    """End-to-end pipeline: fetch → deduplicate → embed → store."""

    def __init__(
        self,
        db: AsyncSession,
        embedding_service: EmbeddingService | None = None,
        qdrant_service: QdrantService | None = None,
    ) -> None:
        self.db = db
        self.embeddings = embedding_service or EmbeddingService()
        self.qdrant = qdrant_service or QdrantService()

    async def process_competitor(
        self,
        competitor: Competitor,
        since: datetime | None = None,
    ) -> dict:
        """Collect and process all content for a single competitor.

        Returns:
            Stats dict with counts of fetched, new, duplicates, embedded.
        """
        stats = {
            "competitor_id": str(competitor.id),
            "competitor_name": competitor.name,
            "fetched": 0,
            "new": 0,
            "duplicates": 0,
            "embedded": 0,
            "errors": [],
        }

        for platform in competitor.platforms:
            platform_config = competitor.tracking_config.get(platform, {})
            if not platform_config:
                logger.debug("No tracking config for %s/%s", competitor.name, platform)
                continue

            try:
                parser = get_parser(platform)
                parsed_posts = await parser.fetch_posts(
                    tracking_config=platform_config,
                    since=since,
                    limit=100,
                )
                stats["fetched"] += len(parsed_posts)

                new_posts = await self._deduplicate_and_store(
                    parsed_posts, competitor, platform
                )
                stats["new"] += len(new_posts)
                stats["duplicates"] += len(parsed_posts) - len(new_posts)

                # Embed and index new posts
                if new_posts:
                    embedded_count = await self._embed_and_index(new_posts, competitor)
                    stats["embedded"] += embedded_count

            except Exception as e:
                msg = f"{platform}: {e}"
                logger.exception("Error processing %s for %s", platform, competitor.name)
                stats["errors"].append(msg)

        return stats

    async def _deduplicate_and_store(
        self,
        parsed_posts: list[ParsedPost],
        competitor: Competitor,
        platform: str,
    ) -> list[CompetitorPost]:
        """Deduplicate posts and store new ones in the database.

        Uses batch queries to avoid N+1 (#042):
        - Batch check all external_ids at once
        - Fetch recent simhashes once for the competitor
        """
        new_posts: list[CompetitorPost] = []
        if not parsed_posts:
            return new_posts

        # Batch-check existing external_ids to avoid N+1 queries (#042)
        all_ext_ids = [p.external_id for p in parsed_posts]
        existing_result = await self.db.execute(
            select(CompetitorPost.external_id).where(
                CompetitorPost.external_id.in_(all_ext_ids)
            )
        )
        existing_ext_ids = set(existing_result.scalars().all())

        # Pre-fetch recent simhashes for near-duplicate check (#042)
        recent_hashes_result = await self.db.execute(
            select(CompetitorPost.simhash).where(
                CompetitorPost.competitor_id == competitor.id,
                CompetitorPost.simhash.isnot(None),
            ).order_by(CompetitorPost.created_at.desc()).limit(500)
        )
        recent_hashes = [h for (h,) in recent_hashes_result if h]

        for parsed in parsed_posts:
            # Skip already-existing external_ids
            if parsed.external_id in existing_ext_ids:
                continue

            # Compute SimHash for content deduplication
            simhash = compute_simhash(parsed.full_text)

            # Check for near-duplicate content against pre-fetched hashes
            if simhash != "0" * 16:
                is_dup = any(
                    is_near_duplicate(simhash, existing_hash)
                    for existing_hash in recent_hashes
                )
                if is_dup:
                    logger.debug(
                        "Near-duplicate found for %s (simhash=%s)",
                        parsed.external_id, simhash,
                    )
                    continue

            # Create new post
            post = self._make_post(parsed, competitor, platform, simhash)
            self.db.add(post)
            new_posts.append(post)
            # Track this external_id and simhash for intra-batch dedup
            existing_ext_ids.add(parsed.external_id)
            if simhash != "0" * 16:
                recent_hashes.append(simhash)

        if new_posts:
            await self.db.flush()
            logger.info(
                "Stored %d new posts for %s/%s",
                len(new_posts), competitor.name, platform,
            )

        return new_posts

    async def _embed_and_index(
        self,
        posts: list[CompetitorPost],
        competitor: Competitor,
    ) -> int:
        """Generate embeddings and index in Qdrant."""
        texts = []
        for post in posts:
            parts = []
            if post.title:
                parts.append(post.title)
            if post.text_content:
                parts.append(post.text_content)
            texts.append("\n".join(parts) if parts else "")

        # Filter posts with actual text content
        indexable = [
            (post, text)
            for post, text in zip(posts, texts)
            if text.strip()
        ]
        if not indexable:
            return 0

        try:
            embeddings = await self.embeddings.embed_texts(
                [text for _, text in indexable]
            )

            qdrant_points = []
            for (post, text), embedding in zip(indexable, embeddings):
                point_id = str(uuid.uuid4())
                qdrant_points.append({
                    "id": point_id,
                    "vector": embedding,
                    "payload": {
                        "post_id": str(post.id),
                        "competitor_id": str(post.competitor_id),
                        "user_id": str(competitor.user_id),
                        "platform": post.platform.value if hasattr(post.platform, 'value') else str(post.platform),
                        "external_id": post.external_id,
                        "title": post.title or "",
                        "text_preview": (post.text_content or "")[:500],
                        "url": post.url or "",
                        "published_at": post.published_at.isoformat() if post.published_at else None,
                        "views": post.views,
                        "likes": post.likes,
                        "engagement_rate": post.engagement_rate,
                    },
                })

            point_ids = await self.qdrant.upsert_points(qdrant_points)

            if not point_ids:
                logger.warning("Qdrant upsert returned no point IDs")
                return 0

            # Update posts with qdrant point IDs
            for (post, _), pid in zip(indexable, point_ids):
                post.qdrant_point_id = pid

            # Flush Postgres; rollback Qdrant on failure (#041)
            try:
                await self.db.flush()
            except Exception:
                logger.exception("Postgres flush failed after Qdrant upsert, rolling back vectors")
                await self.qdrant.delete_points(point_ids)
                raise

            logger.info("Embedded and indexed %d posts in Qdrant", len(point_ids))
            return len(point_ids)

        except Exception:
            logger.exception("Failed to embed and index posts")
            return 0

    @staticmethod
    def _make_post(
        parsed: ParsedPost,
        competitor: Competitor,
        platform: str,
        simhash: str,
    ) -> CompetitorPost:
        """Convert a ParsedPost to a CompetitorPost DB model."""
        platform_enum = PLATFORM_MAP.get(platform, Platform.WEBSITE)

        # Calculate engagement rate
        engagement_rate = None
        total_engagement = parsed.likes + parsed.comments + parsed.shares
        if parsed.views > 0:
            engagement_rate = total_engagement / parsed.views

        return CompetitorPost(
            competitor_id=competitor.id,
            platform=platform_enum,
            external_id=parsed.external_id,
            title=parsed.title,
            text_content=parsed.text_content,
            url=parsed.url,
            media_urls=parsed.media_urls,
            views=parsed.views,
            likes=parsed.likes,
            comments=parsed.comments,
            shares=parsed.shares,
            engagement_rate=engagement_rate,
            published_at=parsed.published_at,
            raw_data=parsed.raw_data,
            simhash=simhash,
        )
