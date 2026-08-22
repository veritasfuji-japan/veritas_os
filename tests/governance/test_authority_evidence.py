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
    VerificationResult,
    is_scope_granting,
    validate_authority_evidence,
    validate_verified_authority_evidence,
    verify_authority_evidence_artifact_to_proof,
    authority_signature_payload,
)
from veritas_os.governance.authority_evidence_signing import (
    TrustedEd25519AuthorityVerifier,
)
from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.governance.runtime_authority import RuntimeAuthorityValidator
from veritas_os.governance.commit_boundary import CommitBoundaryEvaluator


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


def test_legacy_hash_identity_omits_absent_contract_hash() -> None:
    """Protect the historical AuthorityEvidence content address."""
    legacy = _build_valid_authority_evidence(action_contract_hash=None)
    historical_digest = (
        "d13ab3b174d68239d77a4f2cff8bfbfea8aa34aef54a08ac8d7a443220229dbd"
    )

    assert "action_contract_hash" not in legacy.to_dict_for_hash()
    assert legacy.deterministic_digest() == historical_digest

    first_bound = _build_valid_authority_evidence(action_contract_hash="a" * 64)
    second_bound = _build_valid_authority_evidence(action_contract_hash="b" * 64)
    assert first_bound.deterministic_digest() != historical_digest
    assert second_bound.deterministic_digest() != first_bound.deterministic_digest()


def test_expired_authority_is_invalid() -> None:
    expired_until = "2026-04-20T00:00:00+00:00"
    artifact = _build_valid_authority_evidence(
        valid_until=expired_until,
        validity_window={
            "issued_at": "2026-04-15T00:00:00+00:00",
            "valid_from": "2026-04-15T00:00:00+00:00",
            "valid_until": expired_until,
        },
        issued_at="2026-04-15T00:00:00+00:00",
        valid_from="2026-04-15T00:00:00+00:00",
    )

    result = validate_authority_evidence(
        artifact,
        now=datetime.fromisoformat("2026-04-26T00:00:00+00:00"),
    )

    assert result.is_valid is False
    assert "authority_expired" in result.failure_reasons


def test_redundant_validity_window_mismatch_is_invalid() -> None:
    artifact = _build_valid_authority_evidence(
        valid_until="2026-04-29T00:00:00+00:00"
    )
    result = validate_authority_evidence(
        artifact,
        now=datetime.fromisoformat("2026-04-26T00:00:00+00:00"),
    )
    assert "validity_window_fields_mismatch" in result.failure_reasons


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


def _signed_authority_artifact(
    *, signed_at: str = "2026-04-25T00:00:00+00:00"
):
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
        "signed_at": signed_at,
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


def test_authority_artifact_rejects_future_signed_at() -> None:
    """An artifact cannot claim it was signed after verification time."""
    artifact, contract, verifier, policy = _signed_authority_artifact(
        signed_at="2026-04-26T00:00:01+00:00"
    )

    with pytest.raises(ValueError, match="authority_signed_at_future"):
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
                60, ["revocation-control"]
            ),
            now=datetime(2026, 4, 26, tzinfo=UTC),
        )


