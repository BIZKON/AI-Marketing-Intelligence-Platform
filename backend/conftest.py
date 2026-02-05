"""Root conftest — shared fixtures for all tests."""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.main import app

TEST_BASE_URL = "http://test"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def client():
    """Unauthenticated async HTTP client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url=TEST_BASE_URL,
    ) as c:
        yield c


@pytest_asyncio.fixture
async def auth_headers():
    """JWT headers for a test user (no DB dependency)."""
    user_id = str(uuid.uuid4())
    token = create_access_token({"sub": user_id})
    return {"Authorization": f"Bearer {token}"}, user_id


@pytest_asyncio.fixture
async def admin_headers():
    """JWT headers for an admin user (no DB dependency)."""
    user_id = str(uuid.uuid4())
    token = create_access_token({"sub": user_id})
    return {"Authorization": f"Bearer {token}"}, user_id
