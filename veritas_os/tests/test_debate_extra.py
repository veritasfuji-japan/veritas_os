# veritas_os/tests/test_debate_extra.py
"""Additional tests for debate.py to improve coverage."""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from veritas_os.core import debate as debate_mod


class TestIsHardBlocked:
    """Tests for _is_hard_blocked function."""

    def test_blocked_true(self):
        """blocked=True should return True."""
        assert debate_mod._is_hard_blocked({"blocked": True}) is True

    def test_fuji_block_true(self):
        """fuji_block=True should return True."""
        assert debate_mod._is_hard_blocked({"fuji_block": True}) is True

    def test_safety_block_true(self):
        """safety_block=True should return True."""
        assert debate_mod._is_hard_blocked({"safety_block": True}) is True

    def test_is_blocked_true(self):
        """is_blocked=True should return True."""
        assert debate_mod._is_hard_blocked({"is_blocked": True}) is True

    def test_no_block_flags(self):
        """No block flags should return False."""
        assert debate_mod._is_hard_blocked({}) is False
        assert debate_mod._is_hard_blocked({"blocked": False}) is False


class TestNormalizeVerdictByScore:
    """Tests for _normalize_verdict_by_score function."""

    def test_valid_verdict_preserved(self):
        """Valid verdicts should be preserved."""
        assert debate_mod._normalize_verdict_by_score({"verdict": "採用推奨"}) == "採用推奨"
        assert debate_mod._normalize_verdict_by_score({"verdict": "要検討"}) == "要検討"
        assert debate_mod._normalize_verdict_by_score({"verdict": "却下"}) == "却下"

    def test_high_score_becomes_recommend(self):
        """Score >= 0.6 should become 採用推奨."""
        assert debate_mod._normalize_verdict_by_score({"score": 0.8}) == "採用推奨"
        assert debate_mod._normalize_verdict_by_score({"score": 0.6}) == "採用推奨"

    def test_medium_score_becomes_review(self):
        """Score 0.3-0.6 should become 要検討."""
        assert debate_mod._normalize_verdict_by_score({"score": 0.5}) == "要検討"
        assert debate_mod._normalize_verdict_by_score({"score": 0.3}) == "要検討"

    def test_low_score_becomes_reject(self):
        """Score < 0.3 should become 却下."""
        assert debate_mod._normalize_verdict_by_score({"score": 0.2}) == "却下"
        assert debate_mod._normalize_verdict_by_score({"score": 0.0}) == "却下"


class TestCalcRiskDelta:
    """Tests for _calc_risk_delta function."""

    def test_none_chosen_returns_default(self):
        """None chosen should return 0.30."""
        result = debate_mod._calc_risk_delta(None, [])
        assert result == 0.30


class TestSafeParse:
    """Tests for _safe_parse function."""

    def test_none_returns_empty(self):
        """None should return empty options."""
        result = debate_mod._safe_parse(None)
        assert result == {"options": [], "chosen_id": None}

    def test_dict_preserved(self):
        """Dict should be preserved with defaults."""
        result = debate_mod._safe_parse({"options": [{"id": "1"}]})
        assert result["options"] == [{"id": "1"}]

    def test_dict_without_options(self):
        """Dict without options should get empty options."""
        result = debate_mod._safe_parse({"other": "value"})
        assert result["options"] == []
        assert result["chosen_id"] is None

    def test_list_becomes_options(self):
        """List should become options array."""
        result = debate_mod._safe_parse([{"id": "1"}, {"id": "2"}])
        assert result["options"] == [{"id": "1"}, {"id": "2"}]
        assert result["chosen_id"] is None

    def test_non_string_converted(self):
        """Non-string values should be converted."""
        result = debate_mod._safe_parse(123)
        assert "options" in result


class TestSafeJsonExtractLike:
    """Tests for _safe_json_extract_like function."""

    def test_valid_json_string(self):
        """Valid JSON string should be parsed."""
        result = debate_mod._safe_json_extract_like('{"options": [{"id": "1"}]}')
        assert "options" in result

    def test_json_with_code_fence(self):
        """JSON in code fence should be extracted."""
        raw = '```json\n{"options": [{"id": "1"}]}\n```'
        result = debate_mod._safe_json_extract_like(raw)
        assert "options" in result

    def test_malformed_json_rescued(self):
        """Malformed JSON should attempt rescue."""
        # JSON with trailing comma (invalid)
        raw = '{"options": [{"id": "1"},]}'
        result = debate_mod._safe_json_extract_like(raw)
        # Should return something (either parsed or empty)
        assert "options" in result

    def test_options_array_extraction(self):
        """Options array embedded in text should be extracted."""
        raw = 'Some text "options": [{"id": "1"}, {"id": "2"}] more text'
        result = debate_mod._safe_json_extract_like(raw)
        assert "options" in result


