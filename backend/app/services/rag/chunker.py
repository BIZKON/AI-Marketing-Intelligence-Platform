"""Text chunking strategies for RAG ingestion.

Splits long messages into overlapping chunks and groups short chat messages
into conversation windows for better embedding quality.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import tiktoken

logger = logging.getLogger(__name__)

# Lazily initialised encoding — avoids network call at import time
_encoding: tiktoken.Encoding | None = None


def _get_encoding() -> tiktoken.Encoding:
    """Return the cl100k_base encoding, initialising it on first use."""
    global _encoding  # noqa: PLW0603
    if _encoding is None:
        _encoding = tiktoken.get_encoding("cl100k_base")
    return _encoding


@dataclass(frozen=True, slots=True)
class Chunk:
    """A single text chunk produced by the chunking strategy."""

    text: str
    chunk_index: int
    total_chunks: int
    metadata: dict[str, object] = field(default_factory=dict)


def _token_len(text: str) -> int:
    """Count tokens using cl100k_base encoding."""
    return len(_get_encoding().encode(text, disallowed_special=()))


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using a simple regex heuristic."""
    # Split on sentence-ending punctuation followed by whitespace or end
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p.strip()]


class ChunkingStrategy:
    """Configurable chunking strategy for Telegram messages.

    Parameters:
        chunk_size: Maximum chunk size in tokens.
        chunk_overlap: Number of overlapping tokens between adjacent chunks.
        min_chunk_size: Texts shorter than this (tokens) are returned as-is.
        group_short_messages: Whether to group short chat messages into windows.
        group_window: How many consecutive short messages to group together.
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        min_chunk_size: int = 50,
        group_short_messages: bool = True,
        group_window: int = 10,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.group_short_messages = group_short_messages
        self.group_window = group_window

    # ── Single-message chunking ──────────────────────────────────────────

    def chunk_message(
        self,
        text: str,
        message_type: str = "post",
    ) -> list[Chunk]:
        """Split a single message text into chunks.

        Args:
            text: Raw message text.
            message_type: One of ``"post"``, ``"chat"``, ``"group"``.

        Returns:
            List of :class:`Chunk` objects.  Short messages produce exactly one
            chunk; longer ones are split with token-level overlap.
        """
        if not text or not text.strip():
            return []

        text = text.strip()
        token_count = _token_len(text)

        # Short messages — return as a single chunk
        if token_count <= self.min_chunk_size:
            return [
                Chunk(
                    text=text,
                    chunk_index=0,
                    total_chunks=1,
                    metadata={"message_type": message_type, "token_count": token_count},
                )
            ]

        # Long messages — hierarchical split: paragraphs -> sentences -> tokens
        raw_pieces = self._split_by_paragraphs_and_sentences(text)

        # Merge small pieces into chunks respecting chunk_size with overlap
        chunks_text = self._merge_pieces_with_overlap(raw_pieces)

        total = len(chunks_text)
        return [
            Chunk(
                text=ct,
                chunk_index=idx,
                total_chunks=total,
                metadata={
                    "message_type": message_type,
                    "token_count": _token_len(ct),
                },
            )
            for idx, ct in enumerate(chunks_text)
        ]

    # ── Conversation grouping ────────────────────────────────────────────

    def chunk_conversation(
        self,
        messages: list[dict],
    ) -> list[dict]:
        """Group short chat/group messages into conversation windows.

        Each input dict is expected to have at least:
            - ``text`` (str)
            - ``author_id`` (str)
            - ``message_id`` (str)
            - ``date`` (str | datetime)

        Returns:
            List of dicts, each containing:
                - ``text``: concatenated text of the grouped messages
                - ``author_ids``: list of unique author IDs in the group
                - ``message_ids``: list of message IDs in the group
                - ``date_range``: ``{"start": ..., "end": ...}``
        """
        if not messages:
            return []

        if not self.group_short_messages:
            # No grouping — return each message individually
            return [
                {
                    "text": m.get("text", ""),
                    "author_ids": [m.get("author_id", "")],
                    "message_ids": [m.get("message_id", "")],
                    "date_range": {"start": m.get("date"), "end": m.get("date")},
                }
                for m in messages
                if m.get("text", "").strip()
            ]

        groups: list[dict] = []
        window: list[dict] = []

        for msg in messages:
            text = msg.get("text", "").strip()
            if not text:
                continue

            token_count = _token_len(text)

            # If a single message already exceeds chunk_size, flush the
            # current window and emit the long message on its own.
            if token_count > self.chunk_size:
                if window:
                    groups.append(self._flush_window(window))
                    window = []
                groups.append(
                    {
                        "text": text,
                        "author_ids": [msg.get("author_id", "")],
                        "message_ids": [msg.get("message_id", "")],
                        "date_range": {
                            "start": msg.get("date"),
                            "end": msg.get("date"),
                        },
                    }
                )
                continue

            window.append(msg)

            # Flush when the window reaches the configured size or the
            # accumulated text would exceed chunk_size.
            window_text = "\n".join(m.get("text", "") for m in window)
            if (
                len(window) >= self.group_window
                or _token_len(window_text) >= self.chunk_size
            ):
                groups.append(self._flush_window(window))
                window = []

        # Remaining messages
        if window:
            groups.append(self._flush_window(window))

        return groups

    # ── Internal helpers ─────────────────────────────────────────────────

    @staticmethod
    def _flush_window(window: list[dict]) -> dict:
        """Convert a window of messages into a grouped conversation dict."""
        texts: list[str] = []
        author_ids: list[str] = []
        message_ids: list[str] = []
        dates: list[object] = []

        for msg in window:
            text = msg.get("text", "").strip()
            if text:
                author = msg.get("author_username") or msg.get("author_name") or msg.get("author_id", "")
                texts.append(f"[{author}]: {text}" if author else text)
            aid = msg.get("author_id", "")
            if aid and aid not in author_ids:
                author_ids.append(aid)
            mid = msg.get("message_id", "")
            if mid:
                message_ids.append(mid)
            d = msg.get("date")
            if d:
                dates.append(d)

        return {
            "text": "\n".join(texts),
            "author_ids": author_ids,
            "message_ids": message_ids,
            "date_range": {
                "start": dates[0] if dates else None,
                "end": dates[-1] if dates else None,
            },
        }

    def _split_by_paragraphs_and_sentences(self, text: str) -> list[str]:
        """Hierarchically split text into small pieces.

        Strategy:
        1. Split by double newlines (paragraphs).
        2. If a paragraph is still too long, split into sentences.
        3. If a sentence is still too long, split by tokens directly.
        """
        paragraphs = re.split(r"\n{2,}", text.strip())
        pieces: list[str] = []

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if _token_len(para) <= self.chunk_size:
                pieces.append(para)
                continue

            # Paragraph exceeds chunk_size — split into sentences
            sentences = _split_sentences(para)
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                if _token_len(sentence) <= self.chunk_size:
                    pieces.append(sentence)
                    continue

                # Sentence still too long — hard-split by tokens
                pieces.extend(self._split_by_tokens(sentence))

        return pieces

    def _split_by_tokens(self, text: str) -> list[str]:
        """Split text into pieces of at most ``chunk_size`` tokens."""
        enc = _get_encoding()
        tokens = enc.encode(text, disallowed_special=())
        pieces: list[str] = []
        for start in range(0, len(tokens), self.chunk_size):
            piece_tokens = tokens[start : start + self.chunk_size]
            decoded = enc.decode(piece_tokens)
            if decoded.strip():
                pieces.append(decoded.strip())
        return pieces

    def _merge_pieces_with_overlap(self, pieces: list[str]) -> list[str]:
        """Merge small text pieces into chunks of up to ``chunk_size`` tokens.

        Adjacent chunks share ``chunk_overlap`` tokens of context.
        """
        if not pieces:
            return []

        # First pass: greedily merge consecutive pieces into chunks
        merged: list[str] = []
        current_parts: list[str] = []
        current_tokens = 0

        for piece in pieces:
            piece_tokens = _token_len(piece)
            if current_parts and current_tokens + piece_tokens > self.chunk_size:
                merged.append("\n\n".join(current_parts))
                # Keep overlap: walk back from the end of current_parts
                overlap_parts: list[str] = []
                overlap_tokens = 0
                for prev in reversed(current_parts):
                    pt = _token_len(prev)
                    if overlap_tokens + pt > self.chunk_overlap:
                        break
                    overlap_parts.insert(0, prev)
                    overlap_tokens += pt
                current_parts = overlap_parts
                current_tokens = overlap_tokens

            current_parts.append(piece)
            current_tokens += piece_tokens

        if current_parts:
            merged.append("\n\n".join(current_parts))

        return merged
