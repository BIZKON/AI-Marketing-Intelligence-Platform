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


# ── Content schemas ────────────────────────────────────────────────────────

from app.schemas.content import (
    ContentPlanCreate,
    ContentTaskCreate,
    ContentTaskUpdate,
    GenerateDraftRequest,
    GenerateResponse,
)


def test_content_plan_create_defaults():
    """ContentPlanCreate has sensible defaults."""
    plan = ContentPlanCreate()
    assert plan.period.value == "weekly"
    assert plan.title is None


def test_content_task_create_required_fields():
    """ContentTaskCreate requires title and platform."""
    task = ContentTaskCreate(title="Post about AI", platform="telegram")
    assert task.title == "Post about AI"
    assert task.content_type == "text"


def test_content_task_create_with_metadata():
    """ContentTaskCreate accepts metadata_json."""
    task = ContentTaskCreate(
        title="Story", platform="instagram",
        metadata_json={"hashtags": ["#ai", "#ml"]},
    )
    assert task.metadata_json["hashtags"] == ["#ai", "#ml"]


def test_content_task_update_partial():
    """ContentTaskUpdate allows partial updates."""
    update = ContentTaskUpdate(title="New Title")
    assert update.title == "New Title"
    assert update.platform is None
    assert update.content_type is None
    assert update.metadata_json is None


def test_generate_draft_request():
    """GenerateDraftRequest requires a task_id."""
    rid = uuid.uuid4()
    req = GenerateDraftRequest(task_id=rid)
    assert req.task_id == rid


def test_generate_response():
    """GenerateResponse serializes correctly."""
    rid = uuid.uuid4()
    resp = GenerateResponse(task_id=rid, status="generated", body_preview="AI text…")
    assert resp.status == "generated"


# ── Competitor schemas ─────────────────────────────────────────────────────

from app.schemas.competitor import (
    CompetitorCreate,
    CompetitorPostResponse,
    CompetitorUpdate,
)


def test_competitor_create_minimal():
    """CompetitorCreate works with just a name."""
    c = CompetitorCreate(name="Acme Corp")
    assert c.name == "Acme Corp"
    assert c.platforms == []


def test_competitor_create_full():
    """CompetitorCreate accepts all fields."""
    c = CompetitorCreate(
        name="Rival Inc",
        url="https://rival.com",
        platforms=["instagram", "telegram"],
        description="Main competitor",
    )
    assert len(c.platforms) == 2


def test_competitor_update_partial():
    """CompetitorUpdate allows partial updates."""
    u = CompetitorUpdate(name="New Name")
    assert u.name == "New Name"
    assert u.url is None


def test_competitor_post_response_defaults():
    """CompetitorPostResponse has default metric values."""
    from datetime import datetime

    post = CompetitorPostResponse(
        id=uuid.uuid4(),
        competitor_id=uuid.uuid4(),
        platform="telegram",
        created_at=datetime.now(),
    )
    assert post.views == 0
    assert post.likes == 0
    assert post.comments == 0
    assert post.shares == 0
