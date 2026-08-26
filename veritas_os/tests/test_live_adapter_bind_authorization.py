"""Security and issuance tests for authenticated Real Bind Authorization v1."""

from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.governance.authority_evidence import (
    ApprovedAuthorityEvidenceVerifier,
    AuthorityEvidence,
    AuthorityEvidenceSignerPolicy,
    AuthorityEvidenceVerifierPolicy,
    AuthorityRevocationPolicy,
    AuthorityRevocationVerificationResult,
    VerificationResult,
    authority_signature_payload,
)
from veritas_os.governance.authority_evidence_signing import (
    TrustedEd25519AuthorityVerifier,
)
from veritas_os.governance.human_approval_receipt import (
    ApprovedHumanApprovalVerifier,
    HumanApprovalReceipt,
    HumanApprovalSignerPolicy,
    HumanApprovalVerifierPolicy,
)
from veritas_os.governance.human_approval_receipt_signing import (
    TrustedEd25519HumanApprovalVerifier,
    human_approval_signature_payload,
)
from veritas_os.policy.live_adapter_bind_authorization import (
    ACKNOWLEDGEMENTS,
    AUTHORIZER_ARTIFACT_TYPE,
    AUTHORIZER_ARTIFACT_VERSION,
    ApprovedBindAuthorizationVerifier,
    BindAuthorizationDecision,
    BindAuthorizationSignerPolicy,
    BindAuthorizationTrustInputs,
    BindAuthorizationVerifierPolicy,
    LiveAdapterBindAuthorizationError,
    RealBindAuthorizationGovernanceInputs,
    _artifact_hash,
    _bind_context_hash,
    _decision_hash,
    _timestamp,
    bind_authorizer_decision_signature_payload,
    build_live_adapter_bind_authorization_artifact,
    validate_live_adapter_bind_authorization_temporal_validity,
    verify_live_adapter_bind_authorization_artifact,
)
from veritas_os.policy.live_adapter_bind_authorization_signing import (
    TrustedEd25519BindAuthorizationVerifier,
)
from veritas_os.security.hash import sha256_of_canonical_json
from veritas_os.tests.test_live_adapter_dry_run_bind_authorization_gate_review import (
    RECORDED_AT as SOURCE_RECORDED_AT,
    _decision as gate_decision,
    _packet as source_packet,
)

AUTHORIZED_AT = SOURCE_RECORDED_AT + timedelta(seconds=1)
VERIFICATION_NOW = AUTHORIZED_AT + timedelta(seconds=1)
VALID_FROM = AUTHORIZED_AT
VALID_UNTIL = AUTHORIZED_AT + timedelta(minutes=5)


class _FreshRevocationChecker:
    def check(
        self, authority_evidence_id: str, *, now
    ) -> AuthorityRevocationVerificationResult:
        del authority_evidence_id
        return AuthorityRevocationVerificationResult(
            checked=True,
            revoked=False,
            checked_at=now.isoformat(),
            source_identity="bind-authorization-test-revocation",
            source_version="v1",
            source_hash="a" * 64,
            reason="not_revoked",
        )


@dataclass(frozen=True)
class _Ed25519Signer:
    private_key: Ed25519PrivateKey
    key_id: str
    identity: str
    role: str
    algorithm: str = "Ed25519"

    def sign(self, payload: bytes) -> bytes:
        return self.private_key.sign(payload)


def _contract(*, human_required: bool = False, required_evidence: list[str] | None = None):
    source = source_packet()
    action = source.execution_intent["intended_action"]
    scope = list(source.authority_evidence_reference_bundle["bundle_scope"])
    return ActionClassContract(
        id=action,
        version="1.0.0",
        domain="bind-authorization-test",
        action_class=action,
        description="Controlled Real Bind Authorization test contract.",
        declared_intent="Authorize one exact future Bind attempt.",
        allowed_scope=scope,
        prohibited_scope=["forbidden:scope"],
        authority_sources=["authority-source:billing:v1", "policy:billing:v1"],
        required_evidence=list(required_evidence or []),
        evidence_freshness={},
        irreversibility={
            "boundary": "future-bind-consumption",
            "level": "high" if human_required else "medium",
        },
        human_approval_rules=(
            {"required": True, "minimum_approvals": 1} if human_required else {}
        ),
        refusal_conditions=[],
        escalation_conditions=[],
        default_failure_mode="fail_closed",
        metadata={"controlled_test": True},
    )


