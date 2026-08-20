"""Tests for AuthorityEvidence first-class governance artifact."""

from __future__ import annotations

import base64
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from veritas_os.api.schemas import TrustLog
from veritas_os.governance.authority_evidence import (
    AuthorityEvidence,
    ApprovedAuthorityEvidenceVerifier,
    AuthorityEvidenceVerifierPolicy,
    AuthorityEvidenceSignerPolicy,
    AuthorityRevocationPolicy,
    AuthorityRevocationVerificationResult,
    authority_signature_payload,
    VerificationResult,
    is_scope_granting,
    validate_authority_evidence,
    verify_authority_evidence_artifact_to_proof,
)
from veritas_os.governance.authority_evidence_signing import (
    TrustedEd25519AuthorityVerifier,
)
from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.governance.runtime_authority import RuntimeAuthorityValidator


def _build_valid_authority_evidence(**overrides: object) -> AuthorityEvidence:
    base = {
        "authority_evidence_id": "aev-001",
        "action_contract_id": "aml_kyc_customer_risk_escalation",
        "action_contract_version": "1.0.0",
        "actor_identity": "operator:alice",
        "actor_role": "aml_reviewer",
        "authority_source_refs": ["contract:aml_kyc_customer_risk_escalation.v1"],
        "role_or_policy_basis": ["role:aml_reviewer", "policy:customer_risk_escalation"],
        "scope_grants": ["customer:risk_escalation", "customer:case_note"],
        "scope_limitations": ["customer:fund_transfer"],
        "validity_window": {
            "issued_at": "2026-04-25T00:00:00+00:00",
            "valid_from": "2026-04-25T00:00:00+00:00",
            "valid_until": "2026-04-30T00:00:00+00:00",
        },
        "issued_at": "2026-04-25T00:00:00+00:00",
        "valid_from": "2026-04-25T00:00:00+00:00",
        "valid_until": "2026-04-30T00:00:00+00:00",
        "revalidated_at": "2026-04-26T00:00:00+00:00",
        "policy_snapshot_id": "policy-snapshot-001",
        "evidence_hash": "",
        "verification_result": VerificationResult.VALID,
        "failure_reasons": [],
        "metadata": {"issuer": "governance-control-plane", "tier": "high"},
    }
    base.update(overrides)
    return AuthorityEvidence(**base)


def test_valid_authority_evidence_is_validated() -> None:
    artifact = _build_valid_authority_evidence()

    result = validate_authority_evidence(
        artifact,
        policy_snapshot_required=True,
        now=datetime.fromisoformat("2026-04-26T00:00:00+00:00"),
    )

    assert result.is_valid is True
    assert result.failure_reasons == []


def test_deterministic_hash_is_stable() -> None:
    artifact_one = _build_valid_authority_evidence()
    artifact_two = _build_valid_authority_evidence(
        metadata={"tier": "high", "issuer": "governance-control-plane"}
    )

    assert artifact_one.deterministic_serialization() == artifact_two.deterministic_serialization()
    assert artifact_one.deterministic_digest() == artifact_two.deterministic_digest()


def test_expired_authority_is_invalid() -> None:
    artifact = _build_valid_authority_evidence(valid_until="2026-04-20T00:00:00+00:00")

    result = validate_authority_evidence(
        artifact,
        now=datetime.fromisoformat("2026-04-26T00:00:00+00:00"),
    )

    assert result.is_valid is False
    assert "authority_expired" in result.failure_reasons


def test_missing_authority_source_is_invalid() -> None:
    artifact = _build_valid_authority_evidence(authority_source_refs=[])

    result = validate_authority_evidence(artifact)

    assert result.is_valid is False
    assert "authority_source_refs_missing" in result.failure_reasons


def test_missing_actor_identity_is_invalid() -> None:
    artifact = _build_valid_authority_evidence(actor_identity="")

    result = validate_authority_evidence(artifact)

    assert result.is_valid is False
    assert "actor_identity_missing" in result.failure_reasons


def test_indeterminate_authority_is_invalid() -> None:
    artifact = _build_valid_authority_evidence(
        verification_result=VerificationResult.INDETERMINATE
    )

    result = validate_authority_evidence(artifact)

    assert result.is_valid is False
    assert "verification_result_indeterminate" in result.failure_reasons


def test_missing_policy_snapshot_is_invalid_when_required() -> None:
    artifact = _build_valid_authority_evidence(policy_snapshot_id="")

    result = validate_authority_evidence(artifact, policy_snapshot_required=True)

    assert result.is_valid is False
    assert "policy_snapshot_id_missing" in result.failure_reasons


