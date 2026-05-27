"""Tests for local/offline Human Approval Receipt v1 helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.governance.authority_evidence import AuthorityEvidence, VerificationResult
from veritas_os.governance.human_approval_receipt import (
    HumanApprovalReceipt,
    build_human_approval_state,
    validate_human_approval_receipt,
    with_receipt_hash,
)
from veritas_os.governance.runtime_authority import RuntimeAuthorityValidator


def _receipt(**overrides: object) -> HumanApprovalReceipt:
    payload = {
        "approval_receipt_id": "har-001",
        "decision_id": "decision-001",
        "execution_intent_id": "intent-001",
        "approver_identity": "operator:approver-1",
        "approver_role": "risk_manager",
        "approved_action_class": "wire_transfer",
        "approved_scope": ["ledger:debit", "ledger:credit"],
        "approval_basis_refs": ["policy:wire:v1"],
        "approved_at": "2026-05-01T00:00:00+00:00",
        "expires_at": "2026-06-01T00:00:00+00:00",
        "policy_snapshot_id": "policy-001",
        "authority_evidence_id": "aev-001",
        "approval_result": "approved",
        "signature_verified": True,
        "receipt_hash": "",
        "metadata": {"note": "offline"},
    }
    payload.update(overrides)
    return HumanApprovalReceipt(**payload)


def _contract(**overrides: object) -> ActionClassContract:
    payload = {
        "id": "wire_transfer",
        "version": "1.0.0",
        "domain": "payments",
        "action_class": "wire_transfer",
        "description": "Wire transfer action.",
        "declared_intent": "Perform regulated wire transfer.",
        "allowed_scope": ["ledger:debit", "ledger:credit"],
        "prohibited_scope": ["ledger:mint"],
        "authority_sources": ["policy.payments"],
        "required_evidence": ["kyc_status"],
        "evidence_freshness": {"kyc_status": "P1D"},
        "irreversibility": {"boundary": "funds_settled", "level": "high"},
        "human_approval_rules": {"minimum_approvals": 1},
        "refusal_conditions": [],
        "escalation_conditions": [],
        "default_failure_mode": "fail_closed",
        "metadata": {},
    }
    payload.update(overrides)
    return ActionClassContract(**payload)


def _authority() -> AuthorityEvidence:
    return AuthorityEvidence(
        authority_evidence_id="aev-001",
        action_contract_id="wire_transfer",
        action_contract_version="1.0.0",
        actor_identity="operator:alice",
        actor_role="payments_operator",
        authority_source_refs=["policy.payments"],
        role_or_policy_basis=["role:payments_operator"],
        scope_grants=["ledger:debit", "ledger:credit"],
        scope_limitations=["ledger:mint"],
        validity_window={
            "issued_at": "2026-05-01T00:00:00+00:00",
            "valid_from": "2026-05-01T00:00:00+00:00",
            "valid_until": "2026-06-15T00:00:00+00:00",
        },
        issued_at="2026-05-01T00:00:00+00:00",
        valid_from="2026-05-01T00:00:00+00:00",
        valid_until="2026-06-15T00:00:00+00:00",
        revalidated_at=None,
        policy_snapshot_id="policy-001",
        evidence_hash="",
        verification_result=VerificationResult.VALID,
        failure_reasons=[],
        metadata={},
    )


def test_valid_receipt_produces_deterministic_receipt_hash() -> None:
    one = _receipt(metadata={"k": "v"})
    two = _receipt(metadata={"k": "v"})

    assert one.deterministic_digest() == two.deterministic_digest()


def test_valid_receipt_builds_approved_human_approval_state() -> None:
    state = build_human_approval_state(
        _receipt(),
        requested_scope=["ledger:debit"],
        action_class="wire_transfer",
        policy_snapshot_id="policy-001",
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert state["approved"] is True
    assert state["approval_receipt_id"] == "har-001"


def test_missing_receipt_builds_not_approved_state() -> None:
    state = build_human_approval_state(None, requested_scope=["ledger:debit"])

    assert state == {"approved": False, "failure_reasons": ["human_approval_missing"]}


def test_denied_receipt_fails_validation() -> None:
    result = validate_human_approval_receipt(
        _receipt(approval_result="denied"),
        requested_scope=["ledger:debit"],
    )

    assert result.is_valid is False
    assert "human_approval_not_approved" in result.failure_reasons


def test_expired_receipt_fails_validation() -> None:
    result = validate_human_approval_receipt(
        _receipt(expires_at="2026-04-01T00:00:00+00:00"),
        requested_scope=["ledger:debit"],
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.is_valid is False
    assert "human_approval_expired" in result.failure_reasons


def test_signature_unverified_fails_validation() -> None:
    result = validate_human_approval_receipt(
        _receipt(signature_verified=False),
        requested_scope=["ledger:debit"],
    )

    assert result.is_valid is False
    assert "human_approval_signature_unverified" in result.failure_reasons


def test_requested_scope_not_covered_fails_validation() -> None:
    result = validate_human_approval_receipt(
        _receipt(approved_scope=["ledger:credit"]),
        requested_scope=["ledger:debit"],
    )

    assert result.is_valid is False
    assert "human_approval_scope_not_granted" in result.failure_reasons


def test_policy_snapshot_mismatch_fails_validation() -> None:
    result = validate_human_approval_receipt(
        _receipt(policy_snapshot_id="policy-other"),
        requested_scope=["ledger:debit"],
        policy_snapshot_id="policy-001",
    )

    assert result.is_valid is False
    assert "human_approval_policy_snapshot_mismatch" in result.failure_reasons


def test_action_class_mismatch_fails_validation() -> None:
    result = validate_human_approval_receipt(
        _receipt(approved_action_class="other_action"),
        requested_scope=["ledger:debit"],
        action_class="wire_transfer",
    )

    assert result.is_valid is False
    assert "human_approval_action_class_mismatch" in result.failure_reasons


def test_high_irreversibility_passes_with_valid_human_approval_state() -> None:
    validator = RuntimeAuthorityValidator()
    approval_state = build_human_approval_state(
        _receipt(),
        requested_scope=["ledger:debit"],
        action_class="wire_transfer",
        policy_snapshot_id="policy-001",
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    result = validator.validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_state=approval_state,
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "pass"
    assert result.recommended_outcome == "commit"


def test_high_irreversibility_blocks_with_invalid_human_approval_state() -> None:
    validator = RuntimeAuthorityValidator()
    approval_state = build_human_approval_state(
        _receipt(expires_at="2026-04-01T00:00:00+00:00"),
        requested_scope=["ledger:debit"],
        action_class="wire_transfer",
        policy_snapshot_id="policy-001",
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    result = validator.validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_state=approval_state,
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "fail"
    assert result.recommended_outcome == "block"


def test_with_receipt_hash_populates_non_empty_hash() -> None:
    finalized = with_receipt_hash(_receipt())

    assert finalized.receipt_hash


def test_with_receipt_hash_populates_sha256_length() -> None:
    finalized = with_receipt_hash(_receipt())

    assert len(finalized.receipt_hash) == 64


def test_with_receipt_hash_is_deterministic_for_same_content() -> None:
    one = with_receipt_hash(_receipt(metadata={"x": "1"}))
    two = with_receipt_hash(_receipt(metadata={"x": "1"}))

    assert one.receipt_hash == two.receipt_hash


def test_with_receipt_hash_changes_when_meaningful_field_changes() -> None:
    one = with_receipt_hash(_receipt(approved_scope=["ledger:debit"]))
    two = with_receipt_hash(_receipt(approved_scope=["ledger:credit"]))

    assert one.receipt_hash != two.receipt_hash


def test_receipt_hash_does_not_recursively_affect_own_hash() -> None:
    first = with_receipt_hash(_receipt(receipt_hash=""))
    second = with_receipt_hash(_receipt(receipt_hash="tampered"))

    assert first.receipt_hash == second.receipt_hash


def test_human_approval_state_uses_finalized_receipt_hash() -> None:
    receipt = _receipt()
    finalized = with_receipt_hash(receipt)

    state = build_human_approval_state(
        receipt,
        requested_scope=["ledger:debit"],
        action_class="wire_transfer",
        policy_snapshot_id="policy-001",
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert state["approved"] is True
    assert state["receipt_hash"] == finalized.receipt_hash
