# -*- coding: utf-8 -*-
"""Focused tests for deterministic fail-closed bind-time admissibility."""

from veritas_os.core.continuation_runtime.bind_admissibility import (
    AdmissibilityOutcome,
    BindAdmissibilityInput,
    CheckStatus,
    evaluate_bind_admissibility,
)


def _base_input(**overrides) -> BindAdmissibilityInput:
    payload = {
        "execution_intent": "bind:commit_order",
        "current_timestamp": "2026-04-20T10:00:00+00:00",
        "authority_signal": True,
        "constraint_signals": {"region_allowed": True, "policy_current": True},
        "live_state_fingerprint": "abc123",
        "expected_state_fingerprint": "abc123",
        "runtime_risk_signal": True,
        "drift_sensitive": True,
        "ttl_expires_at": "2026-04-20T10:30:00+00:00",
        "approval_expires_at": "2026-04-20T10:15:00+00:00",
    }
    payload.update(overrides)
    return BindAdmissibilityInput(**payload)


def test_all_checks_pass_is_eligible_to_commit() -> None:
    result = evaluate_bind_admissibility(_base_input())

    assert result.admissibility_result is True
    assert result.recommended_outcome is AdmissibilityOutcome.ELIGIBLE_TO_COMMIT
    assert result.reason_codes == []


def test_authority_failure_fails_closed() -> None:
    result = evaluate_bind_admissibility(_base_input(authority_signal=False))

    assert result.admissibility_result is False
    assert result.authority_check_result.status is CheckStatus.FAIL
    assert result.recommended_outcome is AdmissibilityOutcome.BLOCK


def test_constraint_failure_fails_closed() -> None:
    result = evaluate_bind_admissibility(
        _base_input(constraint_signals={"region_allowed": False, "policy_current": True})
    )

    assert result.admissibility_result is False
    assert result.constraint_check_result.status is CheckStatus.FAIL
    assert result.recommended_outcome is AdmissibilityOutcome.BLOCK


def test_drift_detected_blocks() -> None:
    result = evaluate_bind_admissibility(
        _base_input(live_state_fingerprint="live999", expected_state_fingerprint="exp111")
    )

    assert result.admissibility_result is False
    assert result.drift_check_result.status is CheckStatus.FAIL
    assert result.recommended_outcome is AdmissibilityOutcome.BLOCK


def test_runtime_risk_failure_fails_closed() -> None:
    result = evaluate_bind_admissibility(_base_input(runtime_risk_signal=False))

    assert result.admissibility_result is False
    assert result.risk_check_result.status is CheckStatus.FAIL
    assert result.recommended_outcome is AdmissibilityOutcome.BLOCK


def test_missing_authority_signal_fails_closed() -> None:
    result = evaluate_bind_admissibility(_base_input(authority_signal=None))

    assert result.admissibility_result is False
    assert result.authority_check_result.reason_code == "BIND_AUTHORITY_MISSING"
    assert result.recommended_outcome is AdmissibilityOutcome.BLOCK


def test_missing_constraint_signal_fails_closed() -> None:
    result = evaluate_bind_admissibility(_base_input(constraint_signals=None))

    assert result.admissibility_result is False
    assert result.constraint_check_result.reason_code == "BIND_CONSTRAINTS_MISSING"
    assert result.recommended_outcome is AdmissibilityOutcome.BLOCK


def test_missing_runtime_state_on_drift_sensitive_path_fails_closed() -> None:
    result = evaluate_bind_admissibility(_base_input(live_state_fingerprint=None))

    assert result.admissibility_result is False
    assert result.drift_check_result.reason_code == "BIND_DRIFT_SIGNAL_MISSING"
    assert result.recommended_outcome is AdmissibilityOutcome.BLOCK


def test_expired_ttl_escalates_fail_closed() -> None:
    result = evaluate_bind_admissibility(
        _base_input(
            current_timestamp="2026-04-20T10:00:01+00:00",
            ttl_expires_at="2026-04-20T10:00:00+00:00",
        )
    )

    assert result.admissibility_result is False
    assert result.freshness_check_result.status is CheckStatus.ESCALATE
    assert result.recommended_outcome is AdmissibilityOutcome.ESCALATE


def test_deterministic_output_stability_for_same_inputs() -> None:
    bind_input = _base_input()

    result1 = evaluate_bind_admissibility(bind_input)
    result2 = evaluate_bind_admissibility(bind_input)

    assert result1 == result2
