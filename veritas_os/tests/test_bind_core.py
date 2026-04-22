"""Unit tests for reusable bind-core helpers."""

from __future__ import annotations

from veritas_os.policy.bind_artifacts import FinalOutcome
from veritas_os.policy.bind_core import (
    BIND_OUTCOME_VALUES,
    BindOutcome,
    BindReasonCode,
    normalize_bind_receipt,
    normalize_execution_intent,
)


def test_bind_outcome_values_match_public_final_outcomes() -> None:
    assert BindOutcome.COMMITTED.value == FinalOutcome.COMMITTED.value
    assert FinalOutcome.PRECONDITION_FAILED.value in BIND_OUTCOME_VALUES


def test_normalize_execution_intent_payload_compatibility() -> None:
    intent = normalize_execution_intent(
        {
            "execution_intent_id": "ei-001",
            "decision_id": "dec-001",
            "request_id": "req-001",
            "policy_snapshot_id": "snap-001",
            "actor_identity": "operator",
            "target_system": "governance",
            "target_resource": "/tmp/bundle",
            "intended_action": "promote",
            "evidence_refs": ["a", 2],
            "decision_hash": "h",
            "decision_ts": "2026-04-20T12:00:00Z",
        }
    )
    assert intent.execution_intent_id == "ei-001"
    assert intent.evidence_refs == ["a", "2"]


def test_normalize_bind_receipt_payload_compatibility() -> None:
    receipt = normalize_bind_receipt(
        {
            "bind_receipt_id": "br-001",
            "execution_intent_id": "ei-001",
            "decision_id": "dec-001",
            "bind_ts": "2026-04-20T12:00:10Z",
            "final_outcome": "BLOCKED",
            "admissibility_result": {"reason_codes": [BindReasonCode.SNAPSHOT_FAILED.value]},
        }
    )
    assert receipt.bind_receipt_id == "br-001"
    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert receipt.retry_safety is None
    assert receipt.failure_category is None
