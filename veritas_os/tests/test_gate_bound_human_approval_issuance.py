"""Two-phase and fail-closed tests for gate-bound Human Approval issuance."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.governance.human_approval_receipt import (
    ApprovedHumanApprovalVerifier,
    HumanApprovalSignerPolicy,
    HumanApprovalVerifierPolicy,
    validate_human_approval_context_binding,
    verify_human_approval_receipt_artifact_to_proof,
)
from veritas_os.governance.human_approval_receipt_signing import (
    TrustedEd25519HumanApprovalVerifier,
)
from veritas_os.policy.fresh_bind_source_chain import build_fresh_bind_source_chain
from veritas_os.policy.gate_bound_human_approval_issuance import (
    GateBoundHumanApprovalIssuanceError,
    HumanApprovalEvent,
    issue_gate_bound_human_approval_artifact,
)
from veritas_os.policy.live_adapter_bind_authorization_codec import _digest
from veritas_os.policy.live_adapter_bind_authorization_contracts import DOMAINS
from veritas_os.policy.real_bind_context import (
    derive_verified_real_bind_context_hash,
)
from veritas_os.tests.test_fresh_bind_source_chain import _inputs
from veritas_os.tests.test_live_adapter_dry_run_bind_authorization_gate_review import (
    RECORDED_AT,
)

KEY_ID = "approval-key-gate-bound"
IDENTITY = "operator:alice"
ROLE = "billing-operator"


@dataclass(frozen=True)
class _Ed25519Signer:
    key_id: str
    identity: str
    role: str
    private_key: Ed25519PrivateKey
    algorithm: str = "Ed25519"

    def sign(self, payload: bytes) -> bytes:
        return self.private_key.sign(payload)


def _contract(gate) -> ActionClassContract:
    return ActionClassContract(
        id=gate.execution_intent["intended_action"],
        version="1",
        domain="billing",
        action_class="billing_dispatch",
        description="Gate-bound approval test contract",
        declared_intent="dispatch a billing request",
        allowed_scope=["billing-dispatch"],
        prohibited_scope=["billing-admin"],
        authority_sources=["authority:billing"],
        required_evidence=[],
        evidence_freshness={},
        irreversibility={"level": "high"},
        human_approval_rules={"required": True, "minimum_approvals": 1},
        refusal_conditions=[],
        escalation_conditions=[],
        default_failure_mode="deny",
        metadata={"regulated": True},
    )


def _event() -> HumanApprovalEvent:
    return HumanApprovalEvent(
        approval_result="approved",
        approval_basis_refs=["policy:billing:v1"],
        approved_at=(RECORDED_AT - timedelta(minutes=1)).isoformat(),
        expires_at=(RECORDED_AT + timedelta(days=1)).isoformat(),
        signed_at=RECORDED_AT.isoformat(),
        metadata={"ticket": "change-123"},
    )


def _gate(*, built_at=RECORDED_AT):
    intent, inputs = _inputs()
    return build_fresh_bind_source_chain(
        intent, inputs, built_at=built_at
    ).verified_gate_review_packet


def _issue(gate, private_key, **signer_changes):
    signer_values = {
        "key_id": KEY_ID,
        "identity": IDENTITY,
        "role": ROLE,
        "private_key": private_key,
    }
    signer_values.update(signer_changes)
    return issue_gate_bound_human_approval_artifact(
        gate,
        action_contract=_contract(gate),
        event=_event(),
        signer=_Ed25519Signer(**signer_values),
    )


def _verification(gate, artifact, private_key):
    verifier = TrustedEd25519HumanApprovalVerifier(
        trusted_public_keys={KEY_ID: private_key.public_key().public_bytes_raw()},
        trusted_signer_identities={KEY_ID: IDENTITY},
        trusted_signer_roles={KEY_ID: ROLE},
        verifier_id="gate-bound-human-approval-verifier",
    )
    signer_policy = HumanApprovalSignerPolicy(
        policy_id="gate-bound-signers-v1",
        allowed_key_ids=[KEY_ID],
        allowed_algorithms=["Ed25519"],
        required_signer_identities=[IDENTITY],
        required_signer_roles=[ROLE],
        allowed_action_classes=[_contract(gate).action_class],
        allowed_policy_snapshot_ids=[gate.execution_intent["policy_snapshot_id"]],
    )
    verifier_policy = HumanApprovalVerifierPolicy(
        [
            ApprovedHumanApprovalVerifier(
                verifier_id=verifier.verifier_id,
                trust_level="production",
                verifier_key_id=KEY_ID,
                policy_id=verifier.verifier_policy_id,
                policy_hash=verifier.policy_hash(),
            )
        ]
    )
    return verify_human_approval_receipt_artifact_to_proof(
        artifact,
        verifier.verify,
        requested_scope=["billing-dispatch"],
        action_class=_contract(gate).action_class,
        policy_snapshot_id=gate.execution_intent["policy_snapshot_id"],
        now=RECORDED_AT,
        signer_policy=signer_policy,
        verifier_policy=verifier_policy,
        require_structured_signature_result=True,
        require_production_verifier=True,
    )


def test_two_phase_gate_issue_verify_and_context_bind() -> None:
    gate = _gate()
    private_key = Ed25519PrivateKey.generate()

    artifact = _issue(gate, private_key)
    proof = _verification(gate, artifact, private_key)
    result = validate_human_approval_context_binding(
        proof.receipt,
        request_ref=gate.execution_intent["request_id"],
        execution_intent_id=gate.execution_intent_id,
        decision_id=gate.execution_intent["decision_id"],
        action_class=_contract(gate).action_class,
        policy_snapshot_id=gate.execution_intent["policy_snapshot_id"],
        authority_evidence_id=(
            gate.authority_evidence_reference_bundle[
                "authority_evidence_references"
            ][0]["authority_evidence_reference_id"]
        ),
        bind_context_hash=derive_verified_real_bind_context_hash(gate),
    )

    assert result.is_valid is True
    assert proof.receipt.signature_verified is True
    assert artifact["receipt"]["bind_context_hash"] == (
        derive_verified_real_bind_context_hash(gate)
    )


def test_public_context_hash_preserves_prior_canonical_preimage() -> None:
    gate = _gate()
    previous = _digest(
        DOMAINS["bind_context"],
        {
            "source_gate_review_hash": (
                gate.live_adapter_dry_run_bind_authorization_gate_review_hash
            ),
            "execution_intent_id": gate.execution_intent_id,
            "execution_intent_hash": gate.execution_intent_hash,
            "adapter_contract_id": gate.adapter_contract_id,
            "adapter_contract_hash": gate.adapter_contract_hash,
            "endpoint_identity_binding_digest": (
                gate.endpoint_identity_binding_digest
            ),
            "credential_reference_digest": gate.credential_reference_digest,
            "credential_scope_binding_digest": (
                gate.credential_scope_binding_digest
            ),
        },
    )

    assert derive_verified_real_bind_context_hash(gate) == previous


def test_approval_for_gate_a_replays_fail_closed_against_gate_b() -> None:
    gate_a = _gate()
    gate_b = _gate(built_at=RECORDED_AT + timedelta(seconds=1))
    private_key = Ed25519PrivateKey.generate()
    proof = _verification(gate_a, _issue(gate_a, private_key), private_key)

    result = validate_human_approval_context_binding(
        proof.receipt,
        bind_context_hash=derive_verified_real_bind_context_hash(gate_b),
    )

    assert derive_verified_real_bind_context_hash(gate_a) != (
        derive_verified_real_bind_context_hash(gate_b)
    )
    assert result.failure_reasons == [
        "human_approval_bind_context_hash_mismatch"
    ]


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("identity", "operator:mallory", "SIGNER_IDENTITY_MISMATCH"),
        ("role", "billing-admin", "SIGNER_ROLE_MISMATCH"),
    ],
)
def test_signer_cannot_override_gate_approver(field, value, reason) -> None:
    gate = _gate()
    with pytest.raises(GateBoundHumanApprovalIssuanceError, match=reason):
        _issue(gate, Ed25519PrivateKey.generate(), **{field: value})


def test_gate_tampering_and_action_or_scope_substitution_fail_closed() -> None:
    gate = _gate()
    private_key = Ed25519PrivateKey.generate()
    contract = _contract(gate)
    signer = _Ed25519Signer(KEY_ID, IDENTITY, ROLE, private_key)
    raw = gate.model_dump(mode="json")
    raw["execution_intent"]["policy_snapshot_id"] = "foreign"
    with pytest.raises(GateBoundHumanApprovalIssuanceError, match="SOURCE_GATE"):
        issue_gate_bound_human_approval_artifact(
            raw,
            action_contract=contract,
            event=_event(),
            signer=signer,
        )

    wrong_contract = replace(contract, id="foreign-action")
    with pytest.raises(GateBoundHumanApprovalIssuanceError, match="CONTRACT_MISMATCH"):
        issue_gate_bound_human_approval_artifact(
            gate,
            action_contract=wrong_contract,
            event=_event(),
            signer=signer,
        )

    broad_contract = replace(
        contract, allowed_scope=["billing-admin"]
    )
    with pytest.raises(GateBoundHumanApprovalIssuanceError, match="SCOPE_INVALID"):
        issue_gate_bound_human_approval_artifact(
            gate,
            action_contract=broad_contract,
            event=_event(),
            signer=signer,
        )


def test_mutation_wrong_key_and_invalid_signature_fail_closed() -> None:
    gate = _gate()
    private_key = Ed25519PrivateKey.generate()
    artifact = _issue(gate, private_key)

    mutated = deepcopy(artifact)
    mutated["receipt"]["authority_evidence_id"] = "foreign"
    with pytest.raises(ValueError, match="receipt_hash_mismatch"):
        _verification(gate, mutated, private_key)

    artifact_signed_by_untrusted_key = _issue(
        gate, Ed25519PrivateKey.generate()
    )
    with pytest.raises(ValueError, match="signature_verification_failed"):
        _verification(gate, artifact_signed_by_untrusted_key, private_key)

    invalid = deepcopy(artifact)
    invalid["signature"] = "AAAAAAAA"
    with pytest.raises(ValueError, match="signature_verification_failed"):
        _verification(gate, invalid, private_key)
