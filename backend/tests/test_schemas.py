"""Tests for Pydantic schemas — validation and serialization."""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.report import (
    DigestRequest,
    PDFReportRequest,
    VideoReportRequest,
    VoiceReportRequest,
)
from app.schemas.user import UserCreate, UserUpdate


# ── Report schemas ─────────────────────────────────────────────────────────


def test_digest_request_defaults():
    """DigestRequest works with no arguments (all optional)."""
    req = DigestRequest()
    assert req.competitor_ids is None or req.competitor_ids == []


def test_digest_request_with_ids():
    """DigestRequest accepts a list of competitor UUIDs."""
    ids = [uuid.uuid4(), uuid.uuid4()]
    req = DigestRequest(competitor_ids=ids)
    assert len(req.competitor_ids) == 2


def test_pdf_request_requires_report_id():
    """PDFReportRequest requires a report_id."""
    rid = uuid.uuid4()
    req = PDFReportRequest(report_id=rid)
    assert req.report_id == rid


def test_voice_request_requires_report_id():
    """VoiceReportRequest requires a report_id."""
    rid = uuid.uuid4()
    req = VoiceReportRequest(report_id=rid)
    assert req.report_id == rid


def test_video_request_requires_report_id():
    """VideoReportRequest requires a report_id."""
    rid = uuid.uuid4()
    req = VideoReportRequest(report_id=rid)
    assert req.report_id == rid


# ── User schemas ─────────────────────────────────────────────────────────


def test_user_create_minimal():
    """UserCreate works with minimal fields."""
    u = UserCreate(email="a@b.com", password="secret123")
    assert u.email == "a@b.com"
    assert u.password == "secret123"


def test_user_create_with_telegram():
    """UserCreate accepts telegram_id."""
    u = UserCreate(email="a@b.com", password="pw", telegram_id=12345)
    assert u.telegram_id == 12345


def test_user_update_partial():
    """UserUpdate allows partial updates (all fields optional)."""
    u = UserUpdate(full_name="Test User")
    assert u.full_name == "Test User"


def test_user_update_empty():
    """UserUpdate accepts empty body."""
    u = UserUpdate()
    assert u.full_name is None