def test_scope_grants_are_expressed() -> None:
    artifact = _build_valid_authority_evidence()

    assert is_scope_granting(artifact, "customer:risk_escalation") is True


def test_scope_limitations_are_expressed() -> None:
    artifact = _build_valid_authority_evidence()

    assert is_scope_granting(artifact, "customer:fund_transfer") is False


def test_audit_log_entry_alone_is_not_authority_evidence() -> None:
    trust_log_entry = TrustLog(
        request_id="req-001",
        created_at="2026-04-26T00:00:00+00:00",
        sources=["aml_case"],
        critics=["fuji_gate"],
        checks=["admissibility"],
    )

    assert isinstance(trust_log_entry, TrustLog)
    assert not isinstance(trust_log_entry, AuthorityEvidence)

    result = validate_authority_evidence(None)

    assert result.is_valid is False
    assert "authority_evidence_missing" in result.failure_reasons


def test_authority_evidence_has_own_hash_and_verification_result() -> None:
    artifact = _build_valid_authority_evidence(verification_result=VerificationResult.VALID)

    digest = artifact.deterministic_digest()

    assert digest
    assert len(digest) == 64
    assert artifact.verification_result == VerificationResult.VALID


def test_naive_time_is_deterministically_rejected() -> None:
    result = validate_authority_evidence(
        _build_valid_authority_evidence(valid_from="2026-04-25T00:00:00"),
        now=datetime(2026, 4, 26, tzinfo=UTC),
    )
    assert result.is_valid is False
    assert "valid_from_invalid_timezone_required" in result.failure_reasons


class _NotRevoked:
    def check(self, authority_evidence_id: str, *, now: datetime):
        return AuthorityRevocationVerificationResult(
            True, False, now.isoformat(), "revocation-control", "1", "a" * 64,
            "not_revoked",
        )


class _RevocationResultChecker:
    def __init__(self, result: AuthorityRevocationVerificationResult) -> None:
        self.result = result

    def check(self, authority_evidence_id: str, *, now: datetime):
        return self.result


def _contract() -> ActionClassContract:
    return ActionClassContract(
        id="aml_kyc_customer_risk_escalation", version="1.0.0", domain="aml",
        action_class="customer_risk_escalation", description="test",
        declared_intent="test", allowed_scope=["customer:risk_escalation"],
        prohibited_scope=["customer:fund_transfer"], authority_sources=["policy"],
        required_evidence=[], evidence_freshness={},
        irreversibility={"boundary": "dispatch"}, human_approval_rules={},
        refusal_conditions=[], escalation_conditions=[],
        default_failure_mode="fail_closed", metadata={"regulated": True},
    )


def _signed_authority_artifact():
    contract = _contract()
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes_raw()
    evidence = _build_valid_authority_evidence(
        action_contract_hash=contract.deterministic_digest(),
        verification_result=VerificationResult.INVALID,
    )
    claims = evidence.claims_dict()
    from veritas_os.security.hash import sha256_of_canonical_json
    claims_hash = sha256_of_canonical_json(claims)
    artifact = {
        "artifact_type": "authority_evidence", "artifact_version": "v1",
        "claims": claims, "claims_hash": claims_hash,
        "signer": {"key_id": "authority-key-1", "algorithm": "Ed25519"},
        "issuer_identity": "governance-control-plane",
        "signed_at": "2026-04-25T00:00:00+00:00",
    }
    artifact["signature"] = base64.urlsafe_b64encode(
        private.sign(authority_signature_payload(artifact).encode())
    ).decode()
    verifier = TrustedEd25519AuthorityVerifier(
        {"authority-key-1": public},
        {"authority-key-1": "governance-control-plane"}, "verifier-1",
    )
    policy = AuthorityEvidenceSignerPolicy(
        "issuer-policy-1", ["authority-key-1"], ["Ed25519"],
        ["governance-control-plane"],
    )
    return artifact, contract, verifier, policy


def _deployment_policy(verifier, signer_policy):
    return AuthorityEvidenceVerifierPolicy([
        ApprovedAuthorityEvidenceVerifier(
            verifier_id=verifier.verifier_id,
            trust_level=verifier.trust_level,
            verifier_key_id="authority-key-1",
            verifier_policy_id=verifier.verifier_policy_id,
            verifier_policy_hash=verifier.policy_hash(),
            approved_signer_policies={
                signer_policy.policy_id: signer_policy.deterministic_hash()
            },
        )
    ])


