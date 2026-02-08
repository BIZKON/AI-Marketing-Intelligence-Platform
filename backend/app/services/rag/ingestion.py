"""RAG ingestion pipeline for Telegram messages.

Handles text cleaning, chunking, embedding, and storage in Qdrant for
semantic search over user-exported Telegram channels, groups, and chats.
"""

from __future__ import annotations

import html
import logging
import re
import unicodedata
import uuid
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.rag.chunker import Chunk, ChunkingStrategy
from app.services.vectordb.embeddings import EMBEDDING_DIM, EmbeddingService
from app.services.vectordb.qdrant_client import QdrantService

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGES_COLLECTION = "telegram_messages"

# ── Payload index definitions ────────────────────────────────────────────────
# (field_name, qdrant_field_schema)
_PAYLOAD_INDEXES: list[tuple[str, str]] = [
    ("user_id", "keyword"),
    ("source_id", "keyword"),
    ("source_type", "keyword"),
    ("author_id", "keyword"),
    ("export_id", "keyword"),
    ("date", "datetime"),
    ("reactions_count", "integer"),
    ("views_count", "integer"),
]

# Regex for stripping HTML tags
_HTML_TAG_RE = re.compile(r"<[^>]+>")
# Regex for collapsing excessive whitespace
_MULTI_SPACE_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def _clean_text(raw: str) -> str:
    """Strip HTML, normalize unicode, and collapse whitespace."""
    if not raw:
        return ""
    # Unescape HTML entities first, then remove tags
    text = html.unescape(raw)
    text = _HTML_TAG_RE.sub(" ", text)
    # Normalize unicode (NFC form, compatible composition)
    text = unicodedata.normalize("NFC", text)
    # Collapse whitespace
    text = _MULTI_SPACE_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