def _authority_bundle(contract: ActionClassContract):
    source = source_packet()
    ref = source.authority_evidence_reference_bundle[
        "authority_evidence_references"
    ][0]
    actor = source.execution_intent["actor_identity"]
    policy_snapshot = source.execution_intent["policy_snapshot_id"]
    scope = list(source.authority_evidence_reference_bundle["bundle_scope"])
    issued = SOURCE_RECORDED_AT - timedelta(days=1)
    expires = SOURCE_RECORDED_AT + timedelta(days=1)
    evidence = AuthorityEvidence(
        authority_evidence_id=ref["authority_evidence_reference_id"],
        action_contract_id=contract.id,
        action_contract_version=contract.version,
        actor_identity=actor,
        actor_role="controlled-bind-operator",
        authority_source_refs=[ref["authority_source_id"], ref["authority_policy_id"]],
        role_or_policy_basis=["role:controlled-bind-operator"],
        scope_grants=scope,
        scope_limitations=list(contract.prohibited_scope),
        validity_window={
            "issued_at": issued.isoformat(),
            "valid_from": issued.isoformat(),
            "valid_until": expires.isoformat(),
        },
        issued_at=issued.isoformat(),
        valid_from=issued.isoformat(),
        valid_until=expires.isoformat(),
        revalidated_at=None,
        policy_snapshot_id=policy_snapshot,
        action_contract_hash=contract.deterministic_digest(),
        evidence_hash="",
        verification_result=VerificationResult.INDETERMINATE,
        failure_reasons=[],
        metadata={},
    )
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw()
    claims = evidence.claims_dict()
    artifact = {
        "artifact_type": "authority_evidence",
        "artifact_version": "v1",
        "claims": claims,
        "claims_hash": sha256_of_canonical_json(claims),
        "signer": {"key_id": "bind-authority-key", "algorithm": "Ed25519"},
        "issuer_identity": ref["authority_issuer"],
        "signed_at": VERIFICATION_NOW.isoformat(),
    }
    artifact["signature"] = base64.urlsafe_b64encode(
        private_key.sign(authority_signature_payload(artifact).encode("utf-8"))
    ).decode("ascii")
    verifier = TrustedEd25519AuthorityVerifier(
        {"bind-authority-key": public_key},
        {"bind-authority-key": ref["authority_issuer"]},
        "bind-authority-verifier",
    )
    signer_policy = AuthorityEvidenceSignerPolicy(
        "bind-authority-signer-policy",
        ["bind-authority-key"],
        ["Ed25519"],
        [ref["authority_issuer"]],
    )
    verifier_policy = AuthorityEvidenceVerifierPolicy(
        [
            ApprovedAuthorityEvidenceVerifier(
                verifier_id="bind-authority-verifier",
                trust_level="production",
                verifier_key_id="bind-authority-key",
                verifier_policy_id=verifier.verifier_policy_id,
                verifier_policy_hash=verifier.policy_hash(),
                signer_policy_id=signer_policy.policy_id,
                signer_policy_hash=signer_policy.deterministic_hash(),
            )
        ]
    )
    revocation_policy = AuthorityRevocationPolicy(
        max_age_seconds=60,
        allowed_source_identities=["bind-authorization-test-revocation"],
    )
    return (
        artifact,
        verifier,
        signer_policy,
        verifier_policy,
        _FreshRevocationChecker(),
        revocation_policy,
    )


