"""Tests for training API endpoints — authentication and validation."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_scenarios_requires_auth():
    """GET /training/scenarios requires authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/training/scenarios")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_scenarios_invalid_token():
    """GET /training/scenarios rejects invalid token."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/training/scenarios",
            headers={"Authorization": "Bearer bad-token"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_sessions_requires_auth():
    """GET /training/sessions requires authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/training/sessions")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_session_requires_auth():
    """POST /training/sessions requires authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/training/sessions",
            json={"scenario_id": "00000000-0000-0000-0000-000000000000", "mode": "text"},
        )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_analytics_requires_auth():
    """GET /training/analytics requires authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/training/analytics")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_achievements_requires_auth():
    """GET /training/achievements requires authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/training/achievements")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_send_message_requires_auth():
    """POST /training/sessions/{id}/message requires authentication."""
    session_id = "00000000-0000-0000-0000-000000000000"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/training/sessions/{session_id}/message",
            json={"message": "Здравствуйте!"},
        )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_complete_session_requires_auth():
    """POST /training/sessions/{id}/complete requires authentication."""
    session_id = "00000000-0000-0000-0000-000000000000"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/training/sessions/{session_id}/complete",
        )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_voice_requires_auth():
    """GET /voice/voices requires authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/voice/voices")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_gamification_requires_auth():
    """GET /gamification/profile requires authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/gamification/profile")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_multiplayer_requires_auth():
    """POST /multiplayer/create requires authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/multiplayer/create",
            json={"scenario_id": "00000000-0000-0000-0000-000000000000"},
        )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_ab_tests_requires_auth():
    """GET /ab-tests/ requires authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/ab-tests/")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_export_requires_auth():
    """GET /export/sessions requires authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/export/sessions")
    assert response.status_code in (401, 403)
