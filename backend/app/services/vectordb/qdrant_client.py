"""Qdrant vector database service for storing and searching competitor content embeddings."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Sequence

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()
QDRANT_URL = _settings.qdrant_url
QDRANT_API_KEY = _settings.qdrant_api_key
COLLECTION_NAME = "competitor_posts"
EMBEDDING_DIM = 1536


class QdrantService:
    """Manage vector storage in Qdrant for competitor content."""

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        collection: str = COLLECTION_NAME,
    ) -> None:
        self.url = (url or QDRANT_URL).rstrip("/")
        self.api_key = api_key or QDRANT_API_KEY
        self.collection = collection
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            self._headers["api-key"] = self.api_key

    # ── Collection Management ────────────────────────────────────────────────

    async def ensure_collection(self) -> None:
        """Create the collection if it doesn't exist."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.url}/collections/{self.collection}",
                    headers=self._headers,
                )
                if resp.status_code == 200:
                    logger.debug("Qdrant collection '%s' already exists", self.collection)
                    return

                # Create collection
                resp = await client.put(
                    f"{self.url}/collections/{self.collection}",
                    headers=self._headers,
                    json={
                        "vectors": {
                            "size": EMBEDDING_DIM,
                            "distance": "Cosine",
                        },
                    },
                )
                resp.raise_for_status()
                logger.info("Created Qdrant collection '%s'", self.collection)

                # Create payload indexes for filtering
                for field_name, field_type in [
                    ("competitor_id", "keyword"),
                    ("platform", "keyword"),
                    ("user_id", "keyword"),
                    ("published_at", "datetime"),
                ]:
                    await client.put(
                        f"{self.url}/collections/{self.collection}/index",
                        headers=self._headers,
                        json={
                            "field_name": field_name,
                            "field_schema": field_type,
                        },
                    )
                logger.info("Created payload indexes for '%s'", self.collection)

        except Exception:
            logger.exception("Failed to ensure Qdrant collection")

    # ── Upsert ───────────────────────────────────────────────────────────────

    async def upsert_points(
        self,
        points: list[dict[str, Any]],
    ) -> list[str]:
        """Upsert embedding points into Qdrant.

        Each point dict should have:
            - vector: list[float]
            - payload: dict with metadata (competitor_id, platform, text, etc.)
            - id (optional): str UUID, auto-generated if missing

        Returns:
            List of point IDs that were upserted.
        """
        if not points:
            return []

        qdrant_points = []
        point_ids = []
        for pt in points:
            pid = pt.get("id") or str(uuid.uuid4())
            point_ids.append(pid)
            qdrant_points.append({
                "id": pid,
                "vector": pt["vector"],
                "payload": pt.get("payload", {}),
            })

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.put(
                    f"{self.url}/collections/{self.collection}/points",
                    headers=self._headers,
                    json={"points": qdrant_points},
                )
                resp.raise_for_status()
            logger.info("Upserted %d points to Qdrant", len(qdrant_points))
        except Exception:
            logger.exception("Failed to upsert points to Qdrant")
            return []

        return point_ids

    # ── Search ───────────────────────────────────────────────────────────────

    async def search(
        self,
        vector: list[float],
        limit: int = 10,
        filter_conditions: dict | None = None,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search for similar content.

        Args:
            vector: Query embedding vector.
            limit: Max results to return.
            filter_conditions: Qdrant filter dict for payload filtering.
            score_threshold: Minimum similarity score.

        Returns:
            List of results with id, score, payload.
        """
        body: dict[str, Any] = {
            "vector": vector,
            "limit": limit,
            "with_payload": True,
        }
        if filter_conditions:
            body["filter"] = filter_conditions
        if score_threshold is not None:
            body["score_threshold"] = score_threshold

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{self.url}/collections/{self.collection}/points/search",
                    headers=self._headers,
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for hit in data.get("result", []):
                results.append({
                    "id": hit["id"],
                    "score": hit["score"],
                    "payload": hit.get("payload", {}),
                })
            return results

        except Exception:
            logger.exception("Qdrant search failed")
            return []

    async def search_by_competitor(
        self,
        vector: list[float],
        competitor_ids: list[str],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search within specific competitors' content."""
        filter_conditions = {
            "must": [
                {
                    "key": "competitor_id",
                    "match": {"any": competitor_ids},
                }
            ]
        }
        return await self.search(vector, limit=limit, filter_conditions=filter_conditions)

    async def search_by_user(
        self,
        vector: list[float],
        user_id: str,
        limit: int = 10,
        platform: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search within a user's tracked competitors."""
        must_conditions: list[dict] = [
            {"key": "user_id", "match": {"value": user_id}},
        ]
        if platform:
            must_conditions.append(
                {"key": "platform", "match": {"value": platform}},
            )
        return await self.search(
            vector, limit=limit, filter_conditions={"must": must_conditions}
        )

    # ── Delete ───────────────────────────────────────────────────────────────

    async def delete_by_competitor(self, competitor_id: str) -> None:
        """Delete all points for a given competitor."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{self.url}/collections/{self.collection}/points/delete",
                    headers=self._headers,
                    json={
                        "filter": {
                            "must": [
                                {"key": "competitor_id", "match": {"value": competitor_id}},
                            ]
                        }
                    },
                )
                resp.raise_for_status()
            logger.info("Deleted Qdrant points for competitor %s", competitor_id)
        except Exception:
            logger.exception("Failed to delete Qdrant points for competitor %s", competitor_id)

    async def delete_points(self, point_ids: Sequence[str]) -> None:
        """Delete specific points by ID."""
        if not point_ids:
            return
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{self.url}/collections/{self.collection}/points/delete",
                    headers=self._headers,
                    json={"points": list(point_ids)},
                )
                resp.raise_for_status()
        except Exception:
            logger.exception("Failed to delete Qdrant points")

    # ── Stats ────────────────────────────────────────────────────────────────

    async def collection_info(self) -> dict[str, Any]:
        """Get collection statistics."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.url}/collections/{self.collection}",
                    headers=self._headers,
                )
                resp.raise_for_status()
                return resp.json().get("result", {})
        except Exception:
            logger.exception("Failed to get Qdrant collection info")
            return {}
