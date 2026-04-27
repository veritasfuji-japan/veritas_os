"""Tests for additive regulated-action fields in bind receipts and summaries."""

from __future__ import annotations

import pytest

from veritas_os.api.bind_summary import build_bind_response_payload, build_bind_summary_from_receipt
from veritas_os.governance.authority_evidence import VerificationResult
from veritas_os.governance.commit_boundary import CommitBoundaryResult
from veritas_os.policy.bind_core.core import (
    ReferenceBindAdapter,
    execute_bind_adjudication,
)
from veritas_os.policy.bind_core.normalizers import normalize_bind_receipt


def _regulated_context() -> dict[str, object]:
    return {
        "regulated_action_path_id": "rap-001",
        "action_class": "customer_risk_escalation",
        "requested_scope": ["customer:risk_escalation"],
        "action_contract_id": "aml_kyc_customer_risk_escalation",
        "action_contract": {
            "id": "aml_kyc_customer_risk_escalation",
            "version": "1.0.0",
            "domain": "aml",
            "action_class": "customer_risk_escalation",
            "description": "Escalate suspicious customer risk for review.",
            "declared_intent": "Escalate suspicious customer risk for review.",
            "allowed_scope": ["customer:risk_escalation"],
            "prohibited_scope": ["account:freeze"],
            "authority_sources": ["policy.register.aml"],
            "required_evidence": ["kyc_status"],
            "evidence_freshness": {"kyc_status": "P30D"},
            "irreversibility": {"boundary": "escalation_dispatch", "level": "medium"},
            "human_approval_rules": {"minimum_approvals": 0},
            "refusal_conditions": [],
            "escalation_conditions": ["stale_evidence"],
            "default_failure_mode": "fail_closed",
            "metadata": {"regulated": True},
        },
        "authority_evidence": {
            "authority_evidence_id": "aev-001",
            "action_contract_id": "aml_kyc_customer_risk_escalation",
            "action_contract_version": "1.0.0",
            "actor_identity": "operator:alice",
            "actor_role": "aml_reviewer",
            "authority_source_refs": ["policy.register.aml"],
            "role_or_policy_basis": ["role:aml_reviewer"],
            "scope_grants": ["customer:risk_escalation"],
            "scope_limitations": ["account:freeze"],
            "validity_window": {
                "issued_at": "2026-04-25T00:00:00",
                "valid_from": "2026-04-25T00:00:00",
                "valid_until": "2026-04-30T00:00:00",
            },
            "issued_at": "2026-04-25T00:00:00",
            "valid_from": "2026-04-25T00:00:00",
            "valid_until": "2026-04-30T00:00:00",
            "revalidated_at": "2026-04-26T00:00:00",
            "policy_snapshot_id": "policy-snapshot-001",
            "evidence_hash": "hash-001",
            "verification_result": VerificationResult.VALID.value,
            "failure_reasons": [],
            "metadata": {"issuer": "governance-control-plane"},
        },
        "required_evidence_metadata": {"kyc_status": {"present": True}},
        "evidence_freshness_metadata": {"kyc_status": {"fresh": True}},
        "human_approval_state": {"approved": True},
        "bind_context_metadata": {"session_id": "bind-001"},
    }


def _intent_with_regulated_context() -> dict[str, object]:
    return {
        "execution_intent_id": "ei-regulated-001",
        "decision_id": "dec-regulated-001",
        "policy_snapshot_id": "policy-snapshot-001",
        "actor_identity": "operator:alice",
        "target_system": "governance",
        "target_resource": "/v1/governance/policy",
        "intended_action": "escalate",
        "decision_ts": "2026-04-26T00:00:00Z",
        "policy_lineage": {"bind_adjudication": {"drift_required": False}},
        "approval_context": {
            "regulated_action_governance": _regulated_context(),
        },
    }


def _run_bind(intent: dict[str, object], adapter: ReferenceBindAdapter | None = None):
    return execute_bind_adjudication(
        execution_intent=intent,
        adapter=adapter
        or ReferenceBindAdapter(state={"mode": "safe"}, pending_changes={"mode": "strict"}),
        append_trustlog=False,
    )


def test_legacy_bind_receipt_deserializes_without_new_fields() -> None:
    legacy = {
        "bind_receipt_id": "br-legacy",
        "execution_intent_id": "ei-legacy",
        "decision_id": "dec-legacy",
        "bind_ts": "2026-04-26T00:00:00Z",
        "final_outcome": "COMMITTED",
    }

    normalized = normalize_bind_receipt(legacy)
    payload = normalized.to_dict()

    assert normalized.bind_receipt_id == "br-legacy"
    assert "action_contract_id" not in payload


