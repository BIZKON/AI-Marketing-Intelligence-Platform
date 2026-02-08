"""Test-level conftest — patches tiktoken for offline environments.

The cl100k_base encoding requires downloading from Azure Blob Storage,
which may not be available in sandboxed CI environments.  This conftest
monkey-patches the chunker module to use a simple estimator instead.
"""

from __future__ import annotations

import pytest


class _FakeEncoding:
    """Minimal tiktoken-compatible encoding (~1 token per 4 chars)."""

    def encode(self, text: str, **_kwargs) -> list[int]:
        if not text:
            return []
        return list(range(max(1, len(text) // 4)))

    def decode(self, tokens: list[int]) -> str:
        return "x" * (len(tokens) * 4)


@pytest.fixture(autouse=True)
def _patch_tiktoken(monkeypatch):
    """Replace tiktoken encoding in the chunker module with a fake."""
    try:
        import tiktoken
        tiktoken.get_encoding("cl100k_base")
    except Exception:
        # Tiktoken not available — patch with fake
        import app.services.rag.chunker as chunker_mod
        monkeypatch.setattr(chunker_mod, "_encoding", _FakeEncoding())
