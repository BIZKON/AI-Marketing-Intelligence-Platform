"""Unit tests for the RAG ingestion pipeline (services/rag/ingestion.py)."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.rag.chunker import Chunk, ChunkingStrategy
from app.services.rag.ingestion import RAGIngestionPipeline, _clean_text


# ── _clean_text ──────────────────────────────────────────────────────────────


class TestCleanText:
    def test_empty_string(self):
        assert _clean_text("") == ""

    def test_none_returns_empty(self):
        assert _clean_text(None) == ""  # type: ignore[arg-type]

    def test_strips_html_tags(self):
        result = _clean_text("<b>bold</b> and <i>italic</i>")
        assert "<b>" not in result
        assert "<i>" not in result
        assert "bold" in result
        assert "italic" in result

    def test_unescapes_html_entities(self):
        # &lt; and &gt; get unescaped to < and > which are then stripped as HTML tags
        result = _clean_text("&amp; &quot;")
        assert "&" in result
        assert '"' in result

    def test_normalizes_unicode(self):
        # Combining characters should be normalized
        result = _clean_text("café")  # NFC form
        assert len(result) > 0

    def test_collapses_whitespace(self):
        result = _clean_text("too    many   spaces")
        assert "    " not in result
        assert "too" in result and "many" in result

    def test_collapses_newlines(self):
        result = _clean_text("one\n\n\n\n\ntwo")
        assert "\n\n\n" not in result
        assert "one" in result and "two" in result

    def test_strips_outer_whitespace(self):
        result = _clean_text("  hello world  ")
        assert result == "hello world"

    def test_complex_html(self):
        html = '<a href="http://example.com">Link</a> with <br/> tags'
        result = _clean_text(html)
        assert "Link" in result
        assert "tags" in result
        assert "<a" not in result


# ── _build_payload ───────────────────────────────────────────────────────────


class TestBuildPayload:
    def test_basic_payload_structure(self):
        chunk = Chunk(text="Hello", chunk_index=0, total_chunks=1)
        metadata = {
            "message_id": 123,
            "author_id": 456,
            "author_username": "alice",
            "author_name": "Alice",
            "date": datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc),
            "reactions_count": 10,
            "views_count": 500,
            "has_media": False,
            "media_type": "",
        }
        source_info = {
            "source_id": "src-1",
            "source_type": "channel",
            "source_name": "Test Channel",
            "user_id": "user-1",
        }
        export_id = "exp-1"

        payload = RAGIngestionPipeline._build_payload(chunk, metadata, source_info, export_id)

        assert payload["source_id"] == "src-1"
        assert payload["source_type"] == "channel"
        assert payload["user_id"] == "user-1"
        assert payload["message_id"] == "123"
        assert payload["author_id"] == "456"
        assert payload["author_username"] == "alice"
        assert payload["reactions_count"] == 10
        assert payload["views_count"] == 500
        assert payload["has_media"] is False
        assert payload["chunk_index"] == 0
        assert payload["total_chunks"] == 1
        assert payload["text"] == "Hello"
        assert payload["export_id"] == "exp-1"

    def test_datetime_converted_to_iso(self):
        chunk = Chunk(text="X", chunk_index=0, total_chunks=1)
        dt = datetime(2026, 6, 15, 10, 30, tzinfo=timezone.utc)
        payload = RAGIngestionPipeline._build_payload(
            chunk, {"date": dt}, {}, "exp"
        )
        assert payload["date"] == dt.isoformat()

    def test_string_date_passthrough(self):
        chunk = Chunk(text="X", chunk_index=0, total_chunks=1)
        payload = RAGIngestionPipeline._build_payload(
            chunk, {"date": "2026-01-01"}, {}, "exp"
        )
        assert payload["date"] == "2026-01-01"

    def test_none_date(self):
        chunk = Chunk(text="X", chunk_index=0, total_chunks=1)
        payload = RAGIngestionPipeline._build_payload(
            chunk, {"date": None}, {}, "exp"
        )
        assert payload["date"] is None

    def test_missing_fields_default(self):
        chunk = Chunk(text="X", chunk_index=0, total_chunks=1)
        payload = RAGIngestionPipeline._build_payload(chunk, {}, {}, "exp")
        assert payload["reactions_count"] == 0
        assert payload["views_count"] == 0
        assert payload["has_media"] is False
        assert payload["author_username"] == ""


# ── Ingestion pipeline methods (mocked dependencies) ────────────────────────


def _make_pipeline(
    embed_return=None,
    upsert_return=None,
    search_return=None,
):
    """Create a pipeline with mocked EmbeddingService, QdrantService, and db."""
    mock_embeddings = MagicMock()
    mock_embeddings.embed_texts = AsyncMock(
        return_value=embed_return or [[0.1] * 1536]
    )
    mock_embeddings.embed_single = AsyncMock(
        return_value=[0.1] * 1536,
    )

    mock_qdrant = MagicMock()
    mock_qdrant.upsert_points = AsyncMock(
        return_value=upsert_return or [str(uuid.uuid4())]
    )
    mock_qdrant.search = AsyncMock(
        return_value=search_return or [],
    )

    mock_db = MagicMock()

    with patch("app.services.rag.ingestion.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            qdrant_url="http://localhost:6333",
            qdrant_api_key="",
        )
        pipeline = RAGIngestionPipeline(
            embeddings=mock_embeddings,
            qdrant=mock_qdrant,
            db=mock_db,
        )

    return pipeline, mock_embeddings, mock_qdrant


class TestIngestMessage:
    @pytest.mark.asyncio
    async def test_empty_text_returns_empty(self):
        pipeline, _, _ = _make_pipeline()
        result = await pipeline.ingest_message("", {}, {}, "exp-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_html_only_text_returns_empty(self):
        pipeline, _, _ = _make_pipeline()
        result = await pipeline.ingest_message("<br/>  <hr>", {}, {}, "exp-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_successful_ingestion(self):
        point_id = str(uuid.uuid4())
        pipeline, mock_embed, mock_qdrant = _make_pipeline(
            embed_return=[[0.1] * 1536],
            upsert_return=[point_id],
        )

        result = await pipeline.ingest_message(
            text="Hello world",
            metadata={"message_id": 1, "date": "2026-01-01"},
            source_info={"user_id": "u1", "source_id": "s1"},
            export_id="exp-1",
        )

        assert result == [point_id]
        mock_embed.embed_texts.assert_called_once()
        mock_qdrant.upsert_points.assert_called_once()

    @pytest.mark.asyncio
    async def test_embedding_called_with_chunk_texts(self):
        pipeline, mock_embed, _ = _make_pipeline(
            embed_return=[[0.1] * 1536],
        )

        await pipeline.ingest_message(
            text="Short message",
            metadata={},
            source_info={},
            export_id="exp",
        )

        call_args = mock_embed.embed_texts.call_args[0][0]
        assert isinstance(call_args, list)
        assert len(call_args) >= 1
        assert "Short message" in call_args[0]

    @pytest.mark.asyncio
    async def test_payload_contains_export_id(self):
        pipeline, _, mock_qdrant = _make_pipeline(
            embed_return=[[0.1] * 1536],
            upsert_return=["pt-1"],
        )

        await pipeline.ingest_message(
            text="Content here",
            metadata={"message_id": 42},
            source_info={"user_id": "u1"},
            export_id="my-export",
        )

        points = mock_qdrant.upsert_points.call_args[0][0]
        assert points[0]["payload"]["export_id"] == "my-export"


class TestIngestBatch:
    @pytest.mark.asyncio
    async def test_empty_batch(self):
        pipeline, _, _ = _make_pipeline()
        result = await pipeline.ingest_batch([], {}, "exp")
        assert result == 0

    @pytest.mark.asyncio
    async def test_batch_with_messages(self):
        pipeline, mock_embed, mock_qdrant = _make_pipeline(
            embed_return=[[0.1] * 1536, [0.2] * 1536],
            upsert_return=["pt-1", "pt-2"],
        )

        messages = [
            {"text": "First message", "message_id": 1},
            {"text": "Second message", "message_id": 2},
        ]
        result = await pipeline.ingest_batch(
            messages,
            source_info={"user_id": "u1"},
            export_id="exp-1",
        )

        assert result >= 1
        mock_embed.embed_texts.assert_called_once()  # Single batch call

    @pytest.mark.asyncio
    async def test_empty_text_messages_skipped(self):
        pipeline, mock_embed, _ = _make_pipeline(
            embed_return=[[0.1] * 1536],
        )

        messages = [
            {"text": "", "message_id": 1},
            {"text": "Valid", "message_id": 2},
            {"text": "   ", "message_id": 3},
        ]
        await pipeline.ingest_batch(messages, {}, "exp")

        # Only "Valid" should be embedded
        call_texts = mock_embed.embed_texts.call_args[0][0]
        assert len(call_texts) == 1


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_always_filters_by_user_id(self):
        pipeline, mock_embed, mock_qdrant = _make_pipeline(search_return=[])

        await pipeline.search(query="test", user_id="user-123")

        mock_qdrant.search.assert_called_once()
        call_kwargs = mock_qdrant.search.call_args[1]
        filter_conds = call_kwargs["filter_conditions"]["must"]
        user_filter = [f for f in filter_conds if f["key"] == "user_id"]
        assert len(user_filter) == 1
        assert user_filter[0]["match"]["value"] == "user-123"

    @pytest.mark.asyncio
    async def test_search_with_source_filter(self):
        pipeline, _, mock_qdrant = _make_pipeline(search_return=[])

        await pipeline.search(
            query="test", user_id="u1", source_ids=["src-1", "src-2"]
        )

        filter_conds = mock_qdrant.search.call_args[1]["filter_conditions"]["must"]
        source_filter = [f for f in filter_conds if f["key"] == "source_id"]
        assert len(source_filter) == 1
        assert source_filter[0]["match"]["any"] == ["src-1", "src-2"]

    @pytest.mark.asyncio
    async def test_search_with_date_range(self):
        pipeline, _, mock_qdrant = _make_pipeline(search_return=[])
        dt_from = datetime(2026, 1, 1, tzinfo=timezone.utc)
        dt_to = datetime(2026, 6, 1, tzinfo=timezone.utc)

        await pipeline.search(
            query="test", user_id="u1",
            date_from=dt_from, date_to=dt_to,
        )

        filter_conds = mock_qdrant.search.call_args[1]["filter_conditions"]["must"]
        date_filters = [f for f in filter_conds if f["key"] == "date"]
        assert len(date_filters) == 2

    @pytest.mark.asyncio
    async def test_search_with_min_reactions(self):
        pipeline, _, mock_qdrant = _make_pipeline(search_return=[])

        await pipeline.search(query="test", user_id="u1", min_reactions=10)

        filter_conds = mock_qdrant.search.call_args[1]["filter_conditions"]["must"]
        reaction_filter = [f for f in filter_conds if f["key"] == "reactions_count"]
        assert len(reaction_filter) == 1
        assert reaction_filter[0]["range"]["gte"] == 10

    @pytest.mark.asyncio
    async def test_search_returns_formatted_results(self):
        pipeline, _, mock_qdrant = _make_pipeline(
            search_return=[
                {
                    "score": 0.95,
                    "payload": {
                        "text": "Found content",
                        "source_id": "s1",
                        "user_id": "u1",
                    },
                },
            ]
        )

        results = await pipeline.search(query="test", user_id="u1")

        assert len(results) == 1
        assert results[0]["score"] == 0.95
        assert results[0]["text"] == "Found content"
        assert "text" not in results[0]["metadata"]
        assert results[0]["metadata"]["source_id"] == "s1"

    @pytest.mark.asyncio
    async def test_search_no_min_reactions_filter_when_zero(self):
        pipeline, _, mock_qdrant = _make_pipeline(search_return=[])

        await pipeline.search(query="test", user_id="u1", min_reactions=0)

        filter_conds = mock_qdrant.search.call_args[1]["filter_conditions"]["must"]
        reaction_filter = [f for f in filter_conds if f["key"] == "reactions_count"]
        assert len(reaction_filter) == 0


class TestDeleteMethods:
    @pytest.mark.asyncio
    async def test_delete_by_export(self):
        pipeline, _, _ = _make_pipeline()

        with patch("app.services.rag.ingestion.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await pipeline.delete_by_export("exp-123")

            mock_client.post.assert_called_once()
            call_json = mock_client.post.call_args[1]["json"]
            assert call_json["filter"]["must"][0]["key"] == "export_id"
            assert call_json["filter"]["must"][0]["match"]["value"] == "exp-123"

    @pytest.mark.asyncio
    async def test_delete_by_source(self):
        pipeline, _, _ = _make_pipeline()

        with patch("app.services.rag.ingestion.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await pipeline.delete_by_source("user-1", "src-1")

            call_json = mock_client.post.call_args[1]["json"]
            filter_must = call_json["filter"]["must"]
            keys = [f["key"] for f in filter_must]
            assert "user_id" in keys
            assert "source_id" in keys
