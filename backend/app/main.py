from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import (
    ab_tests, admin, auth, billing, calls, competitors, content, crm,
    export, gamification, multiplayer, reports, training, users, voice, voip,
)
from app.core.config import get_settings
from app.core.rate_limit import RateLimitMiddleware

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    yield
    # Shutdown
    from app.core.database import engine
    from app.core.redis import redis_client

    await redis_client.aclose()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.5.0",
    docs_url=f"{settings.api_prefix}/docs",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
app.add_middleware(RateLimitMiddleware)

# Routers
app.include_router(auth.router, prefix=f"{settings.api_prefix}/auth", tags=["auth"])
app.include_router(users.router, prefix=f"{settings.api_prefix}/users", tags=["users"])
app.include_router(billing.router, prefix=f"{settings.api_prefix}/billing", tags=["billing"])
app.include_router(competitors.router, prefix=f"{settings.api_prefix}/competitors", tags=["competitors"])
app.include_router(reports.router, prefix=f"{settings.api_prefix}/reports", tags=["reports"])
app.include_router(content.router, prefix=f"{settings.api_prefix}/content", tags=["content"])
app.include_router(admin.router, prefix=f"{settings.api_prefix}/admin", tags=["admin"])
app.include_router(training.router, prefix=f"{settings.api_prefix}/training", tags=["training"])
app.include_router(voice.router, prefix=f"{settings.api_prefix}/voice", tags=["voice"])
app.include_router(calls.router, prefix=f"{settings.api_prefix}/calls", tags=["calls"])
app.include_router(ab_tests.router, prefix=f"{settings.api_prefix}/ab-tests", tags=["ab-tests"])
app.include_router(multiplayer.router, prefix=f"{settings.api_prefix}/multiplayer", tags=["multiplayer"])
app.include_router(crm.router, prefix=f"{settings.api_prefix}/crm", tags=["crm"])
app.include_router(voip.router, prefix=f"{settings.api_prefix}/voip", tags=["voip"])
app.include_router(gamification.router, prefix=f"{settings.api_prefix}/gamification", tags=["gamification"])
app.include_router(export.router, prefix=f"{settings.api_prefix}/export", tags=["export"])


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/detailed")
async def health_detailed() -> dict:
    """Detailed health check — tests DB, Redis, and external service connectivity."""
    from app.core.health import check_all_services

    return await check_all_services()
