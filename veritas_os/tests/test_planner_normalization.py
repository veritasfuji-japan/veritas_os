"""Tests for planner normalization utility policies."""

import pytest

from veritas_os.core import planner_normalization as norm


def test_normalize_float_uses_default_for_invalid_input():
    value = norm.normalize_float(
        "invalid",
        field_name="eta_hours",
        default_override=2.5,
    )
    assert value == pytest.approx(2.5)


def test_normalize_float_clamps_by_policy_bounds():
    risk = norm.normalize_float(2.7, field_name="risk")
    assert risk == pytest.approx(1.0)


def test_normalize_float_reject_policy_raises_conversion_error():
    reject_rules = {
        **norm.NORMALIZATION_POLICY_TABLE,
        "custom": norm.NumericNormalizationRule(
            default=1.0,
            on_failure="reject",
        ),
    }

    with pytest.raises(ValueError):
        norm.normalize_float(
            "bad",
            field_name="custom",
            rule_overrides=reject_rules,
        )


def test_normalize_int_uses_common_policy_table():
    count = norm.normalize_int("5", field_name="decision_count")
    assert count == 5