def test_real_ed25519_verification_emits_sealed_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact, contract, verifier, policy = _signed_authority_artifact()
    proof = verify_authority_evidence_artifact_to_proof(
        artifact, action_contract=contract, actor_identity="operator:alice",
        requested_scope=["customer:risk_escalation"],
        policy_snapshot_id="policy-snapshot-001", signature_verifier=verifier,
        signer_policy=policy, revocation_checker=_NotRevoked(),
        revocation_policy=AuthorityRevocationPolicy(
            60, ["revocation-control"]
        ),
        now=datetime(2026, 4, 26, tzinfo=UTC),
    )
    assert proof.verification_proof_hash
    assert proof.authority_evidence.verification_result == VerificationResult.INDETERMINATE
    deployment_policy = AuthorityEvidenceVerifierPolicy([
        ApprovedAuthorityEvidenceVerifier(
            verifier_id="verifier-1",
            trust_level="production",
            verifier_key_id="authority-key-1",
            verifier_policy_id="authority-verifier-v1",
            verifier_policy_hash=verifier.policy_hash(),
            signer_policy_id=policy.policy_id,
            signer_policy_hash=policy.deterministic_hash(),
        )
    ])
    validation = validate_verified_authority_evidence(
        proof,
        action_contract=contract,
        actor_identity="operator:alice",
        requested_scope=["customer:risk_escalation"],
        policy_snapshot_id="policy-snapshot-001",
        verifier_policy=deployment_policy,
        revocation_policy=AuthorityRevocationPolicy(
            60, ["revocation-control"]
        ),
        now=datetime(2026, 4, 26, tzinfo=UTC),
        require_production_verifier=True,
    )
    assert validation.is_valid is True
    runtime_result = RuntimeAuthorityValidator().validate(
        action_contract=contract,
        authority_evidence=None,
        verified_authority_evidence=proof,
        authority_verifier_policy=deployment_policy,
        authority_revocation_policy=AuthorityRevocationPolicy(
            60, ["revocation-control"]
        ),
        requested_scope=["customer:risk_escalation"],
        required_evidence_metadata={},
        policy_snapshot_id="policy-snapshot-001",
        actor_identity="operator:alice",
        human_approval_state={"approved": False},
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 4, 26, tzinfo=UTC),
    )
    assert runtime_result.status == "pass"
    assert any(
        predicate.predicate_type == "authority_valid"
        and predicate.status == "pass"
        for predicate in runtime_result.passed_predicates
    )
    monkeypatch.setenv("VERITAS_POSTURE", "prod")
    boundary_result = CommitBoundaryEvaluator().evaluate(
        execution_intent={"admissible": True},
        action_contract=contract,
        authority_evidence=None,
        verified_authority_evidence=proof,
        authority_verifier_policy=deployment_policy,
        authority_revocation_policy=AuthorityRevocationPolicy(
            60, ["revocation-control"]
        ),
        requested_scope=["customer:risk_escalation"],
        required_evidence_metadata={},
        evidence_freshness_metadata={},
        policy_snapshot_id="policy-snapshot-001",
        actor_identity="operator:alice",
        human_approval_state={"approved": False},
        bind_context_metadata={"session_id": "bind-001"},
        now=datetime(2026, 4, 26, tzinfo=UTC),
    )
    assert boundary_result.commit_boundary_result == "commit"
    assert boundary_result.authority_evidence_id == "aev-001"
    assert boundary_result.authority_evidence_hash == proof.authority_evidence.evidence_hash


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
                60, ["revocation-control"]
            ),
            now=datetime(2026, 4, 26, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("claims_hash", "0" * 64),
        ("signed_at", "2026-04-25T00:00:01+00:00"),
        ("artifact_type", "other"),
        ("artifact_version", "v2"),
    ],
)
def test_security_envelope_tampering_invalidates_signature(
    field: str, value: str
) -> None:
    artifact, _, verifier, _ = _signed_authority_artifact()
    artifact[field] = value
    assert verifier.verify(artifact).verified is False


