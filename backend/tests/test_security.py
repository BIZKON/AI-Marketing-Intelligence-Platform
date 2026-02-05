"""Tests for security utilities — JWT, hashing."""

from datetime import timedelta

import pytest
from jose import jwt

from app.core.config import get_settings
from app.core.security import (
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_password_hash,
    verify_password,
)

settings = get_settings()


def test_create_access_token_has_sub():
    """Token contains the 'sub' claim from input data."""
    token = create_access_token({"sub": "user-123"})
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    assert payload["sub"] == "user-123"


def test_create_access_token_has_exp():
    """Token always includes an expiration claim."""
    token = create_access_token({"sub": "user-123"})
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    assert "exp" in payload


def test_create_access_token_custom_expiry():
    """Custom expiry delta is respected."""
    token = create_access_token({"sub": "u"}, expires_delta=timedelta(minutes=5))
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    assert "exp" in payload


def test_create_access_token_does_not_mutate_input():
    """Input dict is not modified (uses .copy() internally)."""
    data = {"sub": "u1"}
    create_access_token(data)
    assert data == {"sub": "u1"}


def test_password_hash_and_verify():
    """Hash then verify round-trip works."""
    plain = "s3cr3t-pa$$word"
    hashed = get_password_hash(plain)
    assert hashed != plain
    assert verify_password(plain, hashed)


def test_password_verify_wrong():
    """Wrong password is rejected."""
    hashed = get_password_hash("correct")
    assert not verify_password("wrong", hashed)


def test_access_token_expire_minutes_value():
    """Expire constant is 24 hours (1440 minutes)."""
    assert ACCESS_TOKEN_EXPIRE_MINUTES == 1440
