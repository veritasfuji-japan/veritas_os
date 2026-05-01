"""Tests for shared bind summary serializer helpers."""

from __future__ import annotations

from veritas_os.api.bind_summary import (
    build_bind_response_payload,
    build_bind_summary_from_receipt,
)


def test_build_bind_summary_from_receipt_includes_shared_vocabulary() -> None:
    """Shared builder should expose canonical bind summary fields."""
    receipt = {
        "bind_receipt_id": "br-1",
        "execution_intent_id": "ei-1",
        "final_outcome": "BLOCKED",
        "target_path": "/v1/governance/policy",
        "target_type": "governance_policy",
        "constraint_check_result": {
            "reason_code": "CONSTRAINT_MISMATCH",
            "reason": "constraint mismatch",
        },
    }

    summary = build_bind_summary_from_receipt(receipt)

    assert summary["bind_outcome"] == "BLOCKED"
    assert summary["bind_reason_code"] == "CONSTRAINT_MISMATCH"
    assert summary["bind_failure_reason"] == "constraint mismatch"
    assert summary["bind_receipt_id"] == "br-1"
    assert summary["execution_intent_id"] == "ei-1"
    assert summary["target_path_type"] == "governance_policy_update"


def test_build_bind_response_payload_keeps_flat_fields_compatible() -> None:
    """Compatibility flat fields should mirror values from bind_summary."""
    receipt = {
        "bind_receipt_id": "br-2",
        "execution_intent_id": "ei-2",
        "final_outcome": "ROLLED_BACK",
        "rollback_reason": "postcondition failed",
        "risk_check_result": {"reason_code": "POST_FAIL"},
    }

    payload = build_bind_response_payload(receipt)
    summary = payload["bind_summary"]

    assert payload["bind_outcome"] == summary["bind_outcome"]
    assert payload["bind_failure_reason"] == summary["bind_failure_reason"]
    assert payload["bind_reason_code"] == summary["bind_reason_code"]
    assert payload["bind_receipt_id"] == summary["bind_receipt_id"]
    assert payload["execution_intent_id"] == summary["execution_intent_id"]


def test_rolled_back_receipt_uses_rollback_reason_for_top_level_reason_fields() -> None:
    """Rolled-back receipts must report rollback cause in top-level reason fields."""
    receipt = {
        "bind_receipt_id": "br-rollback",
        "execution_intent_id": "ei-rollback",
        "final_outcome": "ROLLED_BACK",
        "rollback_reason": "BIND_POSTCONDITION_FAILED",
        "failure_category": "POSTCONDITION",
        "bind_reason_code": "BIND_AUTHORITY_VALID",
        "bind_failure_reason": "Authority remains valid.",
        "authority_check_result": {
            "status": "pass",
            "reason_code": "BIND_AUTHORITY_VALID",
            "message": "Authority remains valid.",
        },
    }

    payload = build_bind_response_payload(receipt)

    assert payload["bind_reason_code"] == "BIND_POSTCONDITION_FAILED"
    assert "Postcondition failed" in (payload["bind_failure_reason"] or "")
    assert "rolled back" in (payload["bind_failure_reason"] or "").lower()
    assert payload["authority_check_result"]["reason_code"] == "BIND_AUTHORITY_VALID"


def test_non_rollback_receipt_keeps_original_top_level_reason_fields() -> None:
    """Non-rollback receipts should continue using explicit top-level reason fields."""
    receipt = {
        "bind_receipt_id": "br-allowed",
        "execution_intent_id": "ei-allowed",
        "final_outcome": "COMMITTED",
        "bind_reason_code": "BIND_AUTHORITY_VALID",
        "bind_failure_reason": "Authority remains valid.",
    }

    payload = build_bind_response_payload(receipt)

    assert payload["bind_reason_code"] == "BIND_AUTHORITY_VALID"
    assert payload["bind_failure_reason"] == "Authority remains valid."