class TestSelectBestCandidate:
    """Tests for _select_best_candidate function."""

    def test_empty_list_returns_none(self):
        """Empty list should return None."""
        result = debate_mod._select_best_candidate([], min_score=0.0)
        assert result is None

    def test_selects_highest_score_non_blocked(self):
        """Should select highest scoring non-blocked option."""
        options = [
            {"id": "1", "score": 0.5, "verdict": "採用推奨"},
            {"id": "2", "score": 0.9, "verdict": "採用推奨"},
        ]
        result = debate_mod._select_best_candidate(options, min_score=0.3)
        assert result is not None
        assert result.get("id") == "2"

    def test_skips_blocked_options(self):
        """Should skip blocked options."""
        options = [
            {"id": "1", "score": 0.9, "blocked": True},
            {"id": "2", "score": 0.5, "verdict": "採用推奨"},
        ]
        result = debate_mod._select_best_candidate(options, min_score=0.3)
        assert result is not None
        assert result.get("id") == "2"

    def test_respects_min_score(self):
        """Should filter by min_score."""
        options = [
            {"id": "1", "score": 0.2},
            {"id": "2", "score": 0.5},
        ]
        result = debate_mod._select_best_candidate(options, min_score=0.4)
        assert result is not None
        assert result.get("id") == "2"

    def test_allow_rejected_flag(self):
        """allow_rejected should include rejected options."""
        options = [
            {"id": "1", "score": 0.9, "verdict": "却下"},
            {"id": "2", "score": 0.5, "verdict": "採用推奨"},
        ]
        # Without allow_rejected, should pick id 2
        result = debate_mod._select_best_candidate(options, min_score=0.0, allow_rejected=False)
        assert result is not None
        assert result.get("id") == "2"

        # With allow_rejected, should pick id 1 (highest score)
        result = debate_mod._select_best_candidate(options, min_score=0.0, allow_rejected=True)
        assert result is not None
        assert result.get("id") == "1"


class TestCreateDegradedChoice:
    """Tests for _create_degraded_choice function."""

    def test_empty_list_returns_none(self):
        """Empty list should return None."""
        result = debate_mod._create_degraded_choice([])
        assert result is None

    def test_returns_first_non_blocked(self):
        """Should return first non-blocked option."""
        options = [
            {"id": "1", "blocked": True},
            {"id": "2"},
        ]
        result = debate_mod._create_degraded_choice(options)
        if result is not None:
            assert result.get("id") == "2"


class TestFallbackDebate:
    """Tests for _fallback_debate function."""

    def test_empty_options(self):
        """Empty options should return result."""
        result = debate_mod._fallback_debate([])
        assert result is not None

    def test_with_options(self):
        """Should return result with options."""
        options = [{"id": "1", "title": "Test", "score": 0.8}]
        result = debate_mod._fallback_debate(options)
        assert result is not None


class TestIsRejected:
    """Tests for _is_rejected function."""

    def test_reject_verdicts(self):
        """Rejected verdicts should return True."""
        assert debate_mod._is_rejected({"verdict": "却下"}) is True
        assert debate_mod._is_rejected({"verdict": "reject"}) is True
        assert debate_mod._is_rejected({"verdict": "Rejected"}) is True
        assert debate_mod._is_rejected({"verdict": "NG"}) is True

    def test_non_reject_verdicts(self):
        """Non-rejected verdicts should return False."""
        assert debate_mod._is_rejected({"verdict": "採用推奨"}) is False
        assert debate_mod._is_rejected({"verdict": "要検討"}) is False
        assert debate_mod._is_rejected({}) is False


class TestGetScore:
    """Tests for _get_score function."""

    def test_score_from_score_field(self):
        """Should get score from score field."""
        assert debate_mod._get_score({"score": 0.8}) == 0.8

    def test_score_from_score_raw(self):
        """Should fallback to score_raw."""
        assert debate_mod._get_score({"score_raw": 0.7}) == 0.7

    def test_clamps_to_01(self):
        """Score should be clamped to 0-1."""
        assert debate_mod._get_score({"score": 1.5}) == 1.0
        assert debate_mod._get_score({"score": -0.5}) == 0.0

    def test_invalid_score_returns_zero(self):
        """Invalid score should return 0."""
        assert debate_mod._get_score({"score": "invalid"}) == 0.0
        assert debate_mod._get_score({}) == 0.0


class TestLooksDangerousText:
    """Tests for _looks_dangerous_text function."""

    def test_dangerous_keywords_detected(self):
        """Dangerous keywords should be detected."""
        assert debate_mod._looks_dangerous_text({"title": "自殺の方法"}) is True
        assert debate_mod._looks_dangerous_text({"detail": "make a weapon"}) is True
        assert debate_mod._looks_dangerous_text({"description": "illegal activity"}) is True

    def test_safe_text_not_flagged(self):
        """Safe text should not be flagged."""
        assert debate_mod._looks_dangerous_text({"title": "普通のタイトル"}) is False
        assert debate_mod._looks_dangerous_text({"detail": "normal content"}) is False
