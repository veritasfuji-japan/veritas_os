"""Tests for FUJI policy diff replay and canary rollout utilities."""

from __future__ import annotations

import math

from veritas_os.core.fuji import _DEFAULT_POLICY
from veritas_os.core.fuji_policy_rollout import (
    PolicyReplaySample,
    _evaluate_sample,
    canary_bucket,
    replay_policy_diff,
)


def _strict_policy() -> dict:
    policy = dict(_DEFAULT_POLICY)
    policy["actions"] = {
        "allow": {"risk_upper": 0.20},
        "warn": {"risk_upper": 0.35},
        "human_review": {"risk_upper": 0.50},
        "deny": {"risk_upper": 1.00},
    }
    return policy


def test_replay_policy_diff_returns_transition_metrics() -> None:
    stable = dict(_DEFAULT_POLICY)
    canary = _strict_policy()

    samples = [
        PolicyReplaySample(sample_id="s1", risk=0.1, categories=[]),
        PolicyReplaySample(sample_id="s2", risk=0.45, categories=[]),
        PolicyReplaySample(sample_id="s3", risk=0.7, categories=[]),
    ]

    result = replay_policy_diff(samples=samples, stable_policy=stable, canary_policy=canary)

    assert result["total"] == 3
    assert result["changed"] >= 1
    assert "allow->hold" in result["transitions"] or "hold->deny" in result["transitions"]
    assert len(result["outcomes"]) == 3


def test_replay_policy_diff_calculates_fp_fn_when_labels_exist() -> None:
    stable = dict(_DEFAULT_POLICY)
    canary = _strict_policy()

    samples = [
        PolicyReplaySample(sample_id="s1", risk=0.25, categories=[], expected_decision="allow"),
        PolicyReplaySample(sample_id="s2", risk=0.05, categories=[], expected_decision="allow"),
        PolicyReplaySample(sample_id="s3", risk=0.9, categories=[], expected_decision="deny"),
    ]

    result = replay_policy_diff(samples=samples, stable_policy=stable, canary_policy=canary)

    assert result["labeled"] == 3
    assert result["false_positive"] >= 0
    assert result["false_negative"] >= 0
    assert 0.0 <= result["false_positive_rate"] <= 1.0
    assert 0.0 <= result["false_negative_rate"] <= 1.0


def test_canary_bucket_is_deterministic_and_respects_ratio() -> None:
    request_id = "req-12345"
    bucket1 = canary_bucket(request_id, 0.25)
    bucket2 = canary_bucket(request_id, 0.25)

    assert bucket1 in {"stable", "canary"}
    assert bucket1 == bucket2

    assert canary_bucket(request_id, 0.0) == "stable"
    assert canary_bucket(request_id, 1.0) == "canary"


def test_canary_bucket_clamps_out_of_range_ratio() -> None:
    request_id = "req-out-of-range"
    assert canary_bucket(request_id, -1.0) == "stable"
    assert canary_bucket(request_id, 2.0) == "canary"


def test_canary_bucket_nan_ratio_is_fail_closed_stable() -> None:
    assert canary_bucket("req-nan", math.nan) == "stable"


def test_replay_policy_diff_disable_enable_rollout_modes() -> None:
    samples = [PolicyReplaySample(sample_id="s1", risk=0.55, categories=[])]
    stable = dict(_DEFAULT_POLICY)
    canary = _strict_policy()

    disabled = replay_policy_diff(samples=samples, stable_policy=stable, canary_policy=stable)
    enabled = replay_policy_diff(samples=samples, stable_policy=stable, canary_policy=canary)

    assert disabled["changed"] == 0
    assert enabled["total"] == 1


def test_evaluate_sample_exception_is_fail_closed_deny(monkeypatch) -> None:
    sample = PolicyReplaySample(sample_id="s1", risk=0.1, categories=[])

    def _raise_apply_policy(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("veritas_os.core.fuji._apply_policy", _raise_apply_policy)
    decision = _evaluate_sample(sample, _DEFAULT_POLICY)
    assert decision == "deny"
