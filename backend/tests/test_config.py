"""Tests for application configuration."""

from app.core.config import Settings, get_settings


def test_get_settings_returns_settings():
    """get_settings returns a Settings instance."""
    s = get_settings()
    assert isinstance(s, Settings)


def test_settings_defaults():
    """Default settings have expected values."""
    s = get_settings()
    assert s.app_name == "AI-Marketing-Platform"
    assert s.api_prefix == "/api/v1"
    assert isinstance(s.debug, bool)
    assert s.app_env == "development"


def test_settings_is_production():
    """is_production returns False for development."""
    s = get_settings()
    assert s.is_production is False


def test_settings_has_database_url():
    """Database URL is configured."""
    s = get_settings()
    assert s.database_url
    assert "postgresql" in s.database_url


def test_settings_has_redis_url():
    """Redis URL is configured."""
    s = get_settings()
    assert s.redis_url
    assert "redis" in s.redis_url


def test_settings_cached():
    """get_settings is cached (returns same object)."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