def test_legacy_bind_summary_deserializes_without_new_fields() -> None:
    summary = build_bind_summary_from_receipt(
        {"bind_receipt_id": "br-old", "execution_intent_id": "ei-old", "final_outcome": "COMMITTED"}
    )

    assert summary["bind_outcome"] == "COMMITTED"
    assert summary.get("commit_boundary_result") is None


def test_evaluator_execution_includes_action_contract_id() -> None:
    receipt = _run_bind(_intent_with_regulated_context())
    assert receipt.action_contract_id == "aml_kyc_customer_risk_escalation"


def test_evaluator_execution_includes_authority_evidence_hash() -> None:
    receipt = _run_bind(_intent_with_regulated_context())
    assert receipt.authority_evidence_hash == "hash-001"


def test_bind_summary_includes_compact_commit_boundary_result() -> None:
    receipt = _run_bind(_intent_with_regulated_context())
    summary = build_bind_summary_from_receipt(receipt.to_dict())
    assert summary["commit_boundary_result"] == "commit"


def test_blocked_path_includes_failed_predicates(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_eval(**_: object) -> CommitBoundaryResult:
        return CommitBoundaryResult(
            commit_boundary_result="block",
            action_contract_id="contract-1",
            action_contract_version="1.0.0",
            authority_evidence_id="aev-1",
            authority_evidence_hash="hash-1",
            authority_validation_status="fail",
            failed_predicates=[{
                "predicate_id": "p-failed",
                "predicate_type": "authority_valid",
                "status": "fail",
                "reason": "authority_invalid",
            }],
            reason_summary="blocked",
        )

    monkeypatch.setattr("veritas_os.policy.bind_core.core.evaluate_commit_boundary", _fake_eval)
    receipt = _run_bind(_intent_with_regulated_context())
    assert receipt.final_outcome.value == "BLOCKED"
    assert isinstance(receipt.failed_predicates, list)


def test_escalated_path_includes_escalation_basis(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_eval(**_: object) -> CommitBoundaryResult:
        return CommitBoundaryResult(
            commit_boundary_result="escalate",
            action_contract_id="contract-1",
            action_contract_version="1.0.0",
            authority_evidence_id="aev-1",
            authority_evidence_hash="hash-1",
            authority_validation_status="fail",
            escalation_basis=["manual_review_required"],
            reason_summary="escalated",
        )

    monkeypatch.setattr("veritas_os.policy.bind_core.core.evaluate_commit_boundary", _fake_eval)
    receipt = _run_bind(_intent_with_regulated_context())
    assert receipt.final_outcome.value == "ESCALATED"
    assert receipt.escalation_basis == ["manual_review_required"]


def test_refused_path_includes_refusal_basis(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_eval(**_: object) -> CommitBoundaryResult:
        return CommitBoundaryResult(
            commit_boundary_result="refuse",
            action_contract_id="contract-1",
            action_contract_version="1.0.0",
            authority_evidence_id="aev-1",
            authority_evidence_hash="hash-1",
            authority_validation_status="fail",
            refusal_basis=["authority_indeterminate"],
            reason_summary="refused",
        )

    monkeypatch.setattr("veritas_os.policy.bind_core.core.evaluate_commit_boundary", _fake_eval)
    receipt = _run_bind(_intent_with_regulated_context())
    assert receipt.final_outcome.value == "BLOCKED"
    assert receipt.refusal_basis == ["authority_indeterminate"]


def test_evaluator_exception_does_not_silent_commit() -> None:
    bad_intent = _intent_with_regulated_context()
    regulated = bad_intent["approval_context"]["regulated_action_governance"]
    regulated["action_contract"] = {"id": "broken"}

    with pytest.raises(RuntimeError, match="BIND_COMMIT_BOUNDARY_EVALUATION_FAILED"):
        _run_bind(bad_intent)


def test_commit_boundary_serialization_error_does_not_silent_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = ReferenceBindAdapter(state={"mode": "safe"}, pending_changes={"mode": "strict"})
    intent = _intent_with_regulated_context()

    def _raise_serialization_error(*_: object, **__: object) -> dict[str, object]:
        raise TypeError("cannot serialize predicate metadata")

    monkeypatch.setattr(
        "veritas_os.policy.bind_core.core._regulated_receipt_updates",
        _raise_serialization_error,
    )

    with pytest.raises(RuntimeError, match="BIND_COMMIT_BOUNDARY_SERIALIZATION_FAILED"):
        _run_bind(intent, adapter=adapter)

    assert adapter.state["mode"] == "safe"


def test_export_payload_remains_backward_compatible() -> None:
    payload = build_bind_response_payload(
        {
            "bind_receipt_id": "br-export-1",
            "execution_intent_id": "ei-export-1",
            "final_outcome": "COMMITTED",
        }
    )
    assert payload["bind_receipt_id"] == "br-export-1"
    assert payload["execution_intent_id"] == "ei-export-1"
    assert "bind_summary" in payload
