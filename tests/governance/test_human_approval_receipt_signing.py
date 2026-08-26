"""Tests for production Ed25519 Human Approval verification."""

from __future__ import annotations

import base64
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from veritas_os.governance.human_approval_receipt import (
    ApprovedHumanApprovalVerifier,
    HumanApprovalReceipt,
    HumanApprovalSignerPolicy,
    HumanApprovalVerifierPolicy,
    VerifiedHumanApprovalReceipt,
    verify_human_approval_receipt_artifact_to_proof,
)
from veritas_os.governance.human_approval_receipt_signing import (
    TrustedEd25519HumanApprovalVerifier,
    human_approval_signature_payload,
)

NOW = datetime(2026, 5, 10, tzinfo=UTC)
KEY_ID = "approval-key-1"
IDENTITY = "operator:approver-1"
ROLE = "risk_manager"


def _receipt() -> HumanApprovalReceipt:
    return HumanApprovalReceipt(
        approval_receipt_id="har-001",
        decision_id="decision-001",
        execution_intent_id="intent-001",
        approver_identity=IDENTITY,
        approver_role=ROLE,
        approved_action_class="wire_transfer",
        approved_scope=["ledger:debit"],
        approval_basis_refs=["policy:wire:v1"],
        approved_at="2026-05-01T00:00:00+00:00",
        expires_at="2026-06-01T00:00:00+00:00",
        policy_snapshot_id="policy-001",
        authority_evidence_id="aev-001",
        approval_result="approved",
        signature_verified=False,
        receipt_hash="",
        metadata={"purpose": "test"},
    )


def _verifier(
    private_key: Ed25519PrivateKey,
    **overrides: object,
) -> TrustedEd25519HumanApprovalVerifier:
    values = {
        "trusted_public_keys": {
            KEY_ID: private_key.public_key().public_bytes_raw()
        },
        "trusted_signer_identities": {KEY_ID: IDENTITY},
        "trusted_signer_roles": {KEY_ID: ROLE},
        "verifier_id": "trusted-human-approval-verifier",
    }
    values.update(overrides)
    return TrustedEd25519HumanApprovalVerifier(**values)  # type: ignore[arg-type]


def _artifact(private_key: Ed25519PrivateKey) -> dict[str, object]:
    receipt_payload = _receipt().to_dict_for_hash()
    receipt_payload["signature_verified"] = True
    digest_payload = dict(receipt_payload)
    digest_payload["signature_verified"] = False
    digest_payload["receipt_hash"] = ""
    receipt_hash = HumanApprovalReceipt(**digest_payload).deterministic_digest()
    artifact: dict[str, object] = {
        "artifact_type": "human_approval_receipt",
        "artifact_version": "v1",
        "receipt": receipt_payload,
        "receipt_hash": receipt_hash,
        "signer": {
            "key_id": KEY_ID,
            "algorithm": "Ed25519",
            "identity": IDENTITY,
            "role": ROLE,
        },
        "signed_at": "2026-05-01T00:00:00+00:00",
    }
    artifact["signature"] = base64.urlsafe_b64encode(
        private_key.sign(human_approval_signature_payload(artifact).encode())
    ).decode("ascii")
    return artifact


def _signer_policy(**overrides: object) -> HumanApprovalSignerPolicy:
    values = {
        "policy_id": "approval-signers-v1",
        "allowed_key_ids": [KEY_ID],
        "allowed_algorithms": ["Ed25519"],
        "required_signer_identities": [IDENTITY],
        "required_signer_roles": [ROLE],
        "allowed_action_classes": ["wire_transfer"],
        "allowed_policy_snapshot_ids": ["policy-001"],
    }
    values.update(overrides)
    return HumanApprovalSignerPolicy(**values)  # type: ignore[arg-type]


def _verifier_policy(
    verifier: TrustedEd25519HumanApprovalVerifier,
    **overrides: object,
) -> HumanApprovalVerifierPolicy:
    values = {
        "verifier_id": verifier.verifier_id,
        "trust_level": "production",
        "verifier_key_id": KEY_ID,
        "policy_id": verifier.verifier_policy_id,
        "policy_hash": verifier.policy_hash(),
    }
    values.update(overrides)
    return HumanApprovalVerifierPolicy(
        [ApprovedHumanApprovalVerifier(**values)]  # type: ignore[arg-type]
    )