def _proof_and_policy():
    artifact, contract, verifier, policy = _signed_authority_artifact()
    verifier_policy = _deployment_policy(verifier, policy)
    revocation_policy = AuthorityRevocationPolicy(3600, ["revocation-control"])
    proof = verify_authority_evidence_artifact_to_proof(
        artifact,
        action_contract=contract,
        actor_identity="operator:alice",
        requested_scope=["customer:risk_escalation"],
        policy_snapshot_id="policy-snapshot-001",
        signature_verifier=verifier,
        signer_policy=policy,
        verifier_policy=verifier_policy,
        revocation_checker=_NotRevoked(),
        revocation_policy=revocation_policy,
        now=datetime(2026, 4, 26, tzinfo=UTC),
    )
    return proof, contract, verifier_policy, revocation_policy


def test_real_ed25519_verification_emits_sealed_proof() -> None:
    artifact, contract, verifier, policy = _signed_authority_artifact()
    proof = verify_authority_evidence_artifact_to_proof(
        artifact, action_contract=contract, actor_identity="operator:alice",
        requested_scope=["customer:risk_escalation"],
        policy_snapshot_id="policy-snapshot-001", signature_verifier=verifier,
        signer_policy=policy, revocation_checker=_NotRevoked(),
        revocation_policy=AuthorityRevocationPolicy(
            3600, ["revocation-control"]
        ),
        now=datetime(2026, 4, 26, tzinfo=UTC),
    )
    assert proof.verification_proof_hash
    assert proof.authority_evidence.verification_result == VerificationResult.INDETERMINATE


def test_attacker_artifact_key_and_forged_flags_do_not_establish_trust() -> None:
    artifact, contract, verifier, policy = _signed_authority_artifact()
    attacker = Ed25519PrivateKey.generate()
    artifact["public_key"] = base64.urlsafe_b64encode(
        attacker.public_key().public_bytes_raw()
    ).decode()
    artifact["signature_verified"] = True
    artifact["not_revoked"] = True
    artifact["signature"] = base64.urlsafe_b64encode(
        attacker.sign(authority_signature_payload(artifact).encode())
    ).decode()
    with pytest.raises(ValueError, match="authority_signature_invalid"):
        verify_authority_evidence_artifact_to_proof(
            artifact, action_contract=contract, actor_identity="operator:alice",
            requested_scope=["customer:risk_escalation"],
            policy_snapshot_id="policy-snapshot-001", signature_verifier=verifier,
            signer_policy=policy, revocation_checker=_NotRevoked(),
            revocation_policy=AuthorityRevocationPolicy(
                3600, ["revocation-control"]
            ),
            now=datetime(2026, 4, 26, tzinfo=UTC),
        )


@pytest.mark.parametrize("posture", ["dev", "secure", "prod"])
def test_real_verified_authority_passes_runtime(monkeypatch, posture: str) -> None:
    proof, contract, verifier_policy, revocation_policy = _proof_and_policy()
    monkeypatch.setenv("VERITAS_POSTURE", posture)
    result = RuntimeAuthorityValidator().validate(
        action_contract=contract,
        authority_evidence=None,
        verified_authority_evidence=proof,
        authority_verifier_policy=verifier_policy,
        authority_revocation_policy=revocation_policy,
        requested_scope=["customer:risk_escalation"],
        required_evidence_metadata={},
        policy_snapshot_id="policy-snapshot-001",
        actor_identity="operator:alice",
        human_approval_state={"approved": False},
        bind_context_metadata={"session_id": "test"},
        now=datetime(2026, 4, 26, tzinfo=UTC),
    )
    assert result.status == "pass"
    assert result.recommended_outcome == "commit"


def test_signed_at_mutation_invalidates_signature() -> None:
    artifact, contract, verifier, policy = _signed_authority_artifact()
    artifact["signed_at"] = "2026-04-25T01:00:00+00:00"
    with pytest.raises(ValueError, match="authority_signature_invalid"):
        verify_authority_evidence_artifact_to_proof(
            artifact,
            action_contract=contract,
            actor_identity="operator:alice",
            requested_scope=["customer:risk_escalation"],
            policy_snapshot_id="policy-snapshot-001",
            signature_verifier=verifier,
            signer_policy=policy,
            revocation_checker=_NotRevoked(),
            revocation_policy=AuthorityRevocationPolicy(
                3600, ["revocation-control"]
            ),
            now=datetime(2026, 4, 26, tzinfo=UTC),
        )


@pytest.mark.parametrize("field", ["issued_at", "valid_from", "valid_until"])
def test_duplicated_validity_window_mismatch_fails(field: str) -> None:
    evidence = _build_valid_authority_evidence()
    window = dict(evidence.validity_window)
    window[field] = "2026-04-25T03:00:00+00:00"
    result = validate_authority_evidence(
        _build_valid_authority_evidence(validity_window=window),
        now=datetime(2026, 4, 26, tzinfo=UTC),
    )
    assert f"validity_window_{field}_mismatch" in result.failure_reasons


