"""System health checks — DB, Redis, Qdrant, S3 connectivity tests."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def check_all_services() -> dict[str, Any]:
    """Run all health checks and return aggregated status."""
    checks: dict[str, Any] = {}
    overall = "ok"

    checks["database"] = await _check_database()
    checks["redis"] = await _check_redis()
    checks["qdrant"] = await _check_qdrant()
    checks["s3"] = await _check_s3()

    for name, result in checks.items():
        if result.get("status") != "ok":
            overall = "degraded"

    return {"status": overall, "checks": checks}


async def _check_database() -> dict:
    """Test PostgreSQL connection."""
    start = time.monotonic()
    try:
        from sqlalchemy import text
        from app.core.database import async_session_factory

        async with async_session_factory() as db:
            result = await db.execute(text("SELECT 1"))
            result.scalar()

        return {"status": "ok", "latency_ms": _elapsed(start)}
    except Exception as e:
        logger.warning("Health check: database failed: %s", e)
        return {"status": "error", "error": str(e), "latency_ms": _elapsed(start)}


async def _check_redis() -> dict:
    """Test Redis connection."""
    start = time.monotonic()
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        await r.ping()
        await r.aclose()

        return {"status": "ok", "latency_ms": _elapsed(start)}
    except Exception as e:
        logger.warning("Health check: redis failed: %s", e)
        return {"status": "error", "error": str(e), "latency_ms": _elapsed(start)}


async def _check_qdrant() -> dict:
    """Test Qdrant vector DB connection."""
    start = time.monotonic()
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.qdrant_url}/collections")
            resp.raise_for_status()

        return {"status": "ok", "latency_ms": _elapsed(start)}
    except Exception as e:
        logger.warning("Health check: qdrant failed: %s", e)
        return {"status": "error", "error": str(e), "latency_ms": _elapsed(start)}


async def _check_s3() -> dict:
    """Test S3/MinIO connection."""
    start = time.monotonic()
    try:
        from app.services.s3_storage import S3Storage

        s3 = S3Storage()
        await s3.ensure_bucket()

        return {"status": "ok", "latency_ms": _elapsed(start)}
    except Exception as e:
        logger.warning("Health check: s3 failed: %s", e)
        return {"status": "error", "error": str(e), "latency_ms": _elapsed(start)}


def _elapsed(start: float) -> int:
    """Return elapsed milliseconds since start."""
    return int((time.monotonic() - start) * 1000)
