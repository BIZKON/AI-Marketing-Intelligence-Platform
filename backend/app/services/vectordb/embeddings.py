"""Embedding service — converts text to vector embeddings via OpenAI API.

Supports text-embedding-3-small (1536 dims) for cost efficiency.
Falls back to a simple TF-IDF-like hash if API key is not set (dev mode).
"""

from __future__ import annotations

import hashlib
import logging
import struct
from typing import Sequence

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

OPENAI_API_KEY = get_settings().openai_api_key
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
EMBEDDING_API_URL = "https://api.openai.com/v1/embeddings"

# Max tokens per request (roughly 8000 tokens ~= 30000 chars for safety)
MAX_TEXT_LENGTH = 25000


class EmbeddingService:
    """Generate embeddings for text content."""

    def __init__(self, api_key: str | None = None, model: str = EMBEDDING_MODEL) -> None:
        self.api_key = api_key or OPENAI_API_KEY
        self.model = model
        self.dim = EMBEDDING_DIM

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors (each is a list of floats).
        """
        if not texts:
            return []

        # Truncate long texts
        truncated = [t[:MAX_TEXT_LENGTH] if t else "" for t in texts]

        if not self.api_key:
            logger.warning("OPENAI_API_KEY not set, using fallback hash embeddings")
            return [_fallback_embedding(t, self.dim) for t in truncated]

        return await self._call_api(truncated)

    async def embed_single(self, text: str) -> list[float]:
        """Embed a single text string."""
        results = await self.embed_texts([text])
        return results[0] if results else _fallback_embedding(text, self.dim)

    async def _call_api(self, texts: list[str]) -> list[list[float]]:
        """Call OpenAI embeddings API in batches."""
        all_embeddings: list[list[float]] = []

        # Process in batches of 100 (API limit is 2048, but 100 is safe)
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            # Filter out empty strings and track their indices
            non_empty: list[tuple[int, str]] = [
                (j, t) for j, t in enumerate(batch) if t.strip()
            ]

            if not non_empty:
                all_embeddings.extend([_zero_vector(self.dim)] * len(batch))
                continue

            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    resp = await client.post(
                        EMBEDDING_API_URL,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "input": [t for _, t in non_empty],
                            "model": self.model,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()

                api_embeddings = [item["embedding"] for item in data["data"]]

                # Reconstruct full batch with zeros for empty strings
                batch_result: list[list[float]] = [_zero_vector(self.dim)] * len(batch)
                for (orig_idx, _), emb in zip(non_empty, api_embeddings):
                    batch_result[orig_idx] = emb

                all_embeddings.extend(batch_result)

            except Exception:
                logger.exception("OpenAI embedding API error, using fallback for batch")
                all_embeddings.extend(
                    [_fallback_embedding(t, self.dim) for t in batch]
                )

        return all_embeddings


def _fallback_embedding(text: str, dim: int) -> list[float]:
    """Generate a deterministic pseudo-embedding from text hash (dev/testing only).

    NOT suitable for semantic search — only for maintaining pipeline integrity.
    """
    if not text or not text.strip():
        return _zero_vector(dim)

    h = hashlib.sha512(text.encode("utf-8")).digest()
    # Repeat hash bytes to fill the dimension
    repeated = h * ((dim * 4 // len(h)) + 1)
    floats = struct.unpack(f"<{dim}f", repeated[: dim * 4])
    # Normalize to [-1, 1]
    max_val = max(abs(f) for f in floats) or 1.0
    return [f / max_val for f in floats]


def _zero_vector(dim: int) -> list[float]:
    return [0.0] * dim
