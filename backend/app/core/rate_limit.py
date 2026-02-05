"""Token-bucket rate limiting middleware using in-memory storage.

Limits API requests per IP. Unauthenticated: 30 req/min, Authenticated: 120 req/min.
Health check and docs endpoints are exempt.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Rate limits
ANON_RATE = 30  # requests per window
AUTH_RATE = 120  # requests per window
WINDOW_SECONDS = 60

# Exempt paths (no rate limiting)
EXEMPT_PREFIXES = ("/health", "/api/v1/docs", "/api/v1/openapi.json")


@dataclass
class _Bucket:
    tokens: float
    last_refill: float = field(default_factory=time.monotonic)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory token bucket rate limiter.

    In production, replace with Redis-backed implementation for multi-process support.
    """

    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self._buckets: dict[str, _Bucket] = defaultdict(
            lambda: _Bucket(tokens=ANON_RATE)
        )

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Exempt health checks and docs
        if any(path.startswith(p) for p in EXEMPT_PREFIXES):
            return await call_next(request)

        # Determine rate limit based on auth
        has_auth = "authorization" in request.headers
        max_tokens = AUTH_RATE if has_auth else ANON_RATE

        # Get client identifier (IP or forwarded IP)
        client_ip = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()

        key = f"{client_ip}:{'auth' if has_auth else 'anon'}"

        # Token bucket algorithm
        bucket = self._buckets[key]
        now = time.monotonic()
        elapsed = now - bucket.last_refill

        # Refill tokens
        bucket.tokens = min(max_tokens, bucket.tokens + elapsed * (max_tokens / WINDOW_SECONDS))
        bucket.last_refill = now

        if bucket.tokens < 1:
            retry_after = int(WINDOW_SECONDS / max_tokens)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        bucket.tokens -= 1

        # Cleanup old buckets periodically (every 1000 requests)
        if len(self._buckets) > 10000:
            self._cleanup(now)

        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(max_tokens)
        response.headers["X-RateLimit-Remaining"] = str(int(bucket.tokens))

        return response

    def _cleanup(self, now: float) -> None:
        """Remove stale buckets older than 5 minutes."""
        stale = [k for k, v in self._buckets.items() if now - v.last_refill > 300]
        for k in stale:
            del self._buckets[k]
