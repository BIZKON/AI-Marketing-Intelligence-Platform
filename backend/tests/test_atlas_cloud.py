"""Tests for AtlasCloudClient — unified AI API gateway."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.core.atlas_cloud import (
    AtlasCloudClient,
    _check_circuit,
    _circuit_state,
    _record_failure,
    _record_success,
    CIRCUIT_FAILURE_THRESHOLD,
    CIRCUIT_RECOVERY_TIMEOUT,
    get_atlas_client,
)


@pytest.fixture(autouse=True)
def _reset_circuit():
    """Reset circuit breaker state between tests."""
    _circuit_state.clear()
    yield
    _circuit_state.clear()


@pytest.fixture
def client():
    return AtlasCloudClient(api_key="test-key", base_url="https://api.test.ai/v1")


# ── Circuit Breaker ────────────────────────────────────────────────────────────


def test_circuit_open_by_default():
    """Circuit is closed (open for traffic) by default."""
    assert _check_circuit("test_service") is True


def test_circuit_opens_after_threshold():
    """Circuit opens (blocks traffic) after CIRCUIT_FAILURE_THRESHOLD failures."""
    for _ in range(CIRCUIT_FAILURE_THRESHOLD):
        _record_failure("test_service")
    assert _check_circuit("test_service") is False


def test_circuit_below_threshold_stays_closed():
    """Circuit stays closed when failures are below threshold."""
    for _ in range(CIRCUIT_FAILURE_THRESHOLD - 1):
        _record_failure("test_service")
    assert _check_circuit("test_service") is True


def test_circuit_resets_on_success():
    """Recording success clears the circuit state."""
    for _ in range(CIRCUIT_FAILURE_THRESHOLD):
        _record_failure("test_service")
    _record_success("test_service")
    assert _check_circuit("test_service") is True


def test_circuit_recovers_after_timeout():
    """Circuit recovers after CIRCUIT_RECOVERY_TIMEOUT seconds."""
    for _ in range(CIRCUIT_FAILURE_THRESHOLD):
        _record_failure("test_service")
    # Simulate time passing
    _circuit_state["test_service"]["last_failure"] = time.monotonic() - CIRCUIT_RECOVERY_TIMEOUT - 1
    assert _check_circuit("test_service") is True


# ── Client Init ────────────────────────────────────────────────────────────────


def test_client_custom_api_key():
    """Client uses custom API key when provided."""
    c = AtlasCloudClient(api_key="my-key")
    assert c.api_key == "my-key"


def test_client_custom_base_url():
    """Client strips trailing slash from base URL."""
    c = AtlasCloudClient(api_key="k", base_url="https://example.com/v1/")
    assert c.base_url == "https://example.com/v1"


def test_auth_headers(client):
    """Auth headers contain Bearer token and Content-Type."""
    headers = client._auth_headers
    assert headers["Authorization"] == "Bearer test-key"
    assert headers["Content-Type"] == "application/json"


# ── Chat ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_returns_fallback_when_no_api_key():
    """Chat returns fallback message when API key is empty."""
    c = AtlasCloudClient(api_key="")
    result = await c.chat(messages=[{"role": "user", "content": "hi"}])
    assert "API ключ" in result["content"]
    assert result["tokens"] == 0


@pytest.mark.asyncio
async def test_chat_returns_fallback_when_circuit_open(client):
    """Chat returns fallback when circuit breaker is open."""
    for _ in range(CIRCUIT_FAILURE_THRESHOLD):
        _record_failure("atlas_chat")
    result = await client.chat(messages=[{"role": "user", "content": "hi"}])
    assert "временно недоступен" in result["content"]


@pytest.mark.asyncio
async def test_chat_success(client):
    """Chat returns parsed response on success."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Hello there"}}],
        "usage": {"total_tokens": 42},
        "model": "test-model",
    }

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("app.core.atlas_cloud.httpx.AsyncClient", return_value=mock_client):
        result = await client.chat(
            messages=[{"role": "user", "content": "Hi"}],
            system="Be helpful",
        )

    assert result["content"] == "Hello there"
    assert result["tokens"] == 42

    # Verify system message was prepended
    call_args = mock_client.post.call_args
    body = call_args.kwargs["json"]
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][0]["content"] == "Be helpful"
    assert body["messages"][1]["role"] == "user"


@pytest.mark.asyncio
async def test_chat_handles_exception(client):
    """Chat returns error fallback on exception and records failure."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=Exception("Connection error"))

    with patch("app.core.atlas_cloud.httpx.AsyncClient", return_value=mock_client):
        result = await client.chat(messages=[{"role": "user", "content": "Hi"}])

    assert "Ошибка" in result["content"]
    assert _circuit_state.get("atlas_chat", {}).get("failures", 0) >= 1


# ── Transcribe ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transcribe_no_api_key():
    """Transcribe returns error when API key is empty."""
    c = AtlasCloudClient(api_key="")
    result = await c.transcribe(b"audio-bytes")
    assert result["error"] == "API key not configured"


@pytest.mark.asyncio
async def test_transcribe_success(client):
    """Transcribe returns parsed response on success."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"text": "Привет мир", "language": "ru"}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("app.core.atlas_cloud.httpx.AsyncClient", return_value=mock_client):
        result = await client.transcribe(b"fake-audio", filename="test.mp3")

    assert result["text"] == "Привет мир"


# ── TTS ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tts_no_api_key():
    """TTS returns None when API key is empty."""
    c = AtlasCloudClient(api_key="")
    result = await c.text_to_speech("Hello")
    assert result is None


@pytest.mark.asyncio
async def test_tts_success(client):
    """TTS returns audio bytes on success."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.content = b"audio-data-bytes"

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("app.core.atlas_cloud.httpx.AsyncClient", return_value=mock_client):
        result = await client.text_to_speech("Привет")

    assert result == b"audio-data-bytes"


# ── Image Generation ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_image_no_api_key():
    """Image generation returns error when API key is empty."""
    c = AtlasCloudClient(api_key="")
    result = await c.generate_image("a cat")
    assert result["error"] == "API key not configured"


# ── Video Generation ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_video_no_api_key():
    """Video generation returns error when API key is empty."""
    c = AtlasCloudClient(api_key="")
    result = await c.generate_video(prompt="a dance")
    assert result["error"] == "API key not configured"


@pytest.mark.asyncio
async def test_get_video_status_no_api_key():
    """Video status check returns error when API key is empty."""
    c = AtlasCloudClient(api_key="")
    result = await c.get_video_status("task-123")
    assert result["error"] == "API key not configured"


# ── Singleton ──────────────────────────────────────────────────────────────────


def test_get_atlas_client_returns_same_instance():
    """get_atlas_client returns singleton instance."""
    import app.core.atlas_cloud as module

    module._client = None  # Reset
    c1 = get_atlas_client()
    c2 = get_atlas_client()
    assert c1 is c2
    module._client = None  # Cleanup
