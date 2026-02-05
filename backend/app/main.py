from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import auth, billing, competitors, content, reports, users
from app.core.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    yield
    # Shutdown
    from app.core.database import engine

    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url=f"{settings.api_prefix}/docs",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix=f"{settings.api_prefix}/auth", tags=["auth"])
app.include_router(users.router, prefix=f"{settings.api_prefix}/users", tags=["users"])
app.include_router(billing.router, prefix=f"{settings.api_prefix}/billing", tags=["billing"])
app.include_router(competitors.router, prefix=f"{settings.api_prefix}/competitors", tags=["competitors"])
app.include_router(reports.router, prefix=f"{settings.api_prefix}/reports", tags=["reports"])
app.include_router(content.router, prefix=f"{settings.api_prefix}/content", tags=["content"])


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