def test_contract_content_mutation_invalidates_proof() -> None:
    proof, contract, verifier_policy, revocation_policy = _proof_and_policy()
    mutated = ActionClassContract(
        **{**contract.to_dict(), "human_approval_rules": {"minimum_approvals": 2}}
    )
    from veritas_os.governance.authority_evidence import (
        validate_verified_authority_evidence,
    )
    result = validate_verified_authority_evidence(
        proof,
        action_contract=mutated,
        actor_identity="operator:alice",
        requested_scope=["customer:risk_escalation"],
        policy_snapshot_id="policy-snapshot-001",
        verifier_policy=verifier_policy,
        revocation_policy=revocation_policy,
        now=datetime(2026, 4, 26, tzinfo=UTC),
    )
    assert "authority_action_contract_hash_mismatch" in result.failure_reasons


@pytest.mark.parametrize(
    ("checked", "revoked", "checked_at", "reason"),
    [
        (False, False, "2026-04-26T00:00:00+00:00",
         "authority_revocation_not_checked"),
        (True, True, "2026-04-26T00:00:00+00:00", "authority_revoked"),
        (True, None, "2026-04-26T00:00:00+00:00",
         "authority_revocation_status_unknown"),
        (True, False, "2026-04-25T22:00:00+00:00",
         "authority_revocation_status_stale"),
        (True, False, "2026-04-26T00:01:00+00:00",
         "authority_revocation_checked_at_future"),
    ],
)
def test_revocation_states_fail_closed(
    checked: bool, revoked: bool | None, checked_at: str, reason: str
) -> None:
    artifact, contract, verifier, policy = _signed_authority_artifact()
    checker = _RevocationResultChecker(AuthorityRevocationVerificationResult(
        checked, revoked, checked_at, "revocation-control", "1", "a" * 64,
        "fixture",
    ))
    with pytest.raises(ValueError, match=reason):
        verify_authority_evidence_artifact_to_proof(
            artifact,
            action_contract=contract,
            actor_identity="operator:alice",
            requested_scope=["customer:risk_escalation"],
            policy_snapshot_id="policy-snapshot-001",
            signature_verifier=verifier,
            signer_policy=policy,
            revocation_checker=checker,
            revocation_policy=AuthorityRevocationPolicy(
                3600, ["revocation-control"]
            ),
            now=datetime(2026, 4, 26, tzinfo=UTC),
        )


def test_self_declared_production_verifier_cannot_bootstrap_prod(
    monkeypatch,
) -> None:
    artifact, contract, _, _ = _signed_authority_artifact()
    attacker = Ed25519PrivateKey.generate()
    artifact["signer"] = {"key_id": "attacker", "algorithm": "Ed25519"}
    artifact["issuer_identity"] = "attacker"
    artifact["signature"] = base64.urlsafe_b64encode(
        attacker.sign(authority_signature_payload(artifact).encode())
    ).decode()
    verifier = TrustedEd25519AuthorityVerifier(
        {"attacker": attacker.public_key().public_bytes_raw()},
        {"attacker": "attacker"},
        "attacker-verifier",
        trust_level="production",
    )
    signer_policy = AuthorityEvidenceSignerPolicy(
        "attacker-policy", ["attacker"], ["Ed25519"], ["attacker"]
    )
    revocation_policy = AuthorityRevocationPolicy(
        3600, ["revocation-control"]
    )
    proof = verify_authority_evidence_artifact_to_proof(
        artifact,
        action_contract=contract,
        actor_identity="operator:alice",
        requested_scope=["customer:risk_escalation"],
        policy_snapshot_id="policy-snapshot-001",
        signature_verifier=verifier,
        signer_policy=signer_policy,
        revocation_checker=_NotRevoked(),
        revocation_policy=revocation_policy,
        now=datetime(2026, 4, 26, tzinfo=UTC),
    )
    _, _, approved_policy, _ = _proof_and_policy()
    monkeypatch.setenv("VERITAS_POSTURE", "prod")
    result = RuntimeAuthorityValidator().validate(
        action_contract=contract,
        authority_evidence=None,
        verified_authority_evidence=proof,
        authority_verifier_policy=approved_policy,
        authority_revocation_policy=revocation_policy,
        requested_scope=["customer:risk_escalation"],
        required_evidence_metadata={},
        policy_snapshot_id="policy-snapshot-001",
        actor_identity="operator:alice",
        human_approval_state={"approved": False},
        bind_context_metadata={"session_id": "test"},
        now=datetime(2026, 4, 26, tzinfo=UTC),
    )
    assert result.status == "fail"
    assert result.recommended_outcome == "block"
