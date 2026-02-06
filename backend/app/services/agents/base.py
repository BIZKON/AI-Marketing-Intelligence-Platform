"""Base agent interface with RAG support via Atlas Cloud API."""

from __future__ import annotations

import abc
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.atlas_cloud import get_atlas_client, DEFAULT_CHAT_MODEL
from app.services.vectordb.embeddings import EmbeddingService
from app.services.vectordb.qdrant_client import QdrantService

logger = logging.getLogger(__name__)

MAX_TOKENS = 4096


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
    """Abstract base class for AI agents with RAG capabilities.

    Uses Atlas Cloud as the unified AI gateway for all LLM calls.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        qdrant_service: QdrantService | None = None,
        model: str = DEFAULT_CHAT_MODEL,
    ) -> None:
        self.embeddings = embedding_service or EmbeddingService()
        self.qdrant = qdrant_service or QdrantService()
        self.model = model
        self.atlas = get_atlas_client()

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
        4. Call Atlas Cloud API with system prompt + context + query
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

        # Step 2: Call Atlas Cloud
        user_message = self._build_user_message(context, query, **kwargs)
        result = await self._call_llm(user_message)

        return AgentResult(
            agent_name=self.agent_name,
            content=result.get("content", ""),
            structured_data=result.get("structured", {}),
            sources_used=sources_used,
            tokens_used=result.get("tokens", 0),
            model=self.model,
        )

    async def _call_llm(self, user_message: str) -> dict:
        """Call Atlas Cloud API with the system prompt and user message."""
        result = await self.atlas.chat(
            messages=[{"role": "user", "content": user_message}],
            system=self.system_prompt,
            model=self.model,
            max_tokens=MAX_TOKENS,
        )

        content = result.get("content", "")
        tokens = result.get("tokens", 0)

        # Try to extract structured data from JSON blocks
        structured = self._extract_json(content)

        return {"content": content, "structured": structured, "tokens": tokens}

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
        import re
        json_match = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        return {}
