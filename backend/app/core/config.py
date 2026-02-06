from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "AI-Marketing-Platform"
    app_env: str = "development"
    debug: bool = False
    secret_key: str
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000"

    @model_validator(mode="after")
    def _validate_secret_key(self) -> "Settings":
        if self.secret_key in ("change-me-in-production", ""):
            raise ValueError(
                "SECRET_KEY must be set to a secure random value. "
                "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(64))'"
            )
        if len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        return self

    # Database
    database_url: str = "postgresql+asyncpg://platform:platform@localhost:5432/marketing_platform"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Telegram
    telegram_bot_token: str = ""
    telegram_webhook_url: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_monitor: str = ""
    stripe_price_creator: str = ""
    stripe_price_autopilot: str = ""
    stripe_price_enterprise: str = ""

    # AI
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Vector DB
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    # ElevenLabs
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""

    # HeyGen
    heygen_api_key: str = ""

    # S3
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket_name: str = "marketing-platform"
    s3_region: str = "us-east-1"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
