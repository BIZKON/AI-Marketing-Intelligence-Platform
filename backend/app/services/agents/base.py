"""Base agent interface with RAG support via Claude API."""

from __future__ import annotations

import abc
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.vectordb.embeddings import EmbeddingService
from app.services.vectordb.qdrant_client import QdrantService

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = get_settings().anthropic_api_key
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 4096

# Simple circuit breaker for external APIs (#050)
_circuit_state: dict[str, dict] = {}
CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_RECOVERY_TIMEOUT = 60  # seconds


def _check_circuit(service: str) -> bool:
    """Return True if the circuit is closed (requests allowed)."""
    state = _circuit_state.get(service)
    if not state:
        return True
    if state["failures"] < CIRCUIT_FAILURE_THRESHOLD:
        return True
    # Circuit is open — check if recovery timeout has passed
    if time.monotonic() - state["last_failure"] > CIRCUIT_RECOVERY_TIMEOUT:
        state["failures"] = 0  # half-open → allow one request
        return True
    return False


def _record_failure(service: str) -> None:
    state = _circuit_state.setdefault(service, {"failures": 0, "last_failure": 0.0})
    state["failures"] += 1
    state["last_failure"] = time.monotonic()


def _record_success(service: str) -> None:
    _circuit_state.pop(service, None)


@dataclass
class AgentResult:
    """Standardized agent output."""

    agent_name: str
    content: str
    structured_data: dict[str, Any] = field(default_factory=dict)
    sources_used: int = 0
    tokens_used: int = 0
    model: str = ""


class BaseAgent(abc.ABC):
    """Abstract base class for AI agents with RAG capabilities."""

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        qdrant_service: QdrantService | None = None,
        api_key: str | None = None,
        model: str = CLAUDE_MODEL,
    ) -> None:
        self.embeddings = embedding_service or EmbeddingService()
        self.qdrant = qdrant_service or QdrantService()
        self.api_key = api_key or ANTHROPIC_API_KEY
        self.model = model

    @property
    @abc.abstractmethod
    def agent_name(self) -> str:
        """Unique agent identifier."""
        ...

    @property
    @abc.abstractmethod
    def system_prompt(self) -> str:
        """System prompt defining the agent's role and behavior."""
        ...

    @abc.abstractmethod
    def _build_user_message(self, context: str, query: str, **kwargs) -> str:
        """Build the user message from context and query."""
        ...

    async def run(
        self,
        query: str,
        user_id: str | None = None,
        competitor_ids: list[str] | None = None,
        extra_context: str = "",
        **kwargs,
    ) -> AgentResult:
        """Execute the agent with RAG context.

        1. Embed the query
        2. Search Qdrant for relevant content
        3. Build context from results
        4. Call Claude API with system prompt + context + query
        """
        # Step 1: Retrieve relevant context via RAG
        context_pieces: list[str] = []
        sources_used = 0

        if user_id or competitor_ids:
            try:
                query_embedding = await self.embeddings.embed_single(query)

                if competitor_ids:
                    results = await self.qdrant.search_by_competitor(
                        vector=query_embedding,
                        competitor_ids=competitor_ids,
                        limit=15,
                    )
                elif user_id:
                    results = await self.qdrant.search_by_user(
                        vector=query_embedding,
                        user_id=user_id,
                        limit=15,
                    )
                else:
                    results = []

                for hit in results:
                    payload = hit.get("payload", {})
                    score = hit.get("score", 0)
                    piece = self._format_source(payload, score)
                    if piece:
                        context_pieces.append(piece)
                        sources_used += 1

            except Exception:
                logger.exception("RAG retrieval failed for agent %s", self.agent_name)

        # Add any extra context provided
        if extra_context:
            context_pieces.append(f"\n--- Additional Context ---\n{extra_context}")

        context = "\n\n".join(context_pieces) if context_pieces else "No competitor data available."

        # Step 2: Call Claude
        user_message = self._build_user_message(context, query, **kwargs)
        result = await self._call_claude(user_message)

        return AgentResult(
            agent_name=self.agent_name,
            content=result.get("content", ""),
            structured_data=result.get("structured", {}),
            sources_used=sources_used,
            tokens_used=result.get("tokens", 0),
            model=self.model,
        )

    async def _call_claude(self, user_message: str) -> dict:
        """Call Claude API with the system prompt and user message.

        Includes circuit breaker to avoid cascading failures (#050).
        """
        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not set, returning placeholder")
            return {
                "content": "[AI анализ недоступен: API ключ не настроен]",
                "structured": {},
                "tokens": 0,
            }

        # Circuit breaker check (#050)
        if not _check_circuit("anthropic"):
            logger.warning("Circuit breaker OPEN for Anthropic API — skipping call")
            return {
                "content": "[AI временно недоступен. Сервис восстановится автоматически.]",
                "structured": {},
                "tokens": 0,
            }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    ANTHROPIC_API_URL,
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": MAX_TOKENS,
                        "system": self.system_prompt,
                        "messages": [
                            {"role": "user", "content": user_message},
                        ],
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            _record_success("anthropic")

            content_blocks = data.get("content", [])
            text = "\n".join(
                block.get("text", "") for block in content_blocks if block.get("type") == "text"
            )
            usage = data.get("usage", {})
            tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

            # Try to extract structured data from JSON blocks
            structured = self._extract_json(text)

            return {"content": text, "structured": structured, "tokens": tokens}

        except Exception:
            _record_failure("anthropic")
            logger.exception("Claude API call failed for agent %s", self.agent_name)
            return {
                "content": "[Ошибка при вызове AI. Попробуйте позже.]",
                "structured": {},
                "tokens": 0,
            }

    @staticmethod
    def _format_source(payload: dict, score: float) -> str:
        """Format a Qdrant search result as context text."""
        parts = []
        platform = payload.get("platform", "unknown")
        title = payload.get("title", "")
        text_preview = payload.get("text_preview", "")
        url = payload.get("url", "")
        views = payload.get("views", 0)
        likes = payload.get("likes", 0)
        published = payload.get("published_at", "")

        header = f"[{platform.upper()}] (relevance: {score:.2f})"
        if title:
            header += f" {title}"
        parts.append(header)
        if text_preview:
            parts.append(text_preview)
        if url:
            parts.append(f"URL: {url}")
        metrics = []
        if views:
            metrics.append(f"views={views}")
        if likes:
            metrics.append(f"likes={likes}")
        if published:
            metrics.append(f"date={published[:10]}")
        if metrics:
            parts.append("Metrics: " + ", ".join(metrics))

        return "\n".join(parts)

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Try to extract a JSON object from the response text."""
        # Look for ```json ... ``` blocks
        import re
        json_match = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        return {}
