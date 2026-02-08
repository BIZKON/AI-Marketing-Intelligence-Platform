"""Unit tests for ChunkingStrategy and related helpers."""

import pytest

from app.services.rag.chunker import Chunk, ChunkingStrategy, _split_sentences, _token_len


# ── _token_len ───────────────────────────────────────────────────────────────


class TestTokenLen:
    def test_empty_string(self):
        assert _token_len("") == 0

    def test_single_word(self):
        count = _token_len("hello")
        assert count >= 1

    def test_longer_text(self):
        text = "The quick brown fox jumps over the lazy dog."
        count = _token_len(text)
        assert 5 < count < 30

    def test_unicode_text(self):
        count = _token_len("Привет мир! Как дела?")
        assert count > 0

    def test_emoji(self):
        count = _token_len("Hello 🌍🔥")
        assert count > 0


# ── _split_sentences ─────────────────────────────────────────────────────────


class TestSplitSentences:
    def test_single_sentence(self):
        result = _split_sentences("Hello world.")
        assert result == ["Hello world."]

    def test_multiple_sentences(self):
        result = _split_sentences("First sentence. Second sentence! Third?")
        assert len(result) == 3
        assert result[0] == "First sentence."
        assert result[1] == "Second sentence!"
        assert result[2] == "Third?"

    def test_no_punctuation(self):
        result = _split_sentences("no punctuation here")
        assert result == ["no punctuation here"]

    def test_empty_string(self):
        result = _split_sentences("")
        assert result == []


# ── Chunk dataclass ──────────────────────────────────────────────────────────


class TestChunk:
    def test_creation(self):
        c = Chunk(text="hello", chunk_index=0, total_chunks=1)
        assert c.text == "hello"
        assert c.chunk_index == 0
        assert c.total_chunks == 1
        assert c.metadata == {}

    def test_with_metadata(self):
        c = Chunk(text="x", chunk_index=0, total_chunks=1, metadata={"a": 1})
        assert c.metadata == {"a": 1}

    def test_frozen(self):
        c = Chunk(text="x", chunk_index=0, total_chunks=1)
        with pytest.raises(AttributeError):
            c.text = "y"  # type: ignore[misc]


# ── ChunkingStrategy.chunk_message ───────────────────────────────────────────


class TestChunkMessage:
    def setup_method(self):
        self.strategy = ChunkingStrategy(
            chunk_size=100, chunk_overlap=10, min_chunk_size=20,
        )

    def test_empty_text_returns_empty(self):
        assert self.strategy.chunk_message("") == []
        assert self.strategy.chunk_message("   ") == []
        assert self.strategy.chunk_message(None) == []  # type: ignore[arg-type]

    def test_short_text_single_chunk(self):
        chunks = self.strategy.chunk_message("Hello world")
        assert len(chunks) == 1
        assert chunks[0].chunk_index == 0
        assert chunks[0].total_chunks == 1
        assert chunks[0].text == "Hello world"
        assert chunks[0].metadata["message_type"] == "post"

    def test_custom_message_type(self):
        chunks = self.strategy.chunk_message("Hi", message_type="chat")
        assert chunks[0].metadata["message_type"] == "chat"

    def test_token_count_in_metadata(self):
        chunks = self.strategy.chunk_message("Short text")
        assert "token_count" in chunks[0].metadata
        assert chunks[0].metadata["token_count"] > 0

    def test_long_text_splits_into_multiple_chunks(self):
        # Create a text that definitely exceeds 100 tokens
        long_text = " ".join(f"Word{i}" for i in range(500))
        chunks = self.strategy.chunk_message(long_text)
        assert len(chunks) > 1

        # Verify chunk indexing
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
            assert chunk.total_chunks == len(chunks)

    def test_paragraphs_split_correctly(self):
        text = "First paragraph content here.\n\nSecond paragraph with more text.\n\nThird paragraph final words."
        small_strategy = ChunkingStrategy(
            chunk_size=15, chunk_overlap=3, min_chunk_size=5,
        )
        chunks = small_strategy.chunk_message(text)
        assert len(chunks) >= 2

    def test_whitespace_stripped(self):
        chunks = self.strategy.chunk_message("  trimmed text  ")
        assert chunks[0].text == "trimmed text"

    def test_chunks_dont_exceed_max_tokens(self):
        long_text = " ".join(f"word{i}" for i in range(1000))
        strategy = ChunkingStrategy(chunk_size=50, chunk_overlap=10, min_chunk_size=10)
        chunks = strategy.chunk_message(long_text)
        for chunk in chunks:
            # Allow some tolerance (overlap + merge rounding)
            assert chunk.metadata["token_count"] <= 80