def _signed_human_approval(contract: ActionClassContract):
    source = source_packet()
    approval_key_id = "human-approval-key"
    ref = source.human_approval_reference_bundle["human_approval_references"][0]
    authority_ref = source.authority_evidence_reference_bundle[
        "authority_evidence_references"
    ][0]
    scope = list(source.authority_evidence_reference_bundle["bundle_scope"])
    receipt = HumanApprovalReceipt(
        approval_receipt_id=ref["human_approval_reference_id"],
        decision_id=source.execution_intent["decision_id"],
        execution_intent_id=source.execution_intent_id,
        approver_identity=ref["approver_id"],
        approver_role=ref["approver_role"],
        approved_action_class=contract.action_class,
        approved_scope=scope,
        approval_basis_refs=["policy:billing:v1"],
        approved_at=SOURCE_RECORDED_AT.isoformat(),
        expires_at=(SOURCE_RECORDED_AT + timedelta(hours=1)).isoformat(),
        policy_snapshot_id=source.execution_intent["policy_snapshot_id"],
        authority_evidence_id=authority_ref["authority_evidence_reference_id"],
        approval_result="approved",
        signature_verified=False,
        receipt_hash="",
        request_ref=source.execution_intent["request_id"],
        ai_output_ref=None,
        bind_context_hash=_bind_context_hash(source),
        metadata={},
    )
    receipt_payload = receipt.to_dict_for_hash()
    receipt_payload["signature_verified"] = True
    digest_payload = dict(receipt_payload)
    digest_payload["signature_verified"] = False
    digest_payload["receipt_hash"] = ""
    expected_hash = HumanApprovalReceipt(**digest_payload).deterministic_digest()
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw()
    artifact = {
        "artifact_type": "human_approval_receipt",
        "artifact_version": "v1",
        "receipt": receipt_payload,
        "receipt_hash": expected_hash,
        "signer": {
            "key_id": approval_key_id,
            "algorithm": "Ed25519",
            "identity": ref["approver_id"],
            "role": ref["approver_role"],
        },
        "signed_at": SOURCE_RECORDED_AT.isoformat(),
    }
    artifact["signature"] = base64.urlsafe_b64encode(
        private_key.sign(human_approval_signature_payload(artifact).encode("utf-8"))
    ).decode("ascii")
    verifier = TrustedEd25519HumanApprovalVerifier(
        trusted_public_keys={approval_key_id: public_key},
        trusted_signer_identities={
            approval_key_id: ref["approver_id"]
        },
        trusted_signer_roles={approval_key_id: ref["approver_role"]},
        verifier_id="human-approval-ed25519-verifier",
        verifier_policy_id="human-approval-ed25519-policy-v1",
    )
    signer_policy = HumanApprovalSignerPolicy(
        policy_id="human-approval-signer-policy",
        allowed_key_ids=[approval_key_id],
        allowed_algorithms=["Ed25519"],
        required_signer_roles=[ref["approver_role"]],
        required_signer_identities=[ref["approver_id"]],
        allowed_action_classes=[contract.action_class],
        allowed_policy_snapshot_ids=[source.execution_intent["policy_snapshot_id"]],
    )
    verifier_policy = HumanApprovalVerifierPolicy(
        [
            ApprovedHumanApprovalVerifier(
                verifier_id=verifier.verifier_id,
                trust_level="production",
                verifier_key_id=approval_key_id,
                policy_id=verifier.verifier_policy_id,
                policy_hash=verifier.policy_hash(),
            )
        ]
    )
    return artifact, verifier, signer_policy, verifier_policy


