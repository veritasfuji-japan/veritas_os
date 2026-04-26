"""Tests for AuthorityEvidence first-class governance artifact."""

from __future__ import annotations

from datetime import datetime

from veritas_os.api.schemas import TrustLog
from veritas_os.governance.authority_evidence import (
    AuthorityEvidence,
    VerificationResult,
    is_scope_granting,
    validate_authority_evidence,
)


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
            "issued_at": "2026-04-25T00:00:00",
            "valid_from": "2026-04-25T00:00:00",
            "valid_until": "2026-04-30T00:00:00",
        },
        "issued_at": "2026-04-25T00:00:00",
        "valid_from": "2026-04-25T00:00:00",
        "valid_until": "2026-04-30T00:00:00",
        "revalidated_at": "2026-04-26T00:00:00",
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
        now=datetime.fromisoformat("2026-04-26T00:00:00"),
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
    artifact = _build_valid_authority_evidence(valid_until="2026-04-20T00:00:00")

    result = validate_authority_evidence(
        artifact,
        now=datetime.fromisoformat("2026-04-26T00:00:00"),
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
        created_at="2026-04-26T00:00:00",
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
