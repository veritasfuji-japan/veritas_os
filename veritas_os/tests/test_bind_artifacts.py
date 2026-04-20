"""Schema-first tests for bind-boundary governance artifacts."""

from __future__ import annotations

from veritas_os.api.schemas import BindReceipt as ApiBindReceipt
from veritas_os.api.schemas import DecideResponse
from veritas_os.api.schemas import ExecutionIntent as ApiExecutionIntent
from veritas_os.policy.bind_artifacts import BindReceipt, ExecutionIntent, FinalOutcome
from veritas_os.policy.bind_artifacts import canonical_bind_receipt_json
from veritas_os.policy.bind_artifacts import canonical_execution_intent_json
from veritas_os.policy.bind_artifacts import hash_bind_receipt, hash_execution_intent


def test_execution_intent_model_creation() -> None:
    """ExecutionIntent should accept minimum decision-linked fields."""
    intent = ExecutionIntent(
        decision_id="dec-001",
        request_id="req-001",
        policy_snapshot_id="policy-v1",
        actor_identity="mission-control-operator",
        target_system="kubernetes",
        target_resource="deployment/api",
        intended_action="apply_patch",
        evidence_refs=["ev-1", "ev-2"],
        decision_hash="a" * 64,
        decision_ts="2026-04-20T12:00:00Z",
    )

    assert intent.execution_intent_id
    assert intent.policy_snapshot_id == "policy-v1"
    assert intent.actor_identity == "mission-control-operator"


def test_bind_receipt_model_creation() -> None:
    """BindReceipt should capture bind-time checks and lineage references."""
    receipt = BindReceipt(
        execution_intent_id="ei-001",
        decision_id="dec-001",
        live_state_fingerprint_before="fp-before",
        live_state_fingerprint_after="fp-after",
        authority_check_result={"ok": True},
        constraint_check_result={"ok": True},
        drift_check_result={"ok": True},
        risk_check_result={"ok": True},
        admissibility_result={"ok": True},
        final_outcome=FinalOutcome.COMMITTED,
        trustlog_hash="b" * 64,
        prev_bind_hash="c" * 64,
    )

    assert receipt.bind_receipt_id
    assert receipt.final_outcome is FinalOutcome.COMMITTED
    assert receipt.prev_bind_hash == "c" * 64


def test_final_outcome_enum_serialization() -> None:
    """Enum should serialize to canonical uppercase contract values."""
    receipt = BindReceipt(
        execution_intent_id="ei-001",
        decision_id="dec-001",
        final_outcome=FinalOutcome.ESCALATED,
    )

    payload = receipt.to_dict()
    assert payload["final_outcome"] == "ESCALATED"


def test_deterministic_serialization_stability() -> None:
    """Canonical JSON serialization should be deterministic for same payload."""
    intent_a = ExecutionIntent(
        execution_intent_id="ei-fixed",
        decision_id="dec-001",
        request_id="req-001",
        policy_snapshot_id="policy-v1",
        actor_identity="actor",
        target_system="system",
        target_resource="resource",
        intended_action="action",
        evidence_refs=["ev-1"],
        decision_hash="d" * 64,
        decision_ts="2026-04-20T00:00:00Z",
    )
    intent_b = ExecutionIntent(
        execution_intent_id="ei-fixed",
        decision_id="dec-001",
        request_id="req-001",
        policy_snapshot_id="policy-v1",
        actor_identity="actor",
        target_system="system",
        target_resource="resource",
        intended_action="action",
        evidence_refs=["ev-1"],
        decision_hash="d" * 64,
        decision_ts="2026-04-20T00:00:00Z",
    )

    assert canonical_execution_intent_json(intent_a) == canonical_execution_intent_json(intent_b)


def test_hashing_stability_for_bind_receipt() -> None:
    """Hashing should remain stable when canonical payload is identical."""
    receipt_a = BindReceipt(
        bind_receipt_id="br-fixed",
        execution_intent_id="ei-001",
        decision_id="dec-001",
        bind_ts="2026-04-20T00:00:00Z",
        final_outcome=FinalOutcome.BLOCKED,
        trustlog_hash="e" * 64,
    )
    receipt_b = BindReceipt(
        bind_receipt_id="br-fixed",
        execution_intent_id="ei-001",
        decision_id="dec-001",
        bind_ts="2026-04-20T00:00:00Z",
        final_outcome=FinalOutcome.BLOCKED,
        trustlog_hash="e" * 64,
    )

    assert canonical_bind_receipt_json(receipt_a) == canonical_bind_receipt_json(receipt_b)
    assert hash_bind_receipt(receipt_a) == hash_bind_receipt(receipt_b)
    assert hash_execution_intent(
        ExecutionIntent(
            execution_intent_id="ei-fixed",
            decision_id="dec-001",
            request_id="req-001",
            policy_snapshot_id="policy-v1",
            actor_identity="actor",
            target_system="system",
            target_resource="resource",
            intended_action="action",
            evidence_refs=["ev-1"],
            decision_hash="f" * 64,
            decision_ts="2026-04-20T00:00:00Z",
        )
    ) == hash_execution_intent(
        ExecutionIntent(
            execution_intent_id="ei-fixed",
            decision_id="dec-001",
            request_id="req-001",
            policy_snapshot_id="policy-v1",
            actor_identity="actor",
            target_system="system",
            target_resource="resource",
            intended_action="action",
            evidence_refs=["ev-1"],
            decision_hash="f" * 64,
            decision_ts="2026-04-20T00:00:00Z",
        )
    )


def test_backward_compatibility_existing_decide_response_unchanged() -> None:
    """Existing decision artifact shape must remain usable without bind artifacts."""
    resp = DecideResponse(request_id="req-compat")
    assert resp.request_id == "req-compat"

    api_intent = ApiExecutionIntent(decision_id="dec-001", request_id="req-001")
    api_receipt = ApiBindReceipt(execution_intent_id="ei-001", decision_id="dec-001")
    assert api_intent.decision_id == "dec-001"
    assert api_receipt.decision_id == "dec-001"
