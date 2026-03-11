# -*- coding: utf-8 -*-
"""
Tests for pipeline split-refactoring:
- _to_bool delegation to _to_bool_local
- _flatten_memory_hits (extracted from nested _append_hits)
- _apply_value_boost (extracted from nested _apply_boost)
"""

import pytest

from veritas_os.core.pipeline import _to_bool
from veritas_os.core.pipeline_helpers import _to_bool_local, _apply_value_boost
from veritas_os.core.pipeline_memory_adapter import _flatten_memory_hits


# =========================================================
# _to_bool delegation tests
# =========================================================


class TestToBoolDelegation:
    """_to_bool in pipeline.py should delegate to _to_bool_local."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            (True, True),
            (False, False),
            (1, True),
            (0, False),
            (1.5, True),
            (0.0, False),
            (None, False),
            ("true", True),
            ("false", False),
            ("1", True),
            ("0", False),
            ("yes", True),
            ("no", False),
            ("on", True),
            ("off", False),
            ("", False),
            ("random", False),
            ("  TRUE  ", True),
        ],
    )
    def test_to_bool_matches_to_bool_local(self, value, expected):
        assert _to_bool(value) == expected
        assert _to_bool(value) == _to_bool_local(value)


# =========================================================
# _flatten_memory_hits tests
# =========================================================


class TestFlattenMemoryHits:
    """Tests for _flatten_memory_hits extracted from nested _append_hits."""

    def test_none_returns_empty(self):
        assert _flatten_memory_hits(None) == []

    def test_empty_dict_returns_empty(self):
        assert _flatten_memory_hits({}) == []

    def test_empty_list_returns_empty(self):
        assert _flatten_memory_hits([]) == []

    def test_dict_with_kind_lists(self):
        src = {
            "semantic": [{"id": "1", "text": "hello"}],
            "episodic": [{"id": "2", "text": "world"}],
        }
        result = _flatten_memory_hits(src)
        assert len(result) == 2
        assert result[0]["kind"] == "semantic"
        assert result[0]["id"] == "1"
        assert result[1]["kind"] == "episodic"

    def test_dict_skips_non_list_values(self):
        src = {"semantic": "not_a_list", "episodic": [{"id": "1"}]}
        result = _flatten_memory_hits(src)
        assert len(result) == 1

    def test_dict_skips_non_dict_hits(self):
        src = {"semantic": [{"id": "1"}, "bad", 42, None]}
        result = _flatten_memory_hits(src)
        assert len(result) == 1

    def test_dict_default_kind_fills_none_kind(self):
        src = {"": [{"id": "1"}]}
        result = _flatten_memory_hits(src, default_kind="doc")
        assert result[0]["kind"] == "doc"

    def test_list_input(self):
        src = [{"id": "1", "kind": "semantic"}, {"id": "2"}]
        result = _flatten_memory_hits(src)
        assert len(result) == 2
        assert result[0]["kind"] == "semantic"
        assert result[1].get("kind") is None  # no default_kind set

    def test_list_with_default_kind(self):
        src = [{"id": "1"}, {"id": "2", "kind": "semantic"}]
        result = _flatten_memory_hits(src, default_kind="doc")
        assert result[0]["kind"] == "doc"
        assert result[1]["kind"] == "semantic"  # existing kind preserved

    def test_list_skips_non_dicts(self):
        src = [{"id": "1"}, "bad", None, 42]
        result = _flatten_memory_hits(src)
        assert len(result) == 1

    def test_original_dict_not_mutated(self):
        h = {"id": "1"}
        src = [h]
        result = _flatten_memory_hits(src, default_kind="doc")
        # result should be a copy, not the same dict
        assert result[0] is not h
        assert result[0]["kind"] == "doc"

    def test_false_value_returns_empty(self):
        assert _flatten_memory_hits(0) == []
        assert _flatten_memory_hits("") == []
        assert _flatten_memory_hits(False) == []


# =========================================================
# _apply_value_boost tests
# =========================================================


class TestApplyValueBoost:
    """Tests for _apply_value_boost extracted from nested _apply_boost."""

    def test_positive_boost(self):
        alts = [{"title": "A", "score": 1.0}]
        result = _apply_value_boost(alts, 0.1)
        assert len(result) == 1
        assert result[0]["score"] == pytest.approx(1.1)
        assert result[0]["score_raw"] == pytest.approx(1.0)

    def test_negative_boost(self):
        alts = [{"title": "A", "score": 1.0}]
        result = _apply_value_boost(alts, -0.1)
        assert len(result) == 1
        assert result[0]["score"] == pytest.approx(0.9)

    def test_zero_boost(self):
        alts = [{"title": "A", "score": 1.0}]
        result = _apply_value_boost(alts, 0.0)
        assert result[0]["score"] == pytest.approx(1.0)

    def test_score_never_negative(self):
        alts = [{"title": "A", "score": 0.1}]
        result = _apply_value_boost(alts, -2.0)
        assert result[0]["score"] >= 0.0

    def test_missing_score_defaults_to_1(self):
        alts = [{"title": "A"}]
        result = _apply_value_boost(alts, 0.05)
        assert result[0]["score"] == pytest.approx(1.05)
        assert result[0]["score_raw"] == pytest.approx(1.0)

    def test_preserves_existing_score_raw(self):
        alts = [{"title": "A", "score": 1.1, "score_raw": 0.9}]
        result = _apply_value_boost(alts, 0.05)
        assert result[0]["score_raw"] == pytest.approx(0.9)

    def test_non_dict_items_filtered(self):
        alts = [{"title": "A", "score": 1.0}, "bad", None, 42]
        result = _apply_value_boost(alts, 0.0)
        assert len(result) == 1

    def test_empty_list(self):
        assert _apply_value_boost([], 0.1) == []

    def test_multiple_alts(self):
        alts = [
            {"title": "A", "score": 1.0},
            {"title": "B", "score": 2.0},
        ]
        result = _apply_value_boost(alts, 0.1)
        assert result[0]["score"] == pytest.approx(1.1)
        assert result[1]["score"] == pytest.approx(2.2)

    def test_invalid_score_value(self):
        alts = [{"title": "A", "score": "not_a_number"}]
        result = _apply_value_boost(alts, 0.1)
        assert len(result) == 1  # item still included
        assert result[0]["score"] == "not_a_number"  # setdefault keeps existing
        assert result[0]["score_raw"] == 1.0  # safe default set

    def test_missing_score_after_failure_gets_default(self):
        """When score key is absent and conversion fails, safe defaults are applied."""
        class BadScore:
            """Object whose float() raises."""
            def __float__(self):
                raise ValueError("boom")
        alts = [{"title": "A", "score": BadScore()}]
        result = _apply_value_boost(alts, 0.1)
        assert len(result) == 1
        # setdefault won't override existing "score" key even though it's BadScore
        assert result[0].get("score_raw") == 1.0
