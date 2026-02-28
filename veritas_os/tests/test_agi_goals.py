# -*- coding: utf-8 -*-
"""Tests for AGI goal auto-adjust normalization safeguards."""

from veritas_os.core.agi_goals import auto_adjust_goals


def test_auto_adjust_goals_zero_total_falls_back_to_uniform() -> None:
    """When all weights are zero, auto_adjust_goals should return uniform weights."""
    result = auto_adjust_goals({"a": 0.0, "b": 0.0})

    assert result == {"a": 0.5, "b": 0.5}


def test_auto_adjust_goals_avoids_division_by_zero_with_tiny_total() -> None:
    """Very small totals should be normalized with a positive epsilon denominator."""
    weights = {"a": 1e-320, "b": 1e-320}

    result = auto_adjust_goals(weights)

    assert set(result.keys()) == {"a", "b"}
    assert result["a"] > 0.0
    assert result["b"] > 0.0
