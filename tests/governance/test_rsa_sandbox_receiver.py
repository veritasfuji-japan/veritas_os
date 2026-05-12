from __future__ import annotations

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
    assert result["veritas_decision"]["final_commit_outcome"] == "SUSPENDED_NOT_COMMITTED"


def test_deferral_engaged_hard_blocks_final_commit() -> None:
    result = evaluate_rsa_sandbox_signal(_payload("DEFERRAL_ENGAGED"))

    assert result["veritas_decision"]["continuation_decision"] == "BLOCK_FINAL_COMMIT"
    assert result["veritas_decision"]["final_commit_outcome"] == "BLOCKED_NOT_COMMITTED"


def test_density_throttled_logs_intervention_without_default_block() -> None:
    result = evaluate_rsa_sandbox_signal(_payload("DENSITY_THROTTLED"))

    assert (
        result["veritas_decision"]["continuation_decision"]
        == "CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED"
    )
    assert result["veritas_decision"]["final_commit_outcome"] == "SUSPENDED_NOT_COMMITTED"


def test_safe_proceed_continues_to_bind_boundary_evaluation() -> None:
    result = evaluate_rsa_sandbox_signal(_payload("SAFE_PROCEED"))

    assert result["veritas_decision"]["continuation_decision"] == "CONTINUE_TO_BIND_BOUNDARY"


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
        result["audit_entry"]["veritas_final_commit_outcome"]
        == result["veritas_decision"]["final_commit_outcome"]
    )


def test_contract_example_matches_expected_output_shape() -> None:
    payload = _payload("ALGORITHMIC_HUMILITY_ENGAGED")

    result = evaluate_rsa_sandbox_signal(payload)

    assert result["veritas_decision"] == {
        "continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
        "reason_code": "UPSTREAM_INCOMPLETE_KYC_CONTEXT",
        "authority_evidence_status": "INSUFFICIENT",
        "bind_boundary_result": "NOT_ADMISSIBLE_PENDING_EVIDENCE",
        "final_commit_outcome": "SUSPENDED_NOT_COMMITTED",
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
        "veritas_final_commit_outcome": "SUSPENDED_NOT_COMMITTED",
    }