# ── ChunkingStrategy.chunk_conversation ──────────────────────────────────────


class TestChunkConversation:
    def setup_method(self):
        self.strategy = ChunkingStrategy(
            chunk_size=100,
            chunk_overlap=10,
            min_chunk_size=20,
            group_short_messages=True,
            group_window=3,
        )

    def _msg(self, text, author_id="user1", message_id="1", date="2026-01-01"):
        return {
            "text": text,
            "author_id": author_id,
            "message_id": message_id,
            "date": date,
        }

    def test_empty_list(self):
        assert self.strategy.chunk_conversation([]) == []

    def test_single_short_message(self):
        msgs = [self._msg("Hello")]
        groups = self.strategy.chunk_conversation(msgs)
        assert len(groups) == 1
        assert "Hello" in groups[0]["text"]
        assert groups[0]["message_ids"] == ["1"]

    def test_groups_by_window_size(self):
        msgs = [
            self._msg("Msg 1", message_id="1"),
            self._msg("Msg 2", message_id="2"),
            self._msg("Msg 3", message_id="3"),
            self._msg("Msg 4", message_id="4"),
        ]
        groups = self.strategy.chunk_conversation(msgs)
        # With window=3, first 3 are grouped, then 4th is separate
        assert len(groups) == 2
        assert len(groups[0]["message_ids"]) == 3
        assert len(groups[1]["message_ids"]) == 1

    def test_unique_author_ids(self):
        msgs = [
            self._msg("A", author_id="alice", message_id="1"),
            self._msg("B", author_id="bob", message_id="2"),
            self._msg("C", author_id="alice", message_id="3"),
        ]
        groups = self.strategy.chunk_conversation(msgs)
        assert len(groups) == 1
        assert "alice" in groups[0]["author_ids"]
        assert "bob" in groups[0]["author_ids"]
        # alice should appear only once
        assert groups[0]["author_ids"].count("alice") == 1

    def test_date_range(self):
        msgs = [
            self._msg("A", date="2026-01-01", message_id="1"),
            self._msg("B", date="2026-01-05", message_id="2"),
        ]
        groups = self.strategy.chunk_conversation(msgs)
        assert groups[0]["date_range"]["start"] == "2026-01-01"
        assert groups[0]["date_range"]["end"] == "2026-01-05"

    def test_empty_messages_skipped(self):
        msgs = [
            self._msg("Hello", message_id="1"),
            self._msg("", message_id="2"),
            self._msg("  ", message_id="3"),
            self._msg("World", message_id="4"),
        ]
        groups = self.strategy.chunk_conversation(msgs)
        total_msg_ids = sum(len(g["message_ids"]) for g in groups)
        assert total_msg_ids == 2  # only "Hello" and "World"

    def test_grouping_disabled(self):
        no_group = ChunkingStrategy(group_short_messages=False)
        msgs = [
            self._msg("A", message_id="1"),
            self._msg("B", message_id="2"),
        ]
        groups = no_group.chunk_conversation(msgs)
        assert len(groups) == 2  # each message is its own group

    def test_long_message_emitted_alone(self):
        # Create a message that exceeds chunk_size tokens
        long_text = " ".join(f"word{i}" for i in range(500))
        msgs = [
            self._msg("Short", message_id="1"),
            self._msg(long_text, message_id="2"),
            self._msg("After", message_id="3"),
        ]
        groups = self.strategy.chunk_conversation(msgs)
        # Long message should be its own group
        long_group = [g for g in groups if len(g["text"]) > 100]
        assert len(long_group) >= 1
        assert long_group[0]["message_ids"] == ["2"]


# ── Edge cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_very_long_single_sentence(self):
        """A single sentence exceeding chunk_size must be hard-split by tokens."""
        strategy = ChunkingStrategy(chunk_size=20, chunk_overlap=5, min_chunk_size=5)
        sentence = "A " * 200  # One long 'sentence' without period
        chunks = strategy.chunk_message(sentence)
        assert len(chunks) > 1

    def test_only_newlines(self):
        strategy = ChunkingStrategy()
        assert strategy.chunk_message("\n\n\n") == []

    def test_cyrillic_text(self):
        strategy = ChunkingStrategy(chunk_size=50, min_chunk_size=10)
        text = "Привет мир. Как дела? Всё хорошо! Спасибо большое."
        chunks = strategy.chunk_message(text)
        assert len(chunks) >= 1
        assert "Привет" in chunks[0].text
