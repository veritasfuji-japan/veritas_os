from __future__ import annotations

import pytest

from veritas_os.governance import RSASandboxPayload as ExportedRSASandboxPayload
from veritas_os.governance import evaluate_rsa_sandbox_signal as exported_evaluator
from veritas_os.governance.rsa_sandbox_receiver import (
    RSASandboxPayload,
    evaluate_rsa_sandbox_signal,
)


def _payload(status: str) -> RSASandboxPayload:
    return RSASandboxPayload(
        rsa_status=status,
        trigger_source="SRC_Incomplete_Context",
        original_llm_intent="Recommend_Transaction_Approval",
        rsa_action_taken="Execution_Suspended_Awaiting_Reality_Sync",
        timestamp="2026-05-11T11:25:44.008Z",
    )


def test_algorithmic_humility_pauses_human_review_without_hard_block() -> None:
    result = evaluate_rsa_sandbox_signal(_payload("ALGORITHMIC_HUMILITY_ENGAGED"))

    assert result["veritas_decision"]["continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"
    assert result["veritas_decision"]["sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
    assert (
        result["audit_entry"]["veritas_reason"]
        == "The workflow cannot continue toward final commit because required "
        "KYC context is incomplete and authority evidence is insufficient."
    )


def test_deferral_engaged_hard_blocks_final_commit() -> None:
    result = evaluate_rsa_sandbox_signal(_payload("DEFERRAL_ENGAGED"))

    assert result["veritas_decision"]["continuation_decision"] == "BLOCK_FINAL_COMMIT"
    assert result["veritas_decision"]["reason_code"] == "UPSTREAM_CRITICAL_DEFERRAL_SIGNAL"
    assert result["veritas_decision"]["sandbox_commit_state"] == "BLOCKED_NOT_COMMITTED"
    assert (
        result["audit_entry"]["veritas_reason"]
        == "RSA reported a critical upstream deferral condition; VERITAS "
        "blocks final commit until human review or policy remediation occurs."
    )


def test_density_throttled_logs_intervention_without_default_block() -> None:
    result = evaluate_rsa_sandbox_signal(_payload("DENSITY_THROTTLED"))

    assert (
        result["veritas_decision"]["continuation_decision"]
        == "CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED"
    )
    assert (
        result["veritas_decision"]["reason_code"]
        == "UPSTREAM_INTERVENTION_DENSITY_THROTTLE"
    )
    assert result["veritas_decision"]["sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
    assert (
        result["audit_entry"]["veritas_reason"]
        == "RSA modified the upstream output for cognitive density control; "
        "VERITAS records the intervention without treating it as a default "
        "hard block."
    )


def test_safe_proceed_continues_to_bind_boundary_evaluation() -> None:
    payload = _payload("SAFE_PROCEED")
    result = evaluate_rsa_sandbox_signal(payload)

    assert result["veritas_decision"]["continuation_decision"] == "CONTINUE_TO_BIND_BOUNDARY"
    assert result["veritas_decision"]["reason_code"] == "UPSTREAM_SAFE_PROCEED_SIGNAL"
    assert result["veritas_decision"]["sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
    assert (
        result["veritas_decision"]["sandbox_bind_boundary_state"]
        == "NOT_EVALUATED_PENDING_AUTHORITY_EVIDENCE"
    )
    assert result["audit_entry"]["upstream_signal_source"] == "RSA"
    assert result["audit_entry"]["rsa_status"] == payload.rsa_status
    assert result["audit_entry"]["trigger_source"] == payload.trigger_source
    assert (
        result["audit_entry"]["veritas_reason"]
        == "The upstream RSA signal indicates the workflow may continue "
        "toward normal bind-boundary evaluation."
    )


def test_audit_entry_preserves_upstream_and_downstream_decision() -> None:
    payload = _payload("ALGORITHMIC_HUMILITY_ENGAGED")

    result = evaluate_rsa_sandbox_signal(payload)

    assert result["audit_entry"]["upstream_signal_source"] == "RSA"
    assert result["audit_entry"]["rsa_status"] == payload.rsa_status
    assert (
        result["audit_entry"]["veritas_continuation_decision"]
        == result["veritas_decision"]["continuation_decision"]
    )
    assert (
        result["audit_entry"]["veritas_sandbox_commit_state"]
        == result["veritas_decision"]["sandbox_commit_state"]
    )


def test_contract_example_matches_expected_output_shape() -> None:
    payload = _payload("ALGORITHMIC_HUMILITY_ENGAGED")

    result = evaluate_rsa_sandbox_signal(payload)

    assert result["veritas_decision"] == {
        "continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
        "reason_code": "UPSTREAM_INCOMPLETE_KYC_CONTEXT",
        "authority_evidence_status": "INSUFFICIENT",
        "sandbox_bind_boundary_state": "NOT_EVALUATED_PENDING_AUTHORITY_EVIDENCE",
        "sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
        "required_next_action": "REQUEST_ADDITIONAL_KYC_EVIDENCE_OR_HUMAN_REVIEW",
    }
    assert result["audit_entry"] == {
        "upstream_signal_source": "RSA",
        "rsa_status": "ALGORITHMIC_HUMILITY_ENGAGED",
        "trigger_source": "SRC_Incomplete_Context",
        "original_llm_intent": "Recommend_Transaction_Approval",
        "rsa_action_taken": "Execution_Suspended_Awaiting_Reality_Sync",
        "veritas_reason": (
            "The workflow cannot continue toward final commit because required "
            "KYC context is incomplete and authority evidence is insufficient."
        ),
        "timestamp": "2026-05-11T11:25:44.008Z",
        "veritas_continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
        "veritas_sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
    }


def test_public_exports_support_safe_proceed_evaluation() -> None:
    payload = ExportedRSASandboxPayload(
        rsa_status="SAFE_PROCEED",
        trigger_source="SRC_Incomplete_Context",
        original_llm_intent="Recommend_Transaction_Approval",
        rsa_action_taken="Execution_Suspended_Awaiting_Reality_Sync",
        timestamp="2026-05-11T11:25:44.008Z",
    )

    result = exported_evaluator(payload)

    assert result["veritas_decision"]["continuation_decision"] == "CONTINUE_TO_BIND_BOUNDARY"


def test_unknown_status_raises_contract_violation() -> None:
    payload = _payload("UNKNOWN_STATUS")

    with pytest.raises(ValueError, match="Unknown RSA sandbox status: UNKNOWN_STATUS") as exc_info:
        evaluate_rsa_sandbox_signal(payload)
    message = str(exc_info.value)

    assert "Unknown RSA sandbox status: UNKNOWN_STATUS" in message
    assert "Supported:" in message
    assert "SAFE_PROCEED" in message
    assert "DENSITY_THROTTLED" in message
    assert "ALGORITHMIC_HUMILITY_ENGAGED" in message
    assert "DEFERRAL_ENGAGED" in message


def test_legacy_bind_boundary_field_is_not_present() -> None:
    result = evaluate_rsa_sandbox_signal(_payload("SAFE_PROCEED"))

    assert "bind_boundary_result" not in result["veritas_decision"]


def test_empty_trigger_source_raises_validation_error() -> None:
    payload = RSASandboxPayload(
        rsa_status="SAFE_PROCEED",
        trigger_source="",
        original_llm_intent="Recommend_Transaction_Approval",
        rsa_action_taken="Execution_Suspended_Awaiting_Reality_Sync",
        timestamp="2026-05-11T11:25:44.008Z",
    )

    with pytest.raises(
        ValueError,
        match="RSASandboxPayload.trigger_source must be a non-empty string",
    ):
        evaluate_rsa_sandbox_signal(payload)


def test_whitespace_original_llm_intent_raises_validation_error() -> None:
    payload = RSASandboxPayload(
        rsa_status="SAFE_PROCEED",
        trigger_source="SRC_Incomplete_Context",
        original_llm_intent="   ",
        rsa_action_taken="Execution_Suspended_Awaiting_Reality_Sync",
        timestamp="2026-05-11T11:25:44.008Z",
    )

    with pytest.raises(
        ValueError,
        match="RSASandboxPayload.original_llm_intent must be a non-empty string",
    ):
        evaluate_rsa_sandbox_signal(payload)


def test_non_string_rsa_action_taken_raises_validation_error() -> None:
    payload = RSASandboxPayload(
        rsa_status="SAFE_PROCEED",
        trigger_source="SRC_Incomplete_Context",
        original_llm_intent="Recommend_Transaction_Approval",
        rsa_action_taken=123,  # type: ignore[arg-type]
        timestamp="2026-05-11T11:25:44.008Z",
    )

    with pytest.raises(
        ValueError,
        match="RSASandboxPayload.rsa_action_taken must be a non-empty string",
    ):
        evaluate_rsa_sandbox_signal(payload)


def test_invalid_timestamp_raises_validation_error() -> None:
    payload = RSASandboxPayload(
        rsa_status="SAFE_PROCEED",
        trigger_source="SRC_Incomplete_Context",
        original_llm_intent="Recommend_Transaction_Approval",
        rsa_action_taken="Execution_Suspended_Awaiting_Reality_Sync",
        timestamp="not-a-timestamp",
    )

    with pytest.raises(
        ValueError,
        match="RSASandboxPayload.timestamp must be ISO-8601 compatible",
    ):
        evaluate_rsa_sandbox_signal(payload)


def test_timestamp_with_trailing_z_is_accepted() -> None:
    payload = _payload("SAFE_PROCEED")

    result = evaluate_rsa_sandbox_signal(payload)

    assert result["audit_entry"]["timestamp"] == "2026-05-11T11:25:44.008Z"
