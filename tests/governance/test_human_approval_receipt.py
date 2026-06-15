"""Tests for local/offline Human Approval Receipt v1 helpers."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.governance.authority_evidence import AuthorityEvidence, VerificationResult
from veritas_os.governance.human_approval_receipt import (
    HumanApprovalReceipt,
    HumanApprovalSignatureVerificationResult,
    HumanApprovalSignerPolicy,
    TestHumanApprovalSignatureVerifier,
    VerifiedHumanApprovalReceipt,
    build_human_approval_state,
    validate_human_approval_receipt,
    verify_human_approval_receipt_artifact,
    verify_human_approval_receipt_artifact_to_proof,
    with_receipt_hash,
)
from veritas_os.governance.runtime_authority import (
    RuntimeAuthorityValidationResult,
    RuntimeAuthorityValidator,
)


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


def _signed_artifact(
    receipt: HumanApprovalReceipt | None = None,
    **overrides: object,
) -> dict[str, object]:
    base_receipt = receipt or _receipt(signature_verified=False)
    receipt_payload = base_receipt.to_dict_for_hash()
    receipt_payload["signature_verified"] = True
    digest_payload = dict(receipt_payload)
    digest_payload["signature_verified"] = False
    digest_payload["receipt_hash"] = ""
    digest_receipt = HumanApprovalReceipt(**digest_payload)
    artifact = {
        "artifact_type": "human_approval_receipt",
        "artifact_version": "v1",
        "receipt": receipt_payload,
        "receipt_hash": digest_receipt.deterministic_digest(),
        "signature": "test-signature",
        "signer": {
            "key_id": "test-key",
            "algorithm": "test-only",
            "identity": "operator:approver-1",
            "role": "risk_manager",
        },
        "signed_at": "2026-05-01T00:00:00+00:00",
    }
    artifact.update(overrides)
    return artifact


def _signature_result(**overrides: object) -> HumanApprovalSignatureVerificationResult:
    payload = {
        "verified": True,
        "key_id": "test-key",
        "algorithm": "test-only",
        "signer_identity": "operator:approver-1",
        "signer_role": "risk_manager",
        "reason": "test_verified",
    }
    payload.update(overrides)
    return HumanApprovalSignatureVerificationResult(**payload)


class _ProductionHumanApprovalSignatureVerifier:
    """Non-test verifier fixture that satisfies the production verifier contract."""

    def __init__(
        self,
        result: HumanApprovalSignatureVerificationResult | None = None,
    ) -> None:
        self._result = result or _signature_result()

    def verify(
        self,
        artifact: dict[str, object],
    ) -> HumanApprovalSignatureVerificationResult:
        """Return a structured verification result for production-path tests."""
        return self._result


def _signer_policy(**overrides: object) -> HumanApprovalSignerPolicy:
    payload = {
        "policy_id": "signer-policy-001",
        "allowed_key_ids": ["test-key"],
        "allowed_algorithms": ["test-only"],
        "required_signer_roles": ["risk_manager"],
        "required_signer_identities": ["operator:approver-1"],
        "allowed_action_classes": ["wire_transfer"],
        "allowed_policy_snapshot_ids": ["policy-001"],
    }
    payload.update(overrides)
    return HumanApprovalSignerPolicy(**payload)


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


def test_raw_approved_dict_without_receipt_hash_fails_closed() -> None:
    """Runtime authority cannot trust a self-asserted approval dict."""
    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_state={"approved": True},
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "fail"
    assert result.recommended_outcome == "block"
    assert "human_approval_receipt_missing" in result.reason_summary


def test_raw_approved_dict_with_untrusted_receipt_hash_fails_closed() -> None:
    """Receipt-shaped dicts must include validated receipt state metadata."""
    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_state={
            "approved": True,
            "approval_state_source": "validated_human_approval_receipt",
            "approval_receipt_id": "har-001",
            "receipt_hash": "0" * 64,
            "approved_scope": ["ledger:debit"],
            "approved_action_class": "wire_transfer",
            "policy_snapshot_id": "policy-001",
            "validated_at": "2026-05-10T00:00:00+00:00",
        },
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "fail"
    assert "human_approval_receipt_missing" in result.reason_summary


def test_tampered_receipt_hash_in_built_state_fails_closed() -> None:
    """Runtime authority rejects receipt-derived state with tampered hash."""
    approval_state = build_human_approval_state(
        _receipt(),
        requested_scope=["ledger:debit"],
        action_class="wire_transfer",
        policy_snapshot_id="policy-001",
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )
    approval_state["receipt_hash"] = "f" * 64

    result = RuntimeAuthorityValidator().validate(
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
    assert "human_approval_validation_hash_mismatch" in result.reason_summary


def test_tampered_approved_scope_in_built_state_fails_closed() -> None:
    """Runtime authority rejects receipt-derived state with tampered scope."""
    approval_state = build_human_approval_state(
        _receipt(),
        requested_scope=["ledger:debit"],
        action_class="wire_transfer",
        policy_snapshot_id="policy-001",
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )
    approval_state["approved_scope"] = ["ledger:mint"]

    result = RuntimeAuthorityValidator().validate(
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
    assert "human_approval_validation_hash_mismatch" in result.reason_summary


@pytest.mark.parametrize(
    ("receipt_overrides", "requested_scope", "action_class", "policy_snapshot_id", "reason"),
    [
        (
            {"expires_at": "2026-04-01T00:00:00+00:00"},
            ["ledger:debit"],
            "wire_transfer",
            "policy-001",
            "human_approval_expired",
        ),
        (
            {"signature_verified": False},
            ["ledger:debit"],
            "wire_transfer",
            "policy-001",
            "human_approval_signature_unverified",
        ),
        (
            {"approved_scope": ["ledger:credit"]},
            ["ledger:debit"],
            "wire_transfer",
            "policy-001",
            "human_approval_scope_not_granted",
        ),
        (
            {"policy_snapshot_id": "policy-other"},
            ["ledger:debit"],
            "wire_transfer",
            "policy-001",
            "human_approval_policy_snapshot_mismatch",
        ),
        (
            {"approved_action_class": "other_action"},
            ["ledger:debit"],
            "wire_transfer",
            "policy-001",
            "human_approval_action_class_mismatch",
        ),
    ],
)
def test_runtime_authority_blocks_invalid_human_approval_receipt_state(
    receipt_overrides: dict[str, object],
    requested_scope: list[str],
    action_class: str,
    policy_snapshot_id: str,
    reason: str,
) -> None:
    """Runtime authority propagates fail-closed receipt validation reasons."""
    approval_state = build_human_approval_state(
        _receipt(**receipt_overrides),
        requested_scope=requested_scope,
        action_class=action_class,
        policy_snapshot_id=policy_snapshot_id,
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    result = RuntimeAuthorityValidator().validate(
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
    assert reason in result.reason_summary


def _approval_reason(result: RuntimeAuthorityValidationResult) -> str:
    return next(
        predicate.reason
        for predicate in result.missing_predicates
        if predicate.predicate_type == "human_approval_present"
    )


@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_strict_posture_rejects_valid_receipt_without_artifact_provenance(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", posture)
    validator = RuntimeAuthorityValidator()

    result = validator.validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_receipt=_receipt(),
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "fail"
    assert _approval_reason(result) == "human_approval_artifact_provenance_required"


@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_strict_posture_rejects_compatibility_state_without_receipt(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", posture)
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

    assert result.status == "fail"
    assert _approval_reason(result) == "human_approval_receipt_required"


def test_dev_posture_keeps_compatibility_state_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", "dev")
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


def test_dev_posture_accepts_direct_signature_verified_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", "dev")

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_receipt=_receipt(signature_verified=True),
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "pass"
    assert result.recommended_outcome == "commit"


def test_dev_posture_rejects_raw_approved_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    validator = RuntimeAuthorityValidator()

    result = validator.validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_state={"approved": True},
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "fail"
    assert _approval_reason(result) == "human_approval_receipt_missing"


@pytest.mark.parametrize("posture", ["secure", "prod"])
@pytest.mark.parametrize(
    "receipt_overrides",
    [
        {"expires_at": "2026-04-01T00:00:00+00:00"},
        {"signature_verified": False},
        {"approved_scope": ["ledger:credit"]},
    ],
)
def test_strict_posture_invalid_direct_receipt_requires_provenance(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
    receipt_overrides: dict[str, object],
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", posture)
    validator = RuntimeAuthorityValidator()

    result = validator.validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_receipt=_receipt(**receipt_overrides),
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "fail"
    assert _approval_reason(result) == "human_approval_artifact_provenance_required"


def test_signed_human_approval_artifact_verification_sets_signature_verified() -> None:
    artifact = _signed_artifact()

    receipt = verify_human_approval_receipt_artifact(
        artifact,
        lambda signed_artifact: signed_artifact["signature"] == "test-signature",
        requested_scope=["ledger:debit"],
        action_class="wire_transfer",
        policy_snapshot_id="policy-001",
        now=datetime(2026, 5, 10, tzinfo=UTC),
        signer_policy=_signer_policy(),
    )

    assert receipt.signature_verified is True
    assert receipt.receipt_hash == artifact["receipt_hash"]
    assert receipt.metadata["verification_source"] == "signed_human_approval_artifact"
    assert receipt.metadata["artifact_type"] == "human_approval_receipt"
    assert receipt.metadata["artifact_version"] == "v1"
    assert receipt.metadata["signer_key_id"] == "test-key"
    assert receipt.metadata["signer_algorithm"] == "test-only"
    assert receipt.metadata["signed_at"] == "2026-05-01T00:00:00+00:00"
    assert receipt.metadata["verified_at"] == "2026-05-10T00:00:00+00:00"
    assert receipt.metadata["receipt_hash_verified"] is True
    assert receipt.metadata["signature_verified_by_runtime"] is True


def test_signed_human_approval_artifact_bad_signature_fails() -> None:
    artifact = _signed_artifact()

    with pytest.raises(ValueError, match="human_approval_signature_verification_failed"):
        verify_human_approval_receipt_artifact(
            artifact,
            lambda _artifact: False,
            requested_scope=["ledger:debit"],
            action_class="wire_transfer",
            policy_snapshot_id="policy-001",
            now=datetime(2026, 5, 10, tzinfo=UTC),
            signer_policy=_signer_policy(),
        )


def test_signed_human_approval_artifact_tampered_receipt_hash_fails() -> None:
    artifact = _signed_artifact(receipt_hash="f" * 64)

    with pytest.raises(ValueError, match="human_approval_receipt_hash_mismatch"):
        verify_human_approval_receipt_artifact(
            artifact,
            lambda _artifact: True,
            requested_scope=["ledger:debit"],
            action_class="wire_transfer",
            policy_snapshot_id="policy-001",
            now=datetime(2026, 5, 10, tzinfo=UTC),
            signer_policy=_signer_policy(),
        )


def test_signed_human_approval_artifact_without_verifier_fails() -> None:
    with pytest.raises(ValueError, match="human_approval_signature_verifier_required"):
        verify_human_approval_receipt_artifact(
            _signed_artifact(),
            None,
            requested_scope=["ledger:debit"],
            action_class="wire_transfer",
            policy_snapshot_id="policy-001",
            now=datetime(2026, 5, 10, tzinfo=UTC),
            signer_policy=_signer_policy(),
        )


@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_strict_posture_rejects_naked_signature_verified_receipt(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", posture)

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_receipt=_receipt(signature_verified=True),
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "fail"
    assert _approval_reason(result) == "human_approval_artifact_provenance_required"


@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_strict_posture_rejects_forged_receipt_provenance(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", posture)
    forged_receipt = _receipt(
        signature_verified=True,
        metadata={
            "verification_source": "signed_human_approval_artifact",
            "artifact_type": "human_approval_receipt",
            "artifact_version": "v1",
            "signer_key_id": "attacker-key",
            "signer_algorithm": "test-only",
            "signed_at": "2026-05-01T00:00:00+00:00",
            "verified_at": "2026-05-10T00:00:00+00:00",
            "receipt_hash_verified": True,
            "signature_verified_by_runtime": True,
        },
    )

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_receipt=forged_receipt,
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "fail"
    assert _approval_reason(result) == "human_approval_artifact_provenance_required"


@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_strict_posture_accepts_receipt_returned_by_artifact_verifier(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", posture)
    verified_receipt = verify_human_approval_receipt_artifact(
        _signed_artifact(),
        lambda _artifact: _signature_result(),
        requested_scope=["ledger:debit"],
        action_class="wire_transfer",
        policy_snapshot_id="policy-001",
        now=datetime(2026, 5, 10, tzinfo=UTC),
        signer_policy=_signer_policy(),
        require_structured_signature_result=True,
    )

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_receipt=verified_receipt,
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "pass"
    assert result.recommended_outcome == "commit"



@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_strict_posture_rejects_test_human_approval_signature_verifier(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", posture)

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_artifact=_signed_artifact(),
        human_approval_signature_verifier=TestHumanApprovalSignatureVerifier(),
        human_approval_signer_policy=_signer_policy(),
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "fail"
    assert _approval_reason(result) == (
        "human_approval_test_signature_verifier_not_allowed"
    )


@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_strict_posture_accepts_non_test_human_approval_signature_verifier(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", posture)

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_artifact=_signed_artifact(),
        human_approval_signature_verifier=_ProductionHumanApprovalSignatureVerifier(),
        human_approval_signer_policy=_signer_policy(),
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "pass"
    assert result.recommended_outcome == "commit"


@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_strict_posture_prefers_human_approval_signature_verifier(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", posture)

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_artifact=_signed_artifact(),
        verify_human_approval_signature_fn=lambda _artifact: _signature_result(
            verified=False
        ),
        human_approval_signature_verifier=_ProductionHumanApprovalSignatureVerifier(),
        human_approval_signer_policy=_signer_policy(),
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "pass"


@pytest.mark.parametrize("posture", ["dev", "test"])
def test_dev_test_posture_can_use_test_human_approval_signature_verifier(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", posture)

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_artifact=_signed_artifact(),
        human_approval_signature_verifier=TestHumanApprovalSignatureVerifier(),
        human_approval_signer_policy=_signer_policy(),
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "pass"


def test_strict_posture_rejects_incomplete_signature_verifier_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", "prod")

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_artifact=_signed_artifact(),
        human_approval_signature_verifier=_ProductionHumanApprovalSignatureVerifier(
            _signature_result(key_id="")
        ),
        human_approval_signer_policy=_signer_policy(),
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "fail"
    assert _approval_reason(result) == "human_approval_signature_key_id_missing"


def test_strict_posture_rejects_signature_verifier_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", "prod")

    def raise_verification_error(_artifact: dict[str, object]) -> object:
        raise RuntimeError("kms unavailable")

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_artifact=_signed_artifact(),
        verify_human_approval_signature_fn=raise_verification_error,
        human_approval_signer_policy=_signer_policy(),
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "fail"
    assert _approval_reason(result) == "human_approval_signature_verification_failed"


@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_strict_posture_passes_with_valid_signed_human_approval_artifact(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", posture)

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_artifact=_signed_artifact(),
        verify_human_approval_signature_fn=lambda _artifact: _signature_result(),
        human_approval_signer_policy=_signer_policy(),
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "pass"
    assert result.recommended_outcome == "commit"


@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_strict_posture_rejects_signed_artifact_with_bad_signature(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", posture)

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_artifact=_signed_artifact(),
        verify_human_approval_signature_fn=(
            lambda _artifact: _signature_result(verified=False)
        ),
        human_approval_signer_policy=_signer_policy(),
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "fail"
    assert _approval_reason(result) == "human_approval_signature_verification_failed"


@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_strict_posture_rejects_signed_artifact_with_tampered_receipt_hash(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", posture)

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_artifact=_signed_artifact(receipt_hash="f" * 64),
        verify_human_approval_signature_fn=lambda _artifact: _signature_result(),
        human_approval_signer_policy=_signer_policy(),
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "fail"
    assert _approval_reason(result) == "human_approval_receipt_hash_mismatch"


@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_strict_posture_rejects_signed_artifact_without_verifier(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", posture)

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_artifact=_signed_artifact(),
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "fail"
    assert _approval_reason(result) == "human_approval_signature_verifier_required"


def test_signed_human_approval_artifact_verification_produces_proof() -> None:
    proof = verify_human_approval_receipt_artifact_to_proof(
        _signed_artifact(),
        lambda _artifact: _signature_result(),
        requested_scope=["ledger:debit"],
        action_class="wire_transfer",
        policy_snapshot_id="policy-001",
        now=datetime(2026, 5, 10, tzinfo=UTC),
        signer_policy=_signer_policy(),
    )

    assert isinstance(proof, VerifiedHumanApprovalReceipt)
    assert proof.receipt.signature_verified is True
    assert proof.receipt_hash == proof.receipt.receipt_hash
    assert proof.artifact_type == "human_approval_receipt"
    assert proof.artifact_version == "v1"
    assert proof.verification_source == "signed_human_approval_artifact"
    assert len(proof.verification_proof_hash) == 64


@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_strict_posture_rejects_bool_signature_verifier_result(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", posture)

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_artifact=_signed_artifact(),
        verify_human_approval_signature_fn=lambda _artifact: True,
        human_approval_signer_policy=_signer_policy(),
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "fail"
    assert _approval_reason(result) == (
        "human_approval_structured_signature_result_required"
    )


def test_dev_posture_accepts_bool_signature_verifier_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", "dev")

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_artifact=_signed_artifact(),
        verify_human_approval_signature_fn=lambda _artifact: True,
        human_approval_signer_policy=_signer_policy(),
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "pass"


@pytest.mark.parametrize(
    ("verification_result", "expected_reason"),
    [
        (_signature_result(key_id=""), "human_approval_signature_key_id_missing"),
        (_signature_result(algorithm=""), "human_approval_signature_algorithm_missing"),
        (
            _signature_result(signer_identity=""),
            "human_approval_signature_signer_identity_missing",
        ),
        (
            _signature_result(signer_role=""),
            "human_approval_signature_signer_role_missing",
        ),
    ],
)
def test_structured_signature_verification_result_missing_fields_fail(
    verification_result: HumanApprovalSignatureVerificationResult,
    expected_reason: str,
) -> None:
    with pytest.raises(ValueError, match=expected_reason):
        verify_human_approval_receipt_artifact_to_proof(
            _signed_artifact(),
            lambda _artifact: verification_result,
            requested_scope=["ledger:debit"],
            action_class="wire_transfer",
            policy_snapshot_id="policy-001",
            now=datetime(2026, 5, 10, tzinfo=UTC),
            signer_policy=_signer_policy(),
            require_structured_signature_result=True,
        )


def test_signed_human_approval_artifact_valid_signer_policy_passes() -> None:
    proof = verify_human_approval_receipt_artifact_to_proof(
        _signed_artifact(),
        lambda _artifact: _signature_result(),
        requested_scope=["ledger:debit"],
        action_class="wire_transfer",
        policy_snapshot_id="policy-001",
        now=datetime(2026, 5, 10, tzinfo=UTC),
        signer_policy=_signer_policy(),
    )

    assert proof.signer_identity == "operator:approver-1"
    assert proof.signer_role == "risk_manager"
    assert proof.signer_policy_id == "signer-policy-001"
    assert proof.signature_verification_reason == "test_verified"


@pytest.mark.parametrize(
    ("policy", "expected_reason"),
    [
        (
            _signer_policy(allowed_key_ids=["other-key"]),
            "human_approval_signer_key_not_allowed",
        ),
        (
            _signer_policy(allowed_algorithms=["ed25519"]),
            "human_approval_signer_algorithm_not_allowed",
        ),
        (
            _signer_policy(required_signer_roles=["security_reviewer"]),
            "human_approval_signer_role_not_allowed",
        ),
        (
            _signer_policy(required_signer_identities=["operator:security-reviewer"]),
            "human_approval_signer_identity_not_allowed",
        ),
        (
            _signer_policy(allowed_action_classes=["account_closure"]),
            "human_approval_signer_action_class_not_allowed",
        ),
        (
            _signer_policy(allowed_policy_snapshot_ids=["policy-999"]),
            "human_approval_signer_policy_snapshot_not_allowed",
        ),
    ],
)
def test_signed_human_approval_artifact_signer_policy_failures(
    policy: HumanApprovalSignerPolicy,
    expected_reason: str,
) -> None:
    with pytest.raises(ValueError, match=expected_reason):
        verify_human_approval_receipt_artifact_to_proof(
            _signed_artifact(),
            lambda _artifact: True,
            requested_scope=["ledger:debit"],
            action_class="wire_transfer",
            policy_snapshot_id="policy-001",
            now=datetime(2026, 5, 10, tzinfo=UTC),
            signer_policy=policy,
        )


def test_signed_human_approval_proof_hash_changes_with_signer_policy_hash() -> None:
    first = verify_human_approval_receipt_artifact_to_proof(
        _signed_artifact(),
        lambda _artifact: True,
        requested_scope=["ledger:debit"],
        action_class="wire_transfer",
        policy_snapshot_id="policy-001",
        now=datetime(2026, 5, 10, tzinfo=UTC),
        signer_policy=_signer_policy(policy_hash="a" * 64),
    )
    second = verify_human_approval_receipt_artifact_to_proof(
        _signed_artifact(),
        lambda _artifact: True,
        requested_scope=["ledger:debit"],
        action_class="wire_transfer",
        policy_snapshot_id="policy-001",
        now=datetime(2026, 5, 10, tzinfo=UTC),
        signer_policy=_signer_policy(policy_hash="b" * 64),
    )

    assert first.verification_proof_hash != second.verification_proof_hash


@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_strict_posture_passes_with_valid_verified_human_approval_proof(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", posture)
    proof = verify_human_approval_receipt_artifact_to_proof(
        _signed_artifact(),
        lambda _artifact: _signature_result(),
        requested_scope=["ledger:debit"],
        action_class="wire_transfer",
        policy_snapshot_id="policy-001",
        now=datetime(2026, 5, 10, tzinfo=UTC),
        signer_policy=_signer_policy(),
    )

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        verified_human_approval=proof,
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "pass"
    assert result.recommended_outcome == "commit"


@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_strict_posture_rejects_tampered_verified_proof_hash(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", posture)
    proof = verify_human_approval_receipt_artifact_to_proof(
        _signed_artifact(),
        lambda _artifact: True,
        requested_scope=["ledger:debit"],
        action_class="wire_transfer",
        policy_snapshot_id="policy-001",
        now=datetime(2026, 5, 10, tzinfo=UTC),
        signer_policy=_signer_policy(),
    )

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        verified_human_approval=replace(proof, verification_proof_hash="f" * 64),
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "fail"
    assert _approval_reason(result) == (
        "human_approval_verification_proof_hash_mismatch"
    )


@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_strict_posture_rejects_tampered_verified_receipt_hash(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", posture)
    proof = verify_human_approval_receipt_artifact_to_proof(
        _signed_artifact(),
        lambda _artifact: True,
        requested_scope=["ledger:debit"],
        action_class="wire_transfer",
        policy_snapshot_id="policy-001",
        now=datetime(2026, 5, 10, tzinfo=UTC),
        signer_policy=_signer_policy(),
    )

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        verified_human_approval=replace(proof, receipt_hash="f" * 64),
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "fail"
    assert _approval_reason(result) == "human_approval_receipt_hash_mismatch"


def test_dev_posture_plain_receipt_compatibility_remains_intact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", "dev")

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_receipt=_receipt(signature_verified=True),
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "pass"
    assert result.recommended_outcome == "commit"


def _bound_receipt(**overrides: object) -> HumanApprovalReceipt:
    payload = {
        "request_ref": "request-001",
        "ai_output_ref": "ai-output-001",
        "execution_intent_id": "intent-001",
        "decision_id": "decision-001",
        "approved_action_class": "wire_transfer",
        "policy_snapshot_id": "policy-001",
        "authority_evidence_id": "aev-001",
        "bind_context_hash": "bind-hash-001",
    }
    payload.update(overrides)
    return _receipt(**payload)


def test_verified_human_approval_proof_hash_includes_context_binding() -> None:
    proof = verify_human_approval_receipt_artifact_to_proof(
        _signed_artifact(_bound_receipt(signature_verified=False)),
        lambda _artifact: _signature_result(),
        requested_scope=["ledger:debit"],
        action_class="wire_transfer",
        policy_snapshot_id="policy-001",
        now=datetime(2026, 5, 10, tzinfo=UTC),
        signer_policy=_signer_policy(),
    )

    payload = proof.proof_hash_payload()

    assert payload["request_ref"] == "request-001"
    assert payload["ai_output_ref"] == "ai-output-001"
    assert payload["execution_intent_id"] == "intent-001"
    assert payload["action_class"] == "wire_transfer"
    assert payload["policy_snapshot_id"] == "policy-001"
    assert payload["authority_evidence_id"] == "aev-001"
    assert payload["bind_context_hash"] == "bind-hash-001"


@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_strict_posture_passes_signed_approval_bound_to_same_context(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", posture)

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_artifact=_signed_artifact(
            _bound_receipt(signature_verified=False)
        ),
        verify_human_approval_signature_fn=lambda _artifact: _signature_result(),
        human_approval_signer_policy=_signer_policy(),
        request_ref="request-001",
        ai_output_ref="ai-output-001",
        execution_intent_id="intent-001",
        bind_context_hash="bind-hash-001",
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "pass"


@pytest.mark.parametrize(
    ("runtime_overrides", "receipt_overrides", "expected_reason"),
    [
        ({"request_ref": "request-999"}, {}, "human_approval_request_ref_mismatch"),
        (
            {"ai_output_ref": "ai-output-999"},
            {},
            "human_approval_ai_output_ref_mismatch",
        ),
        (
            {"execution_intent_id": "intent-999"},
            {},
            "human_approval_execution_intent_mismatch",
        ),
        (
            {},
            {"approved_action_class": "account_closure"},
            "human_approval_action_class_mismatch",
        ),
        (
            {},
            {"policy_snapshot_id": "policy-999"},
            "human_approval_policy_snapshot_mismatch",
        ),
        (
            {},
            {"authority_evidence_id": "aev-999"},
            "human_approval_authority_evidence_mismatch",
        ),
        (
            {"bind_context_hash": "bind-hash-999"},
            {},
            "human_approval_bind_context_hash_mismatch",
        ),
    ],
)
def test_strict_posture_rejects_signed_approval_reused_across_context(
    monkeypatch: pytest.MonkeyPatch,
    runtime_overrides: dict[str, str],
    receipt_overrides: dict[str, str],
    expected_reason: str,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", "secure")
    runtime_payload = {
        "policy_snapshot_id": "policy-001",
        "request_ref": "request-001",
        "ai_output_ref": "ai-output-001",
        "execution_intent_id": "intent-001",
        "bind_context_hash": "bind-hash-001",
    }
    runtime_payload.update(runtime_overrides)

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        actor_identity="operator:alice",
        human_approval_artifact=_signed_artifact(
            _bound_receipt(signature_verified=False, **receipt_overrides)
        ),
        verify_human_approval_signature_fn=lambda _artifact: _signature_result(),
        human_approval_signer_policy=_signer_policy(),
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
        **runtime_payload,
    )

    assert result.status == "fail"
    assert _approval_reason(result) == expected_reason


def test_dev_posture_unbound_compatibility_state_remains_intact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    state = build_human_approval_state(
        _receipt(),
        requested_scope=["ledger:debit"],
        action_class="wire_transfer",
        policy_snapshot_id="policy-001",
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    result = RuntimeAuthorityValidator().validate(
        action_contract=_contract(),
        authority_evidence=_authority(),
        requested_scope=["ledger:debit"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-001",
        actor_identity="operator:alice",
        human_approval_state=state,
        request_ref="request-001",
        ai_output_ref="ai-output-001",
        execution_intent_id="intent-001",
        bind_context_hash="bind-hash-001",
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    assert result.status == "pass"