def _proof(
    artifact: dict[str, object],
    verifier: TrustedEd25519HumanApprovalVerifier,
    *,
    signer_policy: HumanApprovalSignerPolicy | None = None,
    verifier_policy: HumanApprovalVerifierPolicy | None = None,
) -> VerifiedHumanApprovalReceipt:
    return verify_human_approval_receipt_artifact_to_proof(
        artifact,  # type: ignore[arg-type]
        verifier.verify,
        requested_scope=["ledger:debit"],
        action_class="wire_transfer",
        policy_snapshot_id="policy-001",
        now=NOW,
        signer_policy=signer_policy or _signer_policy(),
        verifier_policy=verifier_policy or _verifier_policy(verifier),
        require_structured_signature_result=True,
        require_production_verifier=True,
    )


def test_trusted_ed25519_verifier_produces_existing_verified_proof() -> None:
    private_key = Ed25519PrivateKey.generate()
    verifier = _verifier(private_key)

    proof = _proof(_artifact(private_key), verifier)

    assert proof.signer_identity == IDENTITY
    assert proof.signer_role == ROLE
    assert proof.signer_algorithm == "Ed25519"
    assert proof.verifier_policy_hash == verifier.policy_hash()
    assert proof.receipt.signature_verified is True


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("invalid_signature", "invalid_signature"),
        ("unknown_key", "untrusted_key"),
        ("unsupported_algorithm", "unsupported_algorithm"),
        ("malformed_base64", "malformed_signature"),
        ("missing_signature", "missing_signature"),
        ("malformed_envelope", "malformed_envelope"),
    ],
)
def test_verifier_fails_closed_for_untrusted_envelopes(
    mutation: str,
    reason: str,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    verifier = _verifier(private_key)
    artifact = _artifact(private_key)
    if mutation == "invalid_signature":
        artifact["signature"] = base64.urlsafe_b64encode(b"x" * 64).decode()
    elif mutation == "unknown_key":
        artifact["signer"]["key_id"] = "foreign"  # type: ignore[index]
    elif mutation == "unsupported_algorithm":
        artifact["signer"]["algorithm"] = "RSA"  # type: ignore[index]
    elif mutation == "malformed_base64":
        artifact["signature"] = "%%%"
    elif mutation == "missing_signature":
        artifact.pop("signature")
    else:
        artifact["receipt"] = "not-an-object"

    result = verifier.verify(artifact)  # type: ignore[arg-type]

    assert result.verified is False
    assert result.reason == reason


def test_malformed_trusted_public_key_fails_closed() -> None:
    private_key = Ed25519PrivateKey.generate()
    verifier = _verifier(private_key, trusted_public_keys={KEY_ID: b"short"})

    result = verifier.verify(_artifact(private_key))

    assert result.verified is False
    assert result.reason == "malformed_signature"


@pytest.mark.parametrize("field", ["identity", "role"])
def test_artifact_signer_metadata_cannot_override_trusted_mapping(field: str) -> None:
    private_key = Ed25519PrivateKey.generate()
    verifier = _verifier(private_key)
    artifact = _artifact(private_key)
    artifact["signer"][field] = "foreign"  # type: ignore[index]
    artifact["signature"] = base64.urlsafe_b64encode(
        private_key.sign(human_approval_signature_payload(artifact).encode())
    ).decode()

    with pytest.raises(ValueError, match=f"signer_{field}_mismatch"):
        _proof(artifact, verifier)


def test_tampered_receipt_is_rejected() -> None:
    private_key = Ed25519PrivateKey.generate()
    verifier = _verifier(private_key)
    artifact = deepcopy(_artifact(private_key))
    artifact["receipt"]["approved_scope"] = ["ledger:admin"]  # type: ignore[index]

    with pytest.raises(ValueError, match="receipt_hash_mismatch"):
        _proof(artifact, verifier)


@pytest.mark.parametrize(
    ("policy_kind", "overrides", "reason"),
    [
        ("signer", {"allowed_key_ids": ["foreign"]}, "signer_key_not_allowed"),
        ("signer", {"required_signer_identities": ["foreign"]}, "signer_identity_not_allowed"),
        ("signer", {"required_signer_roles": ["foreign"]}, "signer_role_not_allowed"),
        ("verifier", {"verifier_id": "foreign"}, "verifier_not_allowed"),
        ("verifier", {"policy_id": "foreign"}, "verifier_policy_id_mismatch"),
        ("verifier", {"policy_hash": "0" * 64}, "verifier_policy_hash_mismatch"),
    ],
)
def test_existing_policies_reject_untrusted_signer_or_verifier(
    policy_kind: str,
    overrides: dict[str, object],
    reason: str,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    verifier = _verifier(private_key)
    signer_policy = _signer_policy(**overrides) if policy_kind == "signer" else None
    verifier_policy = (
        _verifier_policy(verifier, **overrides)
        if policy_kind == "verifier"
        else None
    )

    with pytest.raises(ValueError, match=reason):
        _proof(
            _artifact(private_key),
            verifier,
            signer_policy=signer_policy,
            verifier_policy=verifier_policy,
        )
