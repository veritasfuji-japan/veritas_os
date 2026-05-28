"""Tests for deterministic local/offline Evidence Chain Verifier v1."""

from __future__ import annotations

from dataclasses import dataclass

from veritas_os.governance.evidence_chain_manifest import (
    EvidenceChainManifest,
    build_evidence_chain_manifest,
)
from veritas_os.governance.evidence_chain_verifier import (
    EvidenceChainVerificationResult,
    _extract_artifact_hash,
    verify_evidence_chain_manifest,
)

VERIFIED_AT = "2026-04-26T00:00:00+00:00"
AUTHORITY_HASH = "a" * 64
APPROVAL_HASH = "b" * 64
OUTCOME_HASH = "c" * 64


@dataclass(frozen=True)
class DigestArtifact:
    """Test artifact exposing a deterministic_digest method."""

    digest: str

    def deterministic_digest(self) -> str:
        """Return the configured deterministic digest."""
        return self.digest


class UnsupportedArtifact:
    """Test artifact with no deterministic hash surface."""


def _complete_manifest() -> EvidenceChainManifest:
    return build_evidence_chain_manifest(
        decision_id="decision-1",
        execution_intent_id="intent-1",
        operation_id="operation-1",
        action_class="permission_change",
        target_system="mock_saas",
        target_resource="user:alice",
        requested_scope=["saas:grant_admin"],
        final_outcome="commit",
        authority_evidence_id="aev-1",
        authority_evidence_hash=AUTHORITY_HASH,
        human_approval_receipt_id="har-1",
        human_approval_receipt_hash=APPROVAL_HASH,
        outcome_receipt_id="outcome-1",
        outcome_receipt_hash=OUTCOME_HASH,
        bind_coverage_operation_id="saas_permission_change_demo",
        generated_at=VERIFIED_AT,
        metadata={"fixture_only": True},
    )


def _verify_complete(**overrides: object) -> EvidenceChainVerificationResult:
    kwargs = {
        "manifest": _complete_manifest(),
        "authority_evidence": {"evidence_hash": AUTHORITY_HASH},
        "human_approval_receipt": {"receipt_hash": APPROVAL_HASH},
        "outcome_receipt": {"outcome_hash": OUTCOME_HASH},
        "bind_coverage_operation_id": "saas_permission_change_demo",
        "verified_at": VERIFIED_AT,
    }
    kwargs.update(overrides)
    return verify_evidence_chain_manifest(**kwargs)


def test_missing_manifest_fails_verification() -> None:
    result = verify_evidence_chain_manifest(manifest=None, verified_at=VERIFIED_AT)
    assert result.is_valid is False
    assert result.verification_status == "failed"
    assert "evidence_chain_manifest_missing" in result.failure_reasons


def test_valid_complete_chain_verifies_successfully() -> None:
    result = _verify_complete()
    assert result.is_valid is True
    assert result.verification_status == "verified"
    assert result.manifest_hash_matches is True
    assert result.verified_links == [
        "authority_evidence_hash",
        "bind_coverage_operation_id",
        "human_approval_receipt_hash",
        "manifest_hash",
        "outcome_receipt_hash",
    ]
    assert result.failure_reasons == []


def test_manifest_hash_mismatch_fails_verification() -> None:
    manifest = _complete_manifest()
    tampered_manifest = type(manifest)(**{**manifest.to_dict(), "manifest_hash": "x" * 64})
    result = _verify_complete(manifest=tampered_manifest)
    assert result.is_valid is False
    assert result.verification_status == "failed"
    assert "manifest_hash" in result.mismatched_links
    assert "evidence_chain_manifest_hash_mismatch" in result.failure_reasons


def test_authority_evidence_hash_mismatch_fails_verification() -> None:
    result = _verify_complete(authority_evidence={"evidence_hash": "x" * 64})
    assert result.verification_status == "failed"
    assert "authority_evidence_hash" in result.mismatched_links
    assert "evidence_chain_authority_evidence_hash_mismatch" in result.failure_reasons


def test_human_approval_receipt_hash_mismatch_fails_verification() -> None:
    result = _verify_complete(human_approval_receipt={"receipt_hash": "x" * 64})
    assert result.verification_status == "failed"
    assert "human_approval_receipt_hash" in result.mismatched_links
    assert "evidence_chain_human_approval_receipt_hash_mismatch" in result.failure_reasons


def test_outcome_receipt_hash_mismatch_fails_verification() -> None:
    result = _verify_complete(outcome_receipt={"outcome_hash": "x" * 64})
    assert result.verification_status == "failed"
    assert "outcome_receipt_hash" in result.mismatched_links
    assert "evidence_chain_outcome_receipt_hash_mismatch" in result.failure_reasons


def test_missing_authority_evidence_for_claimed_hash_is_not_verified() -> None:
    result = _verify_complete(authority_evidence=None)
    assert result.is_valid is False
    assert result.verification_status == "incomplete"
    assert "authority_evidence_hash" in result.missing_links
    assert "evidence_chain_authority_evidence_missing" in result.failure_reasons


def test_bind_coverage_operation_mismatch_fails_verification() -> None:
    result = _verify_complete(bind_coverage_operation_id="different_operation")
    assert result.verification_status == "failed"
    assert "bind_coverage_operation_id" in result.mismatched_links
    assert "evidence_chain_bind_coverage_operation_mismatch" in result.failure_reasons


def test_bind_coverage_operation_missing_is_not_verified() -> None:
    result = _verify_complete(bind_coverage_operation_id=None)
    assert result.is_valid is False
    assert result.verification_status == "incomplete"
    assert "bind_coverage_operation_id" in result.missing_links
    assert "evidence_chain_bind_coverage_operation_missing" in result.failure_reasons


def test_verified_at_missing_fails_verification() -> None:
    result = _verify_complete(verified_at="")
    assert result.is_valid is False
    assert result.verification_status == "failed"
    assert "evidence_chain_verified_at_missing" in result.failure_reasons


def test_verified_at_unparseable_fails_verification() -> None:
    result = _verify_complete(verified_at="not-a-date")
    assert result.is_valid is False
    assert result.verification_status == "failed"
    assert "evidence_chain_verified_at_unparseable" in result.failure_reasons


def test_extract_artifact_hash_supports_deterministic_digest() -> None:
    assert _extract_artifact_hash(DigestArtifact("d" * 64)) == "d" * 64


def test_extract_artifact_hash_supports_dict_hash_fields() -> None:
    assert _extract_artifact_hash({"receipt_hash": "r" * 64}) == "r" * 64
    assert _extract_artifact_hash({"outcome_hash": "o" * 64}) == "o" * 64


def test_extract_artifact_hash_returns_none_for_unsupported_artifacts() -> None:
    assert _extract_artifact_hash(UnsupportedArtifact()) is None
