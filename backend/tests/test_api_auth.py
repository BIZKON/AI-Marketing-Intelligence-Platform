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