def _governance_inputs(
    *, human_required: bool = False, required_evidence: list[str] | None = None
):
    contract = _contract(
        human_required=human_required, required_evidence=required_evidence
    )
    (
        authority_artifact,
        authority_verifier,
        authority_signer_policy,
        authority_verifier_policy,
        revocation_checker,
        revocation_policy,
    ) = _authority_bundle(contract)
    human = (None, None, None, None)
    if human_required:
        human = _signed_human_approval(contract)
    return RealBindAuthorizationGovernanceInputs(
        action_contract=contract,
        signed_authority_evidence_artifact=authority_artifact,
        authority_signature_verifier=authority_verifier,
        authority_signer_policy=authority_signer_policy,
        authority_verifier_policy=authority_verifier_policy,
        authority_revocation_checker=revocation_checker,
        authority_revocation_policy=revocation_policy,
        verification_now=VERIFICATION_NOW,
        signed_human_approval_artifact=human[0],
        human_approval_signature_verifier=human[1],
        human_approval_signer_policy=human[2],
        human_approval_verifier_policy=human[3],
    )


def _bind_signature_setup(
    *,
    authorizer_identity: str = "operator:bob",
    authorizer_private_key: Ed25519PrivateKey | None = None,
    authorizer_verifier_public_key: bytes | None = None,
):
    authorizer_private_key = authorizer_private_key or Ed25519PrivateKey.generate()
    authorizer_public_key = (
        authorizer_verifier_public_key
        or authorizer_private_key.public_key().public_bytes_raw()
    )
    authorizer_verifier = TrustedEd25519BindAuthorizationVerifier(
        {"bind-authorizer-key": authorizer_public_key},
        {"bind-authorizer-key": authorizer_identity},
        {"bind-authorizer-key": "bind-authorizer"},
        "bind-authorizer-verifier",
        "authorizer_decision",
    )
    authorizer_signer_policy = BindAuthorizationSignerPolicy(
        "bind-authorizer-signer-policy",
        "authorizer_decision",
        ["bind-authorizer-key"],
        ["Ed25519"],
        [authorizer_identity],
        ["bind-authorizer"],
    )
    authorizer_verifier_policy = BindAuthorizationVerifierPolicy(
        [
            ApprovedBindAuthorizationVerifier(
                verifier_id="bind-authorizer-verifier",
                trust_level="production",
                purpose="authorizer_decision",
                verifier_key_id="bind-authorizer-key",
                verifier_policy_id=authorizer_verifier.verifier_policy_id,
                verifier_policy_hash=authorizer_verifier.policy_hash(),
                signer_policy_id=authorizer_signer_policy.policy_id,
                signer_policy_hash=authorizer_signer_policy.deterministic_hash(),
            )
        ]
    )

    issuer_private_key = Ed25519PrivateKey.generate()
    issuer_signer = _Ed25519Signer(
        issuer_private_key,
        "bind-authorization-issuer-key",
        "service:bind-authorization-issuer",
        "bind-authorization-issuer",
    )
    issuer_verifier = TrustedEd25519BindAuthorizationVerifier(
        {"bind-authorization-issuer-key": issuer_private_key.public_key().public_bytes_raw()},
        {"bind-authorization-issuer-key": issuer_signer.identity},
        {"bind-authorization-issuer-key": issuer_signer.role},
        "bind-authorization-issuer-verifier",
        "authorization_issuer",
    )
    issuer_signer_policy = BindAuthorizationSignerPolicy(
        "bind-authorization-issuer-signer-policy",
        "authorization_issuer",
        [issuer_signer.key_id],
        ["Ed25519"],
        [issuer_signer.identity],
        [issuer_signer.role],
    )
    issuer_verifier_policy = BindAuthorizationVerifierPolicy(
        [
            ApprovedBindAuthorizationVerifier(
                verifier_id=issuer_verifier.verifier_id,
                trust_level="production",
                purpose="authorization_issuer",
                verifier_key_id=issuer_signer.key_id,
                verifier_policy_id=issuer_verifier.verifier_policy_id,
                verifier_policy_hash=issuer_verifier.policy_hash(),
                signer_policy_id=issuer_signer_policy.policy_id,
                signer_policy_hash=issuer_signer_policy.deterministic_hash(),
            )
        ]
    )
    trust = BindAuthorizationTrustInputs(
        authorizer_signature_verifier=authorizer_verifier,
        authorizer_signer_policy=authorizer_signer_policy,
        authorizer_verifier_policy=authorizer_verifier_policy,
        authorization_issuer_signature_verifier=issuer_verifier,
        authorization_issuer_signer_policy=issuer_signer_policy,
        authorization_issuer_verifier_policy=issuer_verifier_policy,
    )
    return authorizer_private_key, trust, issuer_signer


