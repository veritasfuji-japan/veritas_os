"""Deterministic local/offline Evidence Chain Verifier v1.

The verifier compares an EvidenceChainManifest with supplied governance
artifacts without network access, credential use, live SaaS calls, or production
audit-store integration. It is intentionally minimal and additive for v1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from veritas_os.governance.evidence_chain_manifest import EvidenceChainManifest

_VERIFICATION_STATUSES = {"verified", "failed", "incomplete", "indeterminate"}
_HASH_FIELD_NAMES = (
    "evidence_hash",
    "receipt_hash",
    "outcome_hash",
    "manifest_hash",
    "bind_receipt_hash",
)


@dataclass(frozen=True)
class EvidenceChainVerificationResult:
    """Result of local/offline EvidenceChainManifest link verification."""

    is_valid: bool
    verification_status: str
    manifest_id: str | None
    decision_id: str | None
    execution_intent_id: str | None
    operation_id: str | None
    verified_links: list[str] = field(default_factory=list)
    missing_links: list[str] = field(default_factory=list)
    mismatched_links: list[str] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)
    recomputed_manifest_hash: str | None = None
    manifest_hash_matches: bool = False
    verified_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic JSON-friendly verification summary."""
        return {
            "is_valid": self.is_valid,
            "verification_status": self.verification_status,
            "manifest_id": self.manifest_id,
            "decision_id": self.decision_id,
            "execution_intent_id": self.execution_intent_id,
            "operation_id": self.operation_id,
            "verified_links": sorted(self.verified_links),
            "missing_links": sorted(self.missing_links),
            "mismatched_links": sorted(self.mismatched_links),
            "failure_reasons": sorted(self.failure_reasons),
            "recomputed_manifest_hash": self.recomputed_manifest_hash,
            "manifest_hash_matches": self.manifest_hash_matches,
            "verified_at": self.verified_at,
            "metadata": dict(self.metadata),
        }


def verify_evidence_chain_manifest(
    *,
    manifest: EvidenceChainManifest | None,
    authority_evidence: Any | None = None,
    human_approval_receipt: Any | None = None,
    outcome_receipt: Any | None = None,
    bind_coverage_operation_id: str | None = None,
    bind_receipt: Any | None = None,
    verified_at: str,
    metadata: dict[str, Any] | None = None,
) -> EvidenceChainVerificationResult:
    """Verify an EvidenceChainManifest against supplied local/offline artifacts.

    The function never performs network calls and never mutates supplied
    artifacts. It verifies only links claimed by the manifest, preserving the
    manifest's own ``missing_links`` for incomplete or blocked chains.
    """
    verified_links: list[str] = []
    missing_links: list[str] = []
    mismatched_links: list[str] = []
    failure_reasons: list[str] = []
    indeterminate_links: list[str] = []

    _validate_verified_at(verified_at, failure_reasons)

    if manifest is None:
        failure_reasons.append("evidence_chain_manifest_missing")
        status = "failed"
        return EvidenceChainVerificationResult(
            is_valid=False,
            verification_status=status,
            manifest_id=None,
            decision_id=None,
            execution_intent_id=None,
            operation_id=None,
            verified_links=[],
            missing_links=[],
            mismatched_links=[],
            failure_reasons=sorted(set(failure_reasons)),
            recomputed_manifest_hash=None,
            manifest_hash_matches=False,
            verified_at=verified_at,
            metadata=dict(metadata or {}),
        )

    missing_links.extend(str(link) for link in manifest.missing_links if str(link).strip())

    recomputed_manifest_hash = manifest.deterministic_digest()
    manifest_hash_matches = recomputed_manifest_hash == manifest.manifest_hash
    if manifest_hash_matches:
        verified_links.append("manifest_hash")
    else:
        mismatched_links.append("manifest_hash")
        failure_reasons.append("evidence_chain_manifest_hash_mismatch")

    _verify_hash_link(
        manifest_hash=manifest.authority_evidence_hash,
        artifact=authority_evidence,
        link_name="authority_evidence_hash",
        missing_reason="evidence_chain_authority_evidence_missing",
        mismatch_reason="evidence_chain_authority_evidence_hash_mismatch",
        indeterminate_reason="evidence_chain_authority_evidence_hash_indeterminate",
        verified_links=verified_links,
        missing_links=missing_links,
        mismatched_links=mismatched_links,
        indeterminate_links=indeterminate_links,
        failure_reasons=failure_reasons,
    )
    _verify_hash_link(
        manifest_hash=manifest.human_approval_receipt_hash,
        artifact=human_approval_receipt,
        link_name="human_approval_receipt_hash",
        missing_reason="evidence_chain_human_approval_receipt_missing",
        mismatch_reason="evidence_chain_human_approval_receipt_hash_mismatch",
        indeterminate_reason="evidence_chain_human_approval_receipt_hash_indeterminate",
        verified_links=verified_links,
        missing_links=missing_links,
        mismatched_links=mismatched_links,
        indeterminate_links=indeterminate_links,
        failure_reasons=failure_reasons,
    )
    _verify_hash_link(
        manifest_hash=manifest.outcome_receipt_hash,
        artifact=outcome_receipt,
        link_name="outcome_receipt_hash",
        missing_reason="evidence_chain_outcome_receipt_missing",
        mismatch_reason="evidence_chain_outcome_receipt_hash_mismatch",
        indeterminate_reason="evidence_chain_outcome_receipt_hash_indeterminate",
        verified_links=verified_links,
        missing_links=missing_links,
        mismatched_links=mismatched_links,
        indeterminate_links=indeterminate_links,
        failure_reasons=failure_reasons,
    )

    if str(manifest.bind_coverage_operation_id or "").strip():
        if not str(bind_coverage_operation_id or "").strip():
            missing_links.append("bind_coverage_operation_id")
            failure_reasons.append("evidence_chain_bind_coverage_operation_missing")
        elif bind_coverage_operation_id == manifest.bind_coverage_operation_id:
            verified_links.append("bind_coverage_operation_id")
        else:
            mismatched_links.append("bind_coverage_operation_id")
            failure_reasons.append("evidence_chain_bind_coverage_operation_mismatch")

    _verify_hash_link(
        manifest_hash=manifest.bind_receipt_hash,
        artifact=bind_receipt,
        link_name="bind_receipt_hash",
        missing_reason="evidence_chain_bind_receipt_missing",
        mismatch_reason="evidence_chain_bind_receipt_hash_mismatch",
        indeterminate_reason="evidence_chain_bind_receipt_hash_indeterminate",
        verified_links=verified_links,
        missing_links=missing_links,
        mismatched_links=mismatched_links,
        indeterminate_links=indeterminate_links,
        failure_reasons=failure_reasons,
    )

    unique_verified = sorted(set(verified_links))
    unique_missing = sorted(set(missing_links))
    unique_mismatched = sorted(set(mismatched_links))
    unique_failures = sorted(set(failure_reasons))
    status = _derive_status(
        manifest_exists=True,
        manifest_hash_matches=manifest_hash_matches,
        mismatched_links=unique_mismatched,
        failure_reasons=unique_failures,
        indeterminate_links=indeterminate_links,
    )

    return EvidenceChainVerificationResult(
        is_valid=status == "verified",
        verification_status=status,
        manifest_id=manifest.manifest_id,
        decision_id=manifest.decision_id,
        execution_intent_id=manifest.execution_intent_id,
        operation_id=manifest.operation_id,
        verified_links=unique_verified,
        missing_links=unique_missing,
        mismatched_links=unique_mismatched,
        failure_reasons=unique_failures,
        recomputed_manifest_hash=recomputed_manifest_hash,
        manifest_hash_matches=manifest_hash_matches,
        verified_at=verified_at,
        metadata=dict(metadata or {}),
    )