def test_verifier_policy_hash_binds_public_key_material_stably() -> None:
    """A key swap under an unchanged key ID must change policy identity."""
    legitimate_key = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
    attacker_key = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
    common = {
        "trusted_issuers": {"key-b": "issuer-b", "key-a": "issuer-a"},
        "verifier_id": "verifier-1",
        "trust_level": "production",
        "verifier_policy_id": "policy-1",
    }
    legitimate = TrustedEd25519AuthorityVerifier(
        trusted_public_keys={"key-a": legitimate_key, "key-b": attacker_key},
        **common,
    )
    reordered = TrustedEd25519AuthorityVerifier(
        trusted_public_keys={"key-b": attacker_key, "key-a": legitimate_key},
        trusted_issuers={"key-a": "issuer-a", "key-b": "issuer-b"},
        verifier_id="verifier-1",
        trust_level="production",
        verifier_policy_id="policy-1",
    )
    swapped = TrustedEd25519AuthorityVerifier(
        trusted_public_keys={"key-a": attacker_key, "key-b": attacker_key},
        **common,
    )
    remapped_issuer = TrustedEd25519AuthorityVerifier(
        trusted_public_keys={"key-a": legitimate_key, "key-b": attacker_key},
        trusted_issuers={"key-a": "issuer-attacker", "key-b": "issuer-b"},
        verifier_id="verifier-1",
        trust_level="production",
        verifier_policy_id="policy-1",
    )

    assert legitimate.policy_hash() == reordered.policy_hash()
    assert legitimate.policy_hash() != swapped.policy_hash()
    assert legitimate.policy_hash() != remapped_issuer.policy_hash()
    assert legitimate_key.hex() not in legitimate.policy_hash()


def test_deployment_policy_rejects_same_id_attacker_key() -> None:
    """An attacker-valid signature cannot satisfy the pinned deployment hash."""
    contract = _contract()
    legitimate_private = Ed25519PrivateKey.generate()
    attacker_private = Ed25519PrivateKey.generate()
    common = {
        "trusted_issuers": {"authority-key-1": "governance-control-plane"},
        "verifier_id": "verifier-1",
        "trust_level": "production",
        "verifier_policy_id": "authority-verifier-v1",
    }
    legitimate = TrustedEd25519AuthorityVerifier(
        trusted_public_keys={
            "authority-key-1": legitimate_private.public_key().public_bytes_raw()
        },
        **common,
    )
    attacker = TrustedEd25519AuthorityVerifier(
        trusted_public_keys={
            "authority-key-1": attacker_private.public_key().public_bytes_raw()
        },
        **common,
    )
    evidence = _build_valid_authority_evidence(
        action_contract_hash=contract.deterministic_digest(),
        verification_result=VerificationResult.INVALID,
    )
    claims = evidence.claims_dict()
    from veritas_os.security.hash import sha256_of_canonical_json

    artifact = {
        "artifact_type": "authority_evidence",
        "artifact_version": "v1",
        "claims": claims,
        "claims_hash": sha256_of_canonical_json(claims),
        "signer": {"key_id": "authority-key-1", "algorithm": "Ed25519"},
        "issuer_identity": "governance-control-plane",
        "signed_at": "2026-04-25T00:00:00+00:00",
    }
    artifact["signature"] = base64.urlsafe_b64encode(
        attacker_private.sign(authority_signature_payload(artifact).encode())
    ).decode()
    signer_policy = AuthorityEvidenceSignerPolicy(
        "issuer-policy-1",
        ["authority-key-1"],
        ["Ed25519"],
        ["governance-control-plane"],
    )
    deployment_policy = AuthorityEvidenceVerifierPolicy(
        [
            ApprovedAuthorityEvidenceVerifier(
                verifier_id="verifier-1",
                trust_level="production",
                verifier_key_id="authority-key-1",
                verifier_policy_id="authority-verifier-v1",
                verifier_policy_hash=legitimate.policy_hash(),
                signer_policy_id=signer_policy.policy_id,
                signer_policy_hash=signer_policy.deterministic_hash(),
            )
        ]
    )

    assert attacker.verify(artifact).verified is True
    assert attacker.policy_hash() != legitimate.policy_hash()
    with pytest.raises(ValueError, match="authority_verifier_policy_mismatch"):
        verify_authority_evidence_artifact_to_proof(
            artifact,
            action_contract=contract,
            actor_identity="operator:alice",
            requested_scope=["customer:risk_escalation"],
            policy_snapshot_id="policy-snapshot-001",
            signature_verifier=attacker,
            signer_policy=signer_policy,
            verifier_policy=deployment_policy,
            revocation_checker=_NotRevoked(),
            revocation_policy=AuthorityRevocationPolicy(
                60, ["revocation-control"]
            ),
            now=datetime(2026, 4, 26, tzinfo=UTC),
        )
