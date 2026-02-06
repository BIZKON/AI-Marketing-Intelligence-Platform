"""Tests for TrainingService — AI-powered sales simulation and evaluation."""

from __future__ import annotations

import pytest

from app.services.training_service import TrainingService


class TestParseEvaluation:
    """Tests for _parse_evaluation static method."""

    def test_valid_json(self):
        """Parses valid JSON directly."""
        text = '{"overall_score": 85, "criteria_scores": {"greeting": 90}}'
        result = TrainingService._parse_evaluation(text)
        assert result["overall_score"] == 85
        assert result["criteria_scores"]["greeting"] == 90

    def test_json_in_markdown_code_block(self):
        """Extracts JSON from markdown code block."""
        text = '```json\n{"overall_score": 75, "criteria_scores": {}}\n```'
        result = TrainingService._parse_evaluation(text)
        assert result["overall_score"] == 75

    def test_json_in_plain_code_block(self):
        """Extracts JSON from plain code block."""
        text = '```\n{"overall_score": 60, "criteria_scores": {}}\n```'
        result = TrainingService._parse_evaluation(text)
        assert result["overall_score"] == 60

    def test_json_with_surrounding_text(self):
        """Extracts JSON from text with surrounding content."""
        text = 'Here is my analysis:\n{"overall_score": 70, "criteria_scores": {}}\nThank you.'
        result = TrainingService._parse_evaluation(text)
        assert result["overall_score"] == 70

    def test_invalid_text_returns_fallback(self):
        """Returns fallback structure for unparseable text."""
        text = "This is not JSON at all."
        result = TrainingService._parse_evaluation(text)
        assert result["overall_score"] == 0
        assert result["criteria_scores"] == {}
        assert "Не удалось выполнить оценку" in result["improvements"]

    def test_empty_string_returns_fallback(self):
        """Returns fallback for empty string."""
        result = TrainingService._parse_evaluation("")
        assert result["overall_score"] == 0


class TestComputeCriteriaAverages:
    """Tests for _compute_criteria_averages static method."""

    def test_single_entry(self):
        """Computes averages for a single criteria set."""
        criteria = [{"greeting": 80, "listening": 70}]
        result = TrainingService._compute_criteria_averages(criteria)
        assert result["greeting"] == 80.0
        assert result["listening"] == 70.0

    def test_multiple_entries(self):
        """Computes averages across multiple criteria sets."""
        criteria = [
            {"greeting": 80, "listening": 60},
            {"greeting": 90, "listening": 80},
        ]
        result = TrainingService._compute_criteria_averages(criteria)
        assert result["greeting"] == 85.0
        assert result["listening"] == 70.0

    def test_empty_list(self):
        """Returns empty dict for empty input."""
        result = TrainingService._compute_criteria_averages([])
        assert result == {}

    def test_ignores_non_numeric(self):
        """Ignores non-numeric values in criteria."""
        criteria = [{"greeting": 80, "comment": "good"}]
        result = TrainingService._compute_criteria_averages(criteria)
        assert "greeting" in result
        assert "comment" not in result


class TestDefaultPrompts:
    """Tests for system prompt generation."""

    def test_default_system_prompt(self):
        """Default system prompt is in Russian and mentions Алхимия."""
        prompt = TrainingService._default_system_prompt()
        assert "Алхимия" in prompt
        assert "клиент" in prompt

    def test_evaluation_system_prompt(self):
        """Evaluation prompt mentions JSON format."""
        prompt = TrainingService._evaluation_system_prompt()
        assert "JSON" in prompt
        assert "оцен" in prompt.lower()

    def test_build_evaluation_prompt_with_script(self):
        """Evaluation prompt includes ideal script when provided."""
        prompt = TrainingService._build_evaluation_prompt(
            transcript="Администратор: Здравствуйте!\nКлиент: Здравствуйте.",
            ideal_script="1. Приветствие\n2. Вопросы",
        )
        assert "ТРАНСКРИПТ" in prompt
        assert "ИДЕАЛЬНЫЙ СКРИПТ" in prompt
        assert "greeting" in prompt
        assert "listening" in prompt

    def test_build_evaluation_prompt_without_script(self):
        """Evaluation prompt works without ideal script."""
        prompt = TrainingService._build_evaluation_prompt(
            transcript="Администратор: Привет",
            ideal_script="",
        )
        assert "ТРАНСКРИПТ" in prompt
        assert "ИДЕАЛЬНЫЙ СКРИПТ" not in prompt


class TestAchievementDefs:
    """Tests for achievement definitions."""

    def test_all_achievements_have_required_fields(self):
        """Each achievement definition has name, icon, and description."""
        from app.services.training_service import ACHIEVEMENT_DEFS

        for key, ach in ACHIEVEMENT_DEFS.items():
            assert "name" in ach, f"Achievement {key} missing 'name'"
            assert "icon" in ach, f"Achievement {key} missing 'icon'"
            assert "description" in ach, f"Achievement {key} missing 'description'"

    def test_expected_achievements_exist(self):
        """All expected achievement types are defined."""
        from app.services.training_service import ACHIEVEMENT_DEFS

        expected = [
            "first_session", "sessions_10", "sessions_50",
            "perfect_score", "score_80_plus", "all_scenarios", "streak_7",
        ]
        for key in expected:
            assert key in ACHIEVEMENT_DEFS, f"Missing achievement: {key}"