def _extract_artifact_hash(artifact: Any) -> str | None:
    """Return a deterministic artifact hash without mutating the artifact."""
    if artifact is None:
        return None

    deterministic_digest = getattr(artifact, "deterministic_digest", None)
    if callable(deterministic_digest):
        digest = deterministic_digest()
        return str(digest) if digest is not None else None

    for field_name in _HASH_FIELD_NAMES:
        if isinstance(artifact, dict):
            value = artifact.get(field_name)
        else:
            value = getattr(artifact, field_name, None)
        if value is not None:
            return str(value)

    return None


def _verify_hash_link(
    *,
    manifest_hash: str | None,
    artifact: Any | None,
    link_name: str,
    missing_reason: str,
    mismatch_reason: str,
    indeterminate_reason: str,
    verified_links: list[str],
    missing_links: list[str],
    mismatched_links: list[str],
    indeterminate_links: list[str],
    failure_reasons: list[str],
) -> None:
    if not str(manifest_hash or "").strip():
        return

    if artifact is None:
        missing_links.append(link_name)
        failure_reasons.append(missing_reason)
        return

    artifact_hash = _extract_artifact_hash(artifact)
    if not str(artifact_hash or "").strip():
        indeterminate_links.append(link_name)
        failure_reasons.append(indeterminate_reason)
        return

    if artifact_hash == manifest_hash:
        verified_links.append(link_name)
    else:
        mismatched_links.append(link_name)
        failure_reasons.append(mismatch_reason)


def _validate_verified_at(verified_at: str, failure_reasons: list[str]) -> None:
    if not str(verified_at or "").strip():
        failure_reasons.append("evidence_chain_verified_at_missing")
        return
    try:
        datetime.fromisoformat(str(verified_at))
    except ValueError:
        failure_reasons.append("evidence_chain_verified_at_unparseable")


def _derive_status(
    *,
    manifest_exists: bool,
    manifest_hash_matches: bool,
    mismatched_links: list[str],
    failure_reasons: list[str],
    indeterminate_links: list[str],
) -> str:
    if not manifest_exists:
        return "failed"
    if mismatched_links or not manifest_hash_matches:
        return "failed"
    verified_at_failures = {
        "evidence_chain_verified_at_missing",
        "evidence_chain_verified_at_unparseable",
    }
    if verified_at_failures.intersection(failure_reasons):
        return "failed"
    if indeterminate_links:
        return "indeterminate"
    if failure_reasons:
        return "incomplete"
    return "verified"


assert _VERIFICATION_STATUSES == {"verified", "failed", "incomplete", "indeterminate"}
