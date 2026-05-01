"""Dry-run evaluator tests for governance observation semantic consistency."""

from __future__ import annotations

import json
from pathlib import Path

from veritas_os.api.schemas import GovernanceObservation
from veritas_os.governance.observation_evaluator import evaluate_governance_observation


def _base_observation(**overrides: object) -> GovernanceObservation:
    payload = {
        "policy_mode": "observe",
        "environment": "development",
        "would_have_blocked": True,
        "would_have_blocked_reason": "policy_violation:missing_authority_evidence",
        "effective_outcome": "proceed",
        "observed_outcome": "block",
        "operator_warning": True,
        "audit_required": True,
    }
    payload.update(overrides)
    return GovernanceObservation(**payload)


def _codes(result: object) -> set[str]:
    return {issue.code for issue in result.issues}


def test_production_observe_is_invalid() -> None:
    result = evaluate_governance_observation(
        _base_observation(environment="production", policy_mode="observe")
    )
    assert result.valid is False
    assert "OBSERVE_MODE_NOT_ALLOWED_IN_PRODUCTION" in _codes(result)


def test_observe_requires_audit() -> None:
    result = evaluate_governance_observation(
        _base_observation(policy_mode="observe", audit_required=False)
    )
    assert result.valid is False
    assert "OBSERVE_MODE_REQUIRES_AUDIT" in _codes(result)


def test_observe_requires_operator_warning() -> None:
    result = evaluate_governance_observation(
        _base_observation(policy_mode="observe", operator_warning=False)
    )
    assert result.valid is False
    assert "OBSERVE_MODE_REQUIRES_OPERATOR_WARNING" in _codes(result)


def test_would_have_blocked_requires_reason() -> None:
    result = evaluate_governance_observation(
        _base_observation(would_have_blocked=True, would_have_blocked_reason="")
    )
    assert result.valid is False
    assert "WOULD_HAVE_BLOCKED_REQUIRES_REASON" in _codes(result)


def test_would_have_blocked_requires_observed_outcome() -> None:
    result = evaluate_governance_observation(
        _base_observation(would_have_blocked=True, observed_outcome=None)
    )
    assert result.valid is False
    assert "WOULD_HAVE_BLOCKED_REQUIRES_OBSERVED_OUTCOME" in _codes(result)


def test_enforce_cannot_proceed_when_would_have_blocked() -> None:
    result = evaluate_governance_observation(
        _base_observation(
            policy_mode="enforce",
            would_have_blocked=True,
            effective_outcome="proceed",
            observed_outcome="block",
        )
    )
    assert result.valid is False
    assert "ENFORCE_MODE_CANNOT_PROCEED_WHEN_BLOCKED" in _codes(result)


def test_off_mode_requires_audit() -> None:
    result = evaluate_governance_observation(
        _base_observation(
            policy_mode="off",
            would_have_blocked=False,
            audit_required=False,
            effective_outcome="proceed",
            observed_outcome=None,
        )
    )
    assert result.valid is False
    assert "OFF_MODE_REQUIRES_AUDIT" in _codes(result)


def test_current_sample_fixture_is_semantically_valid() -> None:
    fixture_path = Path("fixtures/governance_observation_live_snapshot.json")
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    observation = GovernanceObservation(
        **data["governance_layer_snapshot"]["governance_observation"]
    )

    result = evaluate_governance_observation(observation)

    assert result.valid is True
    assert result.issues == ()
