"""Tests for bind receipt replay/revalidation helpers."""

from __future__ import annotations

from veritas_os.policy.bind_artifacts import ExecutionIntent, FinalOutcome
from veritas_os.policy.bind_execution import ReferenceBindAdapter, execute_bind_boundary
from veritas_os.policy.bind_revalidation import revalidate_bind_receipt


def _intent(adapter: ReferenceBindAdapter) -> ExecutionIntent:
    return ExecutionIntent(
        execution_intent_id="ei-revalidate-1",
        decision_id="dec-revalidate-1",
        request_id="req-revalidate-1",
        policy_snapshot_id="policy-revalidate-v1",
        actor_identity="governance_operator",
        target_system="reference",
        target_resource="state",
        intended_action="mutate",
        decision_hash="b" * 64,
        decision_ts="2026-04-22T10:00:00Z",
        expected_state_fingerprint=adapter.fingerprint_state({"version": 1}),
        policy_lineage={
            "governance_identity": {
                "policy_version": "v9",
                "digest": "digest-123",
                "signature_verified": True,
            },
            "bind_adjudication": {
                "drift_required": True,
                "ttl_required": False,
                "approval_freshness_required": False,
                "missing_signal_default": "block",
            },
        },
    )


def test_bind_receipt_revalidation_happy_path() -> None:
    adapter = ReferenceBindAdapter(state={"version": 1}, pending_changes={"version": 2})
    intent = _intent(adapter)

    receipt = execute_bind_boundary(
        execution_intent=intent,
        adapter=adapter,
        bind_ts="2026-04-22T10:01:00Z",
        append_trustlog=False,
    )

    report = revalidate_bind_receipt(receipt=receipt, execution_intent=intent)

    assert report["ok"] is True
    assert report["bind_hash_matches"] is True
    assert report["execution_intent_hash_matches"] is True
    assert report["execution_intent_id_matches"] is True
    assert report["replay"]["admissibility_matches"] is True


def test_bind_revalidation_detects_execution_intent_mismatch() -> None:
    adapter = ReferenceBindAdapter(state={"version": 1}, pending_changes={"version": 2})
    intent = _intent(adapter)
    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter, append_trustlog=False)

    wrong_intent = ExecutionIntent(**{**intent.to_dict(), "execution_intent_id": "ei-other"})
    report = revalidate_bind_receipt(receipt=receipt, execution_intent=wrong_intent)

    assert report["ok"] is False
    assert report["execution_intent_id_matches"] is False


def test_bind_receipt_carries_governance_identity_and_failure_fields() -> None:
    adapter = ReferenceBindAdapter(
        state={"version": 1},
        pending_changes={"version": 2},
        authority_signal=False,
    )
    intent = _intent(adapter)

    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter, append_trustlog=False)

    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert receipt.governance_identity == {
        "policy_version": "v9",
        "digest": "digest-123",
        "signature_verified": True,
    }
    assert receipt.bind_reason_code == "BIND_AUTHORITY_INVALID"
    assert isinstance(receipt.bind_failure_reason, str)
    assert receipt.bind_failure_reason


def test_bind_receipt_backward_compatibility_missing_new_fields() -> None:
    report = revalidate_bind_receipt(
        receipt={
            "bind_receipt_id": "br-legacy",
            "execution_intent_id": "ei-legacy",
            "decision_id": "dec-legacy",
            "bind_ts": "2026-04-22T00:00:00Z",
            "live_state_fingerprint_before": "abc",
            "authority_check_result": {"status": "pass", "reason_code": "", "message": "ok"},
            "constraint_check_result": {"status": "pass", "reason_code": "", "message": "ok"},
            "drift_check_result": {"status": "pass", "reason_code": "", "message": "ok"},
            "risk_check_result": {"status": "pass", "reason_code": "", "message": "ok"},
            "admissibility_result": {
                "admissible": True,
                "recommended_outcome": "commit",
                "reason_codes": [],
            },
            "final_outcome": "COMMITTED",
        }
    )

    assert report["bind_hash_matches"] is True
    assert report["lineage"]["governance_identity_present"] is False