def _signed_decision(
    private_key: Ed25519PrivateKey,
    *,
    authorizer_identity: str = "operator:bob",
    source=None,
    valid_from=VALID_FROM,
    valid_until=VALID_UNTIL,
) -> dict[str, Any]:
    source = source or source_packet()
    decision = BindAuthorizationDecision.model_validate(
        {
            "source_gate_review_id": source.live_adapter_dry_run_bind_authorization_gate_review_id,
            "source_gate_review_hash": source.live_adapter_dry_run_bind_authorization_gate_review_hash,
            "execution_intent_id": source.execution_intent_id,
            "execution_intent_hash": source.execution_intent_hash,
            "adapter_contract_id": source.adapter_contract_id,
            "adapter_contract_hash": source.adapter_contract_hash,
            "endpoint_identity_binding_digest": source.endpoint_identity_binding_digest,
            "credential_reference_digest": source.credential_reference_digest,
            "credential_scope_binding_digest": source.credential_scope_binding_digest,
            "policy_snapshot_id": source.execution_intent["policy_snapshot_id"],
            "valid_from": _timestamp(valid_from),
            "valid_until": _timestamp(valid_until),
            "authorizer_id": authorizer_identity,
            "authorizer_role": "bind-authorizer",
            "authorizer_attestation": "I authorize only this exact future Bind attempt.",
            "authorized_at": _timestamp(AUTHORIZED_AT),
            "authorization_reason": "verified governance and explicit GO",
            "explicit_go_no_go_confirmation": "GO_AUTHORIZED",
            **{field: True for field in ACKNOWLEDGEMENTS},
        }
    )
    artifact = {
        "artifact_type": AUTHORIZER_ARTIFACT_TYPE,
        "artifact_version": AUTHORIZER_ARTIFACT_VERSION,
        "decision": decision.model_dump(mode="json"),
        "decision_hash": _decision_hash(decision),
        "signer": {
            "key_id": "bind-authorizer-key",
            "algorithm": "Ed25519",
            "identity": authorizer_identity,
            "role": "bind-authorizer",
        },
        "signed_at": _timestamp(AUTHORIZED_AT),
    }
    artifact["signature"] = base64.urlsafe_b64encode(
        private_key.sign(
            bind_authorizer_decision_signature_payload(artifact).encode("utf-8")
        )
    ).decode("ascii")
    return artifact


def _build(*, human_required: bool = False):
    governance = _governance_inputs(human_required=human_required)
    private_key, trust, issuer_signer = _bind_signature_setup()
    artifact = build_live_adapter_bind_authorization_artifact(
        source_packet(),
        _signed_decision(private_key),
        VALID_FROM,
        VALID_UNTIL,
        governance_inputs=governance,
        trust_inputs=trust,
        authorization_issuer_signer=issuer_signer,
    )
    return artifact, governance, trust


