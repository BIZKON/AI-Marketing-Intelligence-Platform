"""Integration tests for Telegram Export API endpoints (/api/v1/tg-export/).

Tests cover:
  - Schema validation (422 for invalid payloads)
  - Auth required (401/403 for missing tokens)
  - Functional behaviour with mocked DB/auth dependencies
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.dependencies import get_active_subscription, get_current_user
from app.main import app
from app.models.subscription import PlanType

TEST_BASE_URL = "http://test"


# ── Mock factories ────────────────────────────────────────────────────────────


def _make_mock_user(user_id: str) -> MagicMock:
    user = MagicMock()
    user.id = uuid.UUID(user_id)
    user.is_active = True
    return user


def _make_mock_subscription(plan: str = "creator") -> MagicMock:
    sub = MagicMock()
    sub.plan = getattr(PlanType, plan.upper(), PlanType.CREATOR)
    return sub


def _make_mock_db() -> AsyncMock:
    """Create a mock AsyncSession that returns empty results by default."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_scalars.first.return_value = None
    mock_result.scalars.return_value = mock_scalars
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalar.return_value = 0
    mock_result.all.return_value = []
    mock_result.fetchone.return_value = None
    db.execute = AsyncMock(return_value=mock_result)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()
    db.commit = AsyncMock()
    return db


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def user_id():
    return str(uuid.uuid4())


@pytest.fixture
def mock_user(user_id):
    return _make_mock_user(user_id)


@pytest.fixture
def mock_sub():
    return _make_mock_subscription()


@pytest.fixture
def mock_db():
    return _make_mock_db()


@pytest.fixture
def override_deps(mock_user, mock_sub, mock_db):
    """Override FastAPI dependencies to bypass real DB and auth."""
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_active_subscription] = lambda: mock_sub
    app.dependency_overrides[get_db] = lambda: mock_db
    yield {"user": mock_user, "sub": mock_sub, "db": mock_db}
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url=TEST_BASE_URL)


# ── Schema validation (422) ──────────────────────────────────────────────────


