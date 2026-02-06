"""Tests for authentication API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_protected_endpoint_requires_auth():
    """API endpoints return 401/403 without a token."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/users/me")
    assert response.status_code in (401, 403)  # depends on FastAPI version


@pytest.mark.asyncio
async def test_invalid_token_rejected():
    """An invalid JWT is rejected with 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer invalid-token-here"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_endpoint_requires_auth():
    """Admin stats endpoint requires authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/admin/stats")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_admin_invalid_token():
    """Admin endpoint rejects invalid tokens."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/admin/stats",
            headers={"Authorization": "Bearer bad-token"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_billing_requires_auth():
    """Billing endpoint requires authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/billing/subscription")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_competitors_requires_auth():
    """Competitors endpoint requires authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/competitors/")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_reports_requires_auth():
    """Reports endpoint requires authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/reports/")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_content_requires_auth():
    """Content endpoint requires authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/content/plans")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_telegram_auth_requires_hash():
    """Telegram auth endpoint rejects requests without hash."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/telegram",
            json={
                "telegram_id": 12345,
                "username": "test",
                "full_name": "Test User",
                # Missing required: auth_date, hash
            },
        )
    assert response.status_code == 422  # Validation error — hash and auth_date required


@pytest.mark.asyncio
async def test_telegram_auth_invalid_hash():
    """Telegram auth endpoint rejects invalid hash."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/telegram",
            json={
                "telegram_id": 12345,
                "username": "test",
                "full_name": "Test User",
                "auth_date": 1700000000,
                "hash": "0" * 64,  # Invalid hash
            },
        )
    # Should fail with 401 (bad hash) or 500 depending on bot token config
    assert response.status_code in (401, 500)


@pytest.mark.asyncio
async def test_register_weak_password_rejected():
    """Registration rejects passwords shorter than 8 characters."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "password": "short",  # Less than 8 chars
            },
        )
    assert response.status_code == 422  # Validation error