def test_real_authorization_issues_without_bind_invocation(monkeypatch):
    monkeypatch.setenv("VERITAS_POSTURE", "secure")
    artifact, governance, trust = _build()
    assert artifact.bind_authorization_state == "AUTHORIZED"
    assert artifact.human_approval_requirement_status == "NOT_REQUIRED"
    assert artifact.runtime_authority_status == "pass"
    assert artifact.runtime_authority_recommended_outcome == "commit"
    assert artifact.authorization_consumption_state == "NOT_CONSUMED"
    assert artifact.bind_invocation_state == "NOT_INVOKED"
    assert artifact.execution_state == "NOT_EXECUTED"
    assert len(artifact.authorization_requirement_proofs) == 11
    assert all(
        not getattr(artifact, field)
        for field in (
            "bind_invoked",
            "bind_receipt_created",
            "trustlog_written",
            "request_dispatched",
            "credential_material_accessed",
            "authorization_header_constructed",
            "network_used",
            "webhook_called",
            "operation_committed",
        )
    )
    assert verify_live_adapter_bind_authorization_artifact(
        artifact, governance_inputs=governance, trust_inputs=trust
    ) == artifact


def test_required_signed_human_approval_is_verified(monkeypatch):
    monkeypatch.setenv("VERITAS_POSTURE", "secure")
    artifact, governance, trust = _build(human_required=True)
    assert artifact.human_approval_requirement_status == "VERIFIED"
    assert artifact.signed_human_approval_artifact is not None
    assert artifact.human_approval_verification_proof_digest
    assert verify_live_adapter_bind_authorization_artifact(
        artifact, governance_inputs=governance, trust_inputs=trust
    ) == artifact


def test_gate_reviewer_cannot_be_bind_authorizer(monkeypatch):
    monkeypatch.setenv("VERITAS_POSTURE", "secure")
    governance = _governance_inputs()
    private_key, trust, issuer_signer = _bind_signature_setup(
        authorizer_identity="operator:alice"
    )
    with pytest.raises(
        LiveAdapterBindAuthorizationError,
        match="LABA_REVIEWER_AUTHORIZER_SEPARATION_VIOLATION",
    ):
        build_live_adapter_bind_authorization_artifact(
            source_packet(),
            _signed_decision(private_key, authorizer_identity="operator:alice"),
            VALID_FROM,
            VALID_UNTIL,
            governance_inputs=governance,
            trust_inputs=trust,
            authorization_issuer_signer=issuer_signer,
        )


def test_same_ids_but_swapped_authorizer_key_is_rejected(monkeypatch):
    monkeypatch.setenv("VERITAS_POSTURE", "secure")
    legitimate_key = Ed25519PrivateKey.generate()
    attacker_key = Ed25519PrivateKey.generate()
    _, legitimate_trust, issuer_signer = _bind_signature_setup(
        authorizer_private_key=legitimate_key
    )
    attacker_verifier = TrustedEd25519BindAuthorizationVerifier(
        {"bind-authorizer-key": attacker_key.public_key().public_bytes_raw()},
        {"bind-authorizer-key": "operator:bob"},
        {"bind-authorizer-key": "bind-authorizer"},
        "bind-authorizer-verifier",
        "authorizer_decision",
    )
    assert attacker_verifier.policy_hash() != (
        legitimate_trust.authorizer_signature_verifier.policy_hash()
    )
    attack_trust = BindAuthorizationTrustInputs(
        authorizer_signature_verifier=attacker_verifier,
        authorizer_signer_policy=legitimate_trust.authorizer_signer_policy,
        authorizer_verifier_policy=legitimate_trust.authorizer_verifier_policy,
        authorization_issuer_signature_verifier=(
            legitimate_trust.authorization_issuer_signature_verifier
        ),
        authorization_issuer_signer_policy=(
            legitimate_trust.authorization_issuer_signer_policy
        ),
        authorization_issuer_verifier_policy=(
            legitimate_trust.authorization_issuer_verifier_policy
        ),
    )
    governance = _governance_inputs()
    with pytest.raises(LiveAdapterBindAuthorizationError):
        build_live_adapter_bind_authorization_artifact(
            source_packet(),
            _signed_decision(attacker_key),
            VALID_FROM,
            VALID_UNTIL,
            governance_inputs=governance,
            trust_inputs=attack_trust,
            authorization_issuer_signer=issuer_signer,
        )