class TestSchemaValidation:
    """Endpoints reject invalid request bodies with 422."""

    @pytest.mark.asyncio
    async def test_connect_rejects_empty_body(self, override_deps, client):
        async with client:
            resp = await client.post("/api/v1/tg-export/connect", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_connect_rejects_missing_phone(self, override_deps, client):
        async with client:
            resp = await client.post(
                "/api/v1/tg-export/connect",
                json={"api_id": 12345, "api_hash": "abc123"},
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_verify_rejects_empty_body(self, override_deps, client):
        async with client:
            resp = await client.post("/api/v1/tg-export/verify", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_search_rejects_empty_body(self, override_deps, client):
        async with client:
            resp = await client.post("/api/v1/tg-export/search", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_search_rejects_limit_over_50(self, override_deps, client):
        async with client:
            resp = await client.post(
                "/api/v1/tg-export/search",
                json={"query": "test", "limit": 100},
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_job_create_rejects_empty_body(self, override_deps, client):
        async with client:
            resp = await client.post("/api/v1/tg-export/jobs", json={})
        assert resp.status_code == 422


# ── Auth required (401/403) ──────────────────────────────────────────────────


class TestAuthRequired:
    """All endpoints reject unauthenticated requests (no Bearer token)."""

    ENDPOINTS = [
        ("POST", "/api/v1/tg-export/connect"),
        ("POST", "/api/v1/tg-export/verify"),
        ("GET", "/api/v1/tg-export/sources"),
        ("POST", "/api/v1/tg-export/sources"),
        ("POST", "/api/v1/tg-export/jobs"),
        ("GET", "/api/v1/tg-export/jobs"),
        ("POST", "/api/v1/tg-export/search"),
        ("GET", "/api/v1/tg-export/analytics/popular"),
        ("GET", "/api/v1/tg-export/analytics/authors"),
        ("GET", "/api/v1/tg-export/analytics/activity"),
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method,url", ENDPOINTS)
    async def test_unauthenticated_returns_401_or_403(self, method, url, client):
        async with client:
            if method == "GET":
                resp = await client.get(url)
            else:
                resp = await client.post(url, json={})
        assert resp.status_code in (401, 403)


# ── GET list endpoints (empty DB) ────────────────────────────────────────────


class TestListSources:
    """GET /sources — returns user's export sources."""

    @pytest.mark.asyncio
    async def test_returns_empty_list(self, override_deps, client):
        async with client:
            resp = await client.get("/api/v1/tg-export/sources")
        assert resp.status_code == 200
        assert resp.json() == []


class TestListJobs:
    """GET /jobs — returns user's export jobs."""

    @pytest.mark.asyncio
    async def test_returns_empty_list(self, override_deps, client):
        async with client:
            resp = await client.get("/api/v1/tg-export/jobs")
        assert resp.status_code == 200
        assert resp.json() == []


# ── POST /search ─────────────────────────────────────────────────────────────


class TestSearchEndpoint:
    """POST /search — semantic search over exported data."""

    @pytest.mark.asyncio
    async def test_no_sources_returns_empty(self, override_deps, client):
        """When user has no sources, search returns empty results immediately."""
        async with client:
            resp = await client.post(
                "/api/v1/tg-export/search",
                json={"query": "test topic"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "test topic"
        assert data["results"] == []
        assert data["total"] == 0


# ── GET /analytics/* ─────────────────────────────────────────────────────────


class TestAnalyticsPopular:
    """GET /analytics/popular — popular messages by reactions."""

    @pytest.mark.asyncio
    async def test_returns_empty_posts(self, override_deps, client):
        async with client:
            resp = await client.get("/api/v1/tg-export/analytics/popular")
        assert resp.status_code == 200
        assert resp.json() == {"posts": []}


class TestAnalyticsAuthors:
    """GET /analytics/authors — top authors."""

    @pytest.mark.asyncio
    async def test_returns_empty_authors(self, override_deps, client):
        async with client:
            resp = await client.get("/api/v1/tg-export/analytics/authors")
        assert resp.status_code == 200
        assert resp.json() == {"authors": []}


class TestAnalyticsActivity:
    """GET /analytics/activity — activity distribution."""

    @pytest.mark.asyncio
    async def test_returns_zero_activity(self, override_deps, client):
        async with client:
            resp = await client.get("/api/v1/tg-export/analytics/activity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_messages"] == 0
        assert data["total_sources"] == 0
        assert data["by_hour"] == {}
        assert data["by_weekday"] == {}
        assert data["recent_daily"] == []


# ── POST /connect ────────────────────────────────────────────────────────────


class TestConnectEndpoint:
    """POST /connect — Telethon session initialization."""

    @pytest.mark.asyncio
    async def test_route_responds(self, override_deps, client):
        """Route exists; may return 400/500 (missing encryption key / Telethon)."""
        async with client:
            resp = await client.post(
                "/api/v1/tg-export/connect",
                json={"api_id": 12345, "api_hash": "abc", "phone": "+79991234567"},
            )
        assert resp.status_code != 404


# ── POST /verify ─────────────────────────────────────────────────────────────


class TestVerifyEndpoint:
    """POST /verify — session verification."""

    @pytest.mark.asyncio
    async def test_nonexistent_session_returns_404(self, override_deps, client):
        async with client:
            resp = await client.post(
                "/api/v1/tg-export/verify",
                json={"session_id": str(uuid.uuid4()), "code": "12345"},
            )
        assert resp.status_code == 404


# ── Sources CRUD ─────────────────────────────────────────────────────────────


class TestSourceCRUD:
    """POST/DELETE /sources — source management."""

    @pytest.mark.asyncio
    async def test_add_source_needs_telegram_session(self, override_deps, client):
        """Adding a source fails with 400 when no active Telegram session exists."""
        async with client:
            resp = await client.post(
                "/api/v1/tg-export/sources",
                json={"telegram_id_or_username": "test_channel"},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_nonexistent_source_returns_404(self, override_deps, client):
        fake_id = str(uuid.uuid4())
        async with client:
            resp = await client.delete(f"/api/v1/tg-export/sources/{fake_id}")
        assert resp.status_code == 404


# ── Jobs management ──────────────────────────────────────────────────────────


class TestJobManagement:
    """POST /jobs, GET /jobs/{id}, POST /jobs/{id}/cancel."""

    @pytest.mark.asyncio
    async def test_create_job_source_not_found(self, override_deps, client):
        """Creating a job with nonexistent source returns 404."""
        async with client:
            resp = await client.post(
                "/api/v1/tg-export/jobs",
                json={"source_id": str(uuid.uuid4())},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_nonexistent_job_returns_404(self, override_deps, client):
        fake_id = str(uuid.uuid4())
        async with client:
            resp = await client.get(f"/api/v1/tg-export/jobs/{fake_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_job_returns_404(self, override_deps, client):
        fake_id = str(uuid.uuid4())
        async with client:
            resp = await client.post(f"/api/v1/tg-export/jobs/{fake_id}/cancel")
        assert resp.status_code == 404


# ── GET /folders ─────────────────────────────────────────────────────────────


class TestFoldersEndpoint:
    """GET /folders — Telegram dialog folders."""

    @pytest.mark.asyncio
    async def test_no_session_returns_400(self, override_deps, client):
        """Without an active Telegram session, /folders returns 400."""
        async with client:
            resp = await client.get("/api/v1/tg-export/folders")
        assert resp.status_code == 400