class RAGIngestionPipeline:
    """Full RAG pipeline: clean -> chunk -> embed -> store in Qdrant.

    Uses a dedicated ``telegram_messages`` Qdrant collection, separate from
    the competitor-monitoring collection.
    """

    def __init__(
        self,
        embeddings: EmbeddingService,
        qdrant: QdrantService,
        db: AsyncSession,
        chunker: ChunkingStrategy | None = None,
    ) -> None:
        self.embeddings = embeddings
        self.qdrant = qdrant
        self.db = db
        self.chunker = chunker or ChunkingStrategy()

        # Internal reference to Qdrant HTTP config for direct REST calls that
        # go beyond the generic QdrantService helpers (scroll, filtered delete).
        _settings = get_settings()
        self._qdrant_url = (_settings.qdrant_url).rstrip("/")
        self._qdrant_headers: dict[str, str] = {"Content-Type": "application/json"}
        if _settings.qdrant_api_key:
            self._qdrant_headers["api-key"] = _settings.qdrant_api_key

    # ── Collection management ────────────────────────────────────────────

    async def ensure_collection(self) -> None:
        """Create the ``telegram_messages`` collection and payload indexes.

        Idempotent: skips creation if the collection already exists.
        """
        collection = TELEGRAM_MESSAGES_COLLECTION
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self._qdrant_url}/collections/{collection}",
                    headers=self._qdrant_headers,
                )
                if resp.status_code == 200:
                    logger.debug(
                        "Qdrant collection '%s' already exists", collection
                    )
                    return

                # Create collection with cosine distance
                resp = await client.put(
                    f"{self._qdrant_url}/collections/{collection}",
                    headers=self._qdrant_headers,
                    json={
                        "vectors": {
                            "size": EMBEDDING_DIM,
                            "distance": "Cosine",
                        },
                    },
                )
                resp.raise_for_status()
                logger.info("Created Qdrant collection '%s'", collection)

                # Create payload indexes for efficient filtering
                for field_name, field_type in _PAYLOAD_INDEXES:
                    await client.put(
                        f"{self._qdrant_url}/collections/{collection}/index",
                        headers=self._qdrant_headers,
                        json={
                            "field_name": field_name,
                            "field_schema": field_type,
                        },
                    )
                logger.info(
                    "Created %d payload indexes for '%s'",
                    len(_PAYLOAD_INDEXES),
                    collection,
                )

        except Exception:
            logger.exception("Failed to ensure Qdrant collection '%s'", collection)

    # ── Single message ingestion ─────────────────────────────────────────

    async def ingest_message(
        self,
        text: str,
        metadata: dict[str, Any],
        source_info: dict[str, Any],
        export_id: str,
    ) -> list[str]:
        """Ingest a single Telegram message into the RAG store.

        Steps:
            1. Clean text (strip HTML, normalize unicode).
            2. Chunk using :class:`ChunkingStrategy`.
            3. Embed chunks via :class:`EmbeddingService`.
            4. Build Qdrant points with rich payloads.
            5. Upsert to Qdrant.

        Args:
            text: Raw message text (may contain HTML).
            metadata: Per-message metadata (message_id, author_id,
                author_username, author_name, date, reactions_count,
                views_count, has_media, media_type, is_transcription).
            source_info: Source-level metadata (source_id, source_type,
                source_name, user_id).
            export_id: ID of the export job that produced this message.

        Returns:
            List of Qdrant point IDs created for the message's chunks.
        """
        cleaned = _clean_text(text)
        if not cleaned:
            return []

        message_type = source_info.get("source_type", "post")
        chunks = self.chunker.chunk_message(cleaned, message_type=message_type)
        if not chunks:
            return []

        # Embed all chunk texts in one batch
        chunk_texts = [c.text for c in chunks]
        embeddings = await self.embeddings.embed_texts(chunk_texts)

        # Build Qdrant points
        points: list[dict[str, Any]] = []
        for chunk, vector in zip(chunks, embeddings):
            point_id = str(uuid.uuid4())
            payload = self._build_payload(
                chunk=chunk,
                metadata=metadata,
                source_info=source_info,
                export_id=export_id,
            )
            points.append({
                "id": point_id,
                "vector": vector,
                "payload": payload,
            })

        point_ids = await self.qdrant.upsert_points(points)
        if point_ids:
            logger.debug(
                "Ingested message %s -> %d chunks",
                metadata.get("message_id", "?"),
                len(point_ids),
            )
        return point_ids

    # ── Batch ingestion ──────────────────────────────────────────────────

    async def ingest_batch(
        self,
        messages: list[dict[str, Any]],
        source_info: dict[str, Any],
        export_id: str,
    ) -> int:
        """Ingest a batch of messages, returning total chunks created.

        Each message dict should have at least ``text`` and metadata fields
        matching :meth:`ingest_message` expectations.

        Args:
            messages: List of message dicts with ``text`` and metadata keys.
            source_info: Source-level metadata shared by all messages.
            export_id: ID of the export job.

        Returns:
            Total number of chunks created across all messages.
        """
        if not messages:
            return 0

        # Collect all cleaned texts and their associated metadata
        cleaned_items: list[tuple[str, dict[str, Any], list[Chunk]]] = []
        for msg in messages:
            raw_text = msg.get("text", "")
            cleaned = _clean_text(raw_text)
            if not cleaned:
                continue
            message_type = source_info.get("source_type", "post")
            chunks = self.chunker.chunk_message(cleaned, message_type=message_type)
            if chunks:
                cleaned_items.append((raw_text, msg, chunks))

        if not cleaned_items:
            return 0

        # Flatten all chunk texts for a single embedding batch call
        all_chunk_texts: list[str] = []
        chunk_map: list[tuple[int, int]] = []  # (item_index, chunk_index_in_item)
        for item_idx, (_, _, chunks) in enumerate(cleaned_items):
            for chunk_idx, chunk in enumerate(chunks):
                all_chunk_texts.append(chunk.text)
                chunk_map.append((item_idx, chunk_idx))

        # Embed everything at once for efficiency
        all_embeddings = await self.embeddings.embed_texts(all_chunk_texts)

        # Build all Qdrant points
        all_points: list[dict[str, Any]] = []
        for flat_idx, (item_idx, chunk_idx) in enumerate(chunk_map):
            _, msg, chunks = cleaned_items[item_idx]
            chunk = chunks[chunk_idx]
            vector = all_embeddings[flat_idx]

            point_id = str(uuid.uuid4())
            payload = self._build_payload(
                chunk=chunk,
                metadata=msg,
                source_info=source_info,
                export_id=export_id,
            )
            all_points.append({
                "id": point_id,
                "vector": vector,
                "payload": payload,
            })

        # Upsert in sub-batches to avoid oversized requests
        total_created = 0
        batch_size = 100
        for i in range(0, len(all_points), batch_size):
            batch = all_points[i : i + batch_size]
            ids = await self.qdrant.upsert_points(batch)
            total_created += len(ids)

        logger.info(
            "Batch ingested %d messages -> %d chunks (export=%s)",
            len(messages),
            total_created,
            export_id,
        )
        return total_created

    # ── Search ───────────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        user_id: str,
        source_ids: list[str] | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        min_reactions: int = 0,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Semantic search over ingested Telegram messages.

        Always filters by ``user_id`` for data isolation.

        Args:
            query: Natural-language search query.
            user_id: Owner user ID (mandatory filter).
            source_ids: Optional list of source IDs to restrict search.
            date_from: Optional earliest date filter.
            date_to: Optional latest date filter.
            min_reactions: Minimum reactions_count filter.
            limit: Maximum number of results.

        Returns:
            List of dicts with ``score``, ``text``, and ``metadata`` keys.
        """
        query_vector = await self.embeddings.embed_single(query)

        # Build Qdrant filter — always include user_id
        must_conditions: list[dict[str, Any]] = [
            {"key": "user_id", "match": {"value": user_id}},
        ]

        if source_ids:
            must_conditions.append(
                {"key": "source_id", "match": {"any": source_ids}},
            )

        if date_from is not None:
            must_conditions.append(
                {"key": "date", "range": {"gte": date_from.isoformat()}},
            )

        if date_to is not None:
            must_conditions.append(
                {"key": "date", "range": {"lte": date_to.isoformat()}},
            )

        if min_reactions > 0:
            must_conditions.append(
                {"key": "reactions_count", "range": {"gte": min_reactions}},
            )

        filter_conditions = {"must": must_conditions}

        results = await self.qdrant.search(
            vector=query_vector,
            limit=limit,
            filter_conditions=filter_conditions,
        )

        return [
            {
                "score": r["score"],
                "text": r["payload"].get("text", ""),
                "metadata": {
                    k: v
                    for k, v in r["payload"].items()
                    if k != "text"
                },
            }
            for r in results
        ]

    # ── Popular posts ────────────────────────────────────────────────────

    async def get_popular_posts(
        self,
        user_id: str,
        source_id: str,
        min_reactions: int = 5,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve popular posts by reaction count using Qdrant scroll.

        Args:
            user_id: Owner user ID (mandatory filter).
            source_id: Source (channel/group) to query.
            min_reactions: Minimum reactions_count threshold.
            limit: Maximum number of results.

        Returns:
            List of dicts with ``text`` and ``metadata`` keys, sorted by
            reactions_count descending.
        """
        collection = TELEGRAM_MESSAGES_COLLECTION
        scroll_filter = {
            "must": [
                {"key": "user_id", "match": {"value": user_id}},
                {"key": "source_id", "match": {"value": source_id}},
                {"key": "reactions_count", "range": {"gte": min_reactions}},
                # Only return the first chunk of each message to avoid dupes
                {"key": "chunk_index", "match": {"value": 0}},
            ]
        }

        all_points: list[dict[str, Any]] = []
        offset: str | None = None

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                while True:
                    body: dict[str, Any] = {
                        "filter": scroll_filter,
                        "limit": min(limit, 100),
                        "with_payload": True,
                        "with_vector": False,
                    }
                    if offset is not None:
                        body["offset"] = offset

                    resp = await client.post(
                        f"{self._qdrant_url}/collections/{collection}/points/scroll",
                        headers=self._qdrant_headers,
                        json=body,
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    points = data.get("result", {}).get("points", [])
                    for pt in points:
                        payload = pt.get("payload", {})
                        all_points.append({
                            "text": payload.get("text", ""),
                            "metadata": {
                                k: v for k, v in payload.items() if k != "text"
                            },
                        })

                    next_offset = data.get("result", {}).get("next_page_offset")
                    if not next_offset or len(all_points) >= limit:
                        break
                    offset = next_offset

        except Exception:
            logger.exception(
                "Failed to scroll popular posts for source %s", source_id
            )
            return []

        # Sort by reactions_count descending and trim to limit
        all_points.sort(
            key=lambda p: p["metadata"].get("reactions_count", 0),
            reverse=True,
        )
        return all_points[:limit]

    # ── Deletion ─────────────────────────────────────────────────────────

    async def delete_by_export(self, export_id: str) -> None:
        """Delete all Qdrant points belonging to an export job."""
        collection = TELEGRAM_MESSAGES_COLLECTION
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self._qdrant_url}/collections/{collection}/points/delete",
                    headers=self._qdrant_headers,
                    json={
                        "filter": {
                            "must": [
                                {"key": "export_id", "match": {"value": export_id}},
                            ]
                        }
                    },
                )
                resp.raise_for_status()
            logger.info("Deleted Qdrant points for export %s", export_id)
        except Exception:
            logger.exception(
                "Failed to delete Qdrant points for export %s", export_id
            )

    async def delete_by_source(self, user_id: str, source_id: str) -> None:
        """Delete all Qdrant points for a given source owned by a user."""
        collection = TELEGRAM_MESSAGES_COLLECTION
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self._qdrant_url}/collections/{collection}/points/delete",
                    headers=self._qdrant_headers,
                    json={
                        "filter": {
                            "must": [
                                {"key": "user_id", "match": {"value": user_id}},
                                {"key": "source_id", "match": {"value": source_id}},
                            ]
                        }
                    },
                )
                resp.raise_for_status()
            logger.info(
                "Deleted Qdrant points for source %s (user=%s)",
                source_id,
                user_id,
            )
        except Exception:
            logger.exception(
                "Failed to delete Qdrant points for source %s (user=%s)",
                source_id,
                user_id,
            )

    # ── Internal helpers ─────────────────────────────────────────────────

    @staticmethod
    def _build_payload(
        chunk: Chunk,
        metadata: dict[str, Any],
        source_info: dict[str, Any],
        export_id: str,
    ) -> dict[str, Any]:
        """Assemble the Qdrant point payload from chunk + metadata."""
        # Normalise the date to ISO string if it's a datetime object
        raw_date = metadata.get("date")
        if isinstance(raw_date, datetime):
            date_str = raw_date.isoformat()
        else:
            date_str = str(raw_date) if raw_date else None

        return {
            # Source-level fields
            "source_id": source_info.get("source_id", ""),
            "source_type": source_info.get("source_type", ""),
            "source_name": source_info.get("source_name", ""),
            "user_id": source_info.get("user_id", ""),
            # Message-level fields
            "message_id": str(metadata.get("message_id", "")),
            "author_id": str(metadata.get("author_id", "")),
            "author_username": metadata.get("author_username", ""),
            "author_name": metadata.get("author_name", ""),
            "date": date_str,
            "reactions_count": int(metadata.get("reactions_count", 0)),
            "views_count": int(metadata.get("views_count", 0)),
            "has_media": bool(metadata.get("has_media", False)),
            "media_type": metadata.get("media_type", ""),
            "is_transcription": bool(metadata.get("is_transcription", False)),
            # Chunk-level fields
            "chunk_index": chunk.chunk_index,
            "total_chunks": chunk.total_chunks,
            "text": chunk.text,
            # Job-level fields
            "export_id": export_id,
        }