def test_generic_required_evidence_without_first_class_proof_fails_closed(monkeypatch):
    monkeypatch.setenv("VERITAS_POSTURE", "secure")
    governance = _governance_inputs(required_evidence=["external_fact"])
    private_key, trust, issuer_signer = _bind_signature_setup()
    with pytest.raises(
        LiveAdapterBindAuthorizationError,
        match="LABA_REQUIRED_EVIDENCE_PROOF_UNAVAILABLE",
    ):
        build_live_adapter_bind_authorization_artifact(
            source_packet(),
            _signed_decision(private_key),
            VALID_FROM,
            VALID_UNTIL,
            governance_inputs=governance,
            trust_inputs=trust,
            authorization_issuer_signer=issuer_signer,
        )


def test_tampered_artifact_rejected_even_after_outer_rehash(monkeypatch):
    monkeypatch.setenv("VERITAS_POSTURE", "secure")
    artifact, governance, trust = _build()
    raw = deepcopy(artifact.model_dump(mode="json"))
    raw["credential_resolution_grant"]["policy_snapshot_id"] = "tampered"
    digest = _artifact_hash(raw)
    raw["live_adapter_bind_authorization_hash"] = digest
    raw["live_adapter_bind_authorization_id"] = f"laba:v1:sha256:{digest}"
    with pytest.raises(LiveAdapterBindAuthorizationError):
        verify_live_adapter_bind_authorization_artifact(
            raw, governance_inputs=governance, trust_inputs=trust
        )


def test_temporal_boundary_rejects_expired_authorization(monkeypatch):
    monkeypatch.setenv("VERITAS_POSTURE", "secure")
    artifact, governance, trust = _build()
    with pytest.raises(LiveAdapterBindAuthorizationError, match="LABA_NOT_CURRENTLY_VALID"):
        validate_live_adapter_bind_authorization_temporal_validity(
            artifact,
            now=VALID_UNTIL,
            governance_inputs=governance,
            trust_inputs=trust,
        )


def test_failed_gate_review_cannot_be_upgraded(monkeypatch):
    monkeypatch.setenv("VERITAS_POSTURE", "secure")
    failed = source_packet(decision=gate_decision(passed=False))
    governance = _governance_inputs()
    private_key, trust, issuer_signer = _bind_signature_setup()
    with pytest.raises(LiveAdapterBindAuthorizationError, match="LABA_SOURCE_NOT_AUTHORIZABLE"):
        build_live_adapter_bind_authorization_artifact(
            failed,
            _signed_decision(private_key, source=failed),
            VALID_FROM,
            VALID_UNTIL,
            governance_inputs=governance,
            trust_inputs=trust,
            authorization_issuer_signer=issuer_signer,
        )


def test_modules_do_not_import_or_call_effectful_bind_runtime():
    modules = [
        Path("veritas_os/policy/live_adapter_bind_authorization.py"),
        Path("veritas_os/policy/live_adapter_bind_authorization_contracts.py"),
        Path("veritas_os/policy/live_adapter_bind_authorization_models.py"),
        Path("veritas_os/policy/live_adapter_bind_authorization_codec.py"),
        Path("veritas_os/policy/live_adapter_bind_authorization_governance.py"),
        Path("veritas_os/policy/live_adapter_bind_authorization_checks.py"),
        Path("veritas_os/policy/live_adapter_bind_authorization_requirements.py"),
        Path("veritas_os/policy/live_adapter_bind_authorization_issuance.py"),
        Path("veritas_os/policy/live_adapter_bind_authorization_verification.py"),
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in modules)
    for prohibited in (
        "execute_bind_adjudication",
        "execute_bind_boundary",
        "WebhookBindAdapter",
        "ReferenceBindAdapter",
        "BindReceipt(",
        "TrustLog(",
        "resolve_credentials",
        "construct_authorization_header(",
        "requests.",
        "httpx.",
        "socket.",
        "subprocess.",
        "os.environ",
    ):
        assert prohibited not in text
