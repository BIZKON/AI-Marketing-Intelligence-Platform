"""Token-bucket rate limiting middleware using Redis for multi-process support.

Limits API requests per IP. Unauthenticated: 30 req/min, Authenticated: 120 req/min.
Health check and docs endpoints are exempt.
"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Rate limits
ANON_RATE = 30  # requests per window
AUTH_RATE = 120  # requests per window
WINDOW_SECONDS = 60

# Exempt paths (no rate limiting)
EXEMPT_PREFIXES = ("/health", "/api/v1/docs", "/api/v1/openapi.json")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-backed sliding window rate limiter.

    Falls back to pass-through if Redis is unavailable (fail-open).
    """

    def __init__(self, app, redis_url: str | None = None, **kwargs):
        super().__init__(app, **kwargs)
        self._redis = None
        self._redis_url = redis_url

    async def _get_redis(self):
        if self._redis is None:
            try:
                from app.core.config import get_settings
                import redis.asyncio as aioredis

                url = self._redis_url or get_settings().redis_url
                self._redis = aioredis.from_url(url, decode_responses=True)
                # Test connection
                await self._redis.ping()
            except Exception:
                logger.warning("Redis unavailable for rate limiting, falling back to pass-through")
                self._redis = None
        return self._redis

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Exempt health checks and docs
        if any(path.startswith(p) for p in EXEMPT_PREFIXES):
            return await call_next(request)

        # Determine rate limit based on auth
        has_auth = "authorization" in request.headers
        max_tokens = AUTH_RATE if has_auth else ANON_RATE

        # Get client identifier from actual connection (ignore X-Forwarded-For to prevent spoofing)
        client_ip = request.client.host if request.client else "unknown"
        key = f"ratelimit:{client_ip}:{'auth' if has_auth else 'anon'}"

        r = await self._get_redis()
        if r is None:
            # Fail-open: if Redis is down, allow the request
            return await call_next(request)

        try:
            remaining = await self._check_rate_limit(r, key, max_tokens)
        except Exception:
            # Fail-open on Redis errors
            logger.warning("Rate limit check failed, allowing request")
            return await call_next(request)

        if remaining < 0:
            retry_after = int(WINDOW_SECONDS / max_tokens)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(max_tokens)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))

        return response

    @staticmethod
    async def _check_rate_limit(r, key: str, max_tokens: int) -> int:
        """Sliding window counter using Redis sorted sets.

        Returns remaining tokens (negative = over limit).
        """
        now = time.time()
        window_start = now - WINDOW_SECONDS

        pipe = r.pipeline()
        # Remove old entries outside the window
        pipe.zremrangebyscore(key, 0, window_start)
        # Count current requests in window
        pipe.zcard(key)
        # Add current request
        pipe.zadd(key, {f"{now}": now})
        # Set TTL so keys auto-expire
        pipe.expire(key, WINDOW_SECONDS + 1)
        results = await pipe.execute()

        current_count = results[1]  # zcard result
        remaining = max_tokens - current_count - 1
        return remaining
