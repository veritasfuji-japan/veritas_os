from __future__ import annotations

from examples.sandbox.rsa_veritas_e2e_harness import run_rsa_veritas_e2e_harness


def test_rsa_veritas_e2e_harness_returns_expected_sandbox_contract() -> None:
    result = run_rsa_veritas_e2e_harness()

    assert result["veritas_decision"]["continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"
    assert result["veritas_decision"]["reason_code"] == "UPSTREAM_INCOMPLETE_KYC_CONTEXT"
    assert result["veritas_decision"]["sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
    assert result["audit_entry"]["original_llm_intent"] == "[REDACTED]"
    assert result["audit_entry"]["rsa_action_taken"] == "[REDACTED]"
    assert result["audit_entry"]["timestamp"] == "2026-10-25T09:15:30Z"
    assert result["audit_entry"]["veritas_continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"
    assert result["audit_entry"]["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
