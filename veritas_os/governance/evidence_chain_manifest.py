"""Deterministic local/offline Evidence Chain Manifest v1 helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from veritas_os.security.hash import sha256_of_canonical_json

_ALLOWED_CHAIN_STATUS = {"complete", "incomplete", "blocked", "indeterminate"}
_BLOCKED_OUTCOMES = {"block", "blocked", "refuse", "refused"}
_COMMITTED_OUTCOMES = {"commit", "committed", "commit_eligible"}
_REQUIRED_COMPLETE_HASH_FIELDS = (
    "authority_evidence_hash",
    "human_approval_receipt_hash",
    "outcome_receipt_hash",
)


@dataclass(frozen=True)
class EvidenceChainManifest:
    """Deterministic local/offline evidence-chain manifest for one execution."""

    manifest_id: str
    decision_id: str
    execution_intent_id: str
    operation_id: str
    action_class: str
    target_system: str
    target_resource: str
    requested_scope: list[str]
    authority_evidence_id: str | None
    authority_evidence_hash: str | None
    human_approval_receipt_id: str | None
    human_approval_receipt_hash: str | None
    bind_receipt_id: str | None
    bind_receipt_hash: str | None
    outcome_receipt_id: str | None
    outcome_receipt_hash: str | None
    bind_coverage_operation_id: str | None
    final_outcome: str
    chain_status: str
    missing_links: list[str]
    refusal_basis: list[str]
    observed_effects_summary: list[dict[str, Any]]
    generated_at: str
    manifest_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return deterministic dictionary representation."""
        return {
            "manifest_id": self.manifest_id,
            "decision_id": self.decision_id,
            "execution_intent_id": self.execution_intent_id,
            "operation_id": self.operation_id,
            "action_class": self.action_class,
            "target_system": self.target_system,
            "target_resource": self.target_resource,
            "requested_scope": sorted(str(scope) for scope in self.requested_scope),
            "authority_evidence_id": self.authority_evidence_id,
            "authority_evidence_hash": self.authority_evidence_hash,
            "human_approval_receipt_id": self.human_approval_receipt_id,
            "human_approval_receipt_hash": self.human_approval_receipt_hash,
            "bind_receipt_id": self.bind_receipt_id,
            "bind_receipt_hash": self.bind_receipt_hash,
            "outcome_receipt_id": self.outcome_receipt_id,
            "outcome_receipt_hash": self.outcome_receipt_hash,
            "bind_coverage_operation_id": self.bind_coverage_operation_id,
            "final_outcome": self.final_outcome,
            "chain_status": self.chain_status,
            "missing_links": sorted(str(link) for link in self.missing_links),
            "refusal_basis": sorted(str(reason) for reason in self.refusal_basis),
            "observed_effects_summary": self.observed_effects_summary,
            "generated_at": self.generated_at,
            "manifest_hash": self.manifest_hash,
            "metadata": self.metadata,
        }

    def to_dict_for_hash(self) -> dict[str, Any]:
        """Return canonical hash payload excluding ``manifest_hash`` recursion."""
        payload = self.to_dict()
        payload.pop("manifest_hash", None)
        return payload

    def deterministic_digest(self) -> str:
        """Compute deterministic SHA-256 digest from canonical hash payload."""
        return sha256_of_canonical_json(self.to_dict_for_hash())


@dataclass(frozen=True)
class EvidenceChainManifestValidationResult:
    """Fail-closed validation output for an evidence-chain manifest."""

    is_valid: bool
    failure_reasons: list[str]


def with_manifest_hash(manifest: EvidenceChainManifest) -> EvidenceChainManifest:
    """Return a new manifest finalized with deterministic ``manifest_hash``."""
    data = manifest.to_dict()
    data["manifest_hash"] = manifest.deterministic_digest()
    return EvidenceChainManifest(**data)


def validate_evidence_chain_manifest(
    manifest: EvidenceChainManifest | None,
) -> EvidenceChainManifestValidationResult:
    """Validate manifest with deterministic fail-closed checks."""
    if manifest is None:
        return EvidenceChainManifestValidationResult(False, ["evidence_chain_manifest_missing"])

    failure_reasons: list[str] = []

    if not str(manifest.manifest_id).strip():
        failure_reasons.append("evidence_chain_manifest_id_missing")
    if not str(manifest.decision_id).strip():
        failure_reasons.append("evidence_chain_decision_id_missing")
    if not str(manifest.execution_intent_id).strip():
        failure_reasons.append("evidence_chain_execution_intent_id_missing")
    if not str(manifest.operation_id).strip():
        failure_reasons.append("evidence_chain_operation_id_missing")
    if not str(manifest.action_class).strip():
        failure_reasons.append("evidence_chain_action_class_missing")
    if not str(manifest.target_system).strip():
        failure_reasons.append("evidence_chain_target_system_missing")
    if not str(manifest.target_resource).strip():
        failure_reasons.append("evidence_chain_target_resource_missing")
    if not str(manifest.final_outcome).strip():
        failure_reasons.append("evidence_chain_final_outcome_missing")

    if manifest.chain_status not in _ALLOWED_CHAIN_STATUS:
        failure_reasons.append("evidence_chain_invalid_chain_status")

    if manifest.chain_status == "complete":
        for field_name in _REQUIRED_COMPLETE_HASH_FIELDS:
            if not str(getattr(manifest, field_name) or "").strip():
                failure_reasons.append("evidence_chain_complete_missing_required_hash")
                break
        if not str(manifest.bind_coverage_operation_id or "").strip():
            failure_reasons.append("evidence_chain_complete_missing_required_hash")
        if manifest.missing_links:
            failure_reasons.append("evidence_chain_complete_has_missing_links")

    normalized_outcome = str(manifest.final_outcome).strip().lower()
    if manifest.chain_status == "blocked":
        if normalized_outcome not in _BLOCKED_OUTCOMES:
            failure_reasons.append("evidence_chain_blocked_outcome_mismatch")
        if not [item for item in manifest.refusal_basis if str(item).strip()]:
            failure_reasons.append("evidence_chain_blocked_without_refusal_basis")

    generated_at_raw = str(manifest.generated_at).strip()
    if not generated_at_raw:
        failure_reasons.append("evidence_chain_generated_at_missing")
    elif _parse_iso_datetime(generated_at_raw) is None:
        failure_reasons.append("evidence_chain_generated_at_unparseable")

    if not str(manifest.manifest_hash).strip():
        failure_reasons.append("evidence_chain_manifest_hash_missing")

    return EvidenceChainManifestValidationResult(not failure_reasons, sorted(set(failure_reasons)))


def build_evidence_chain_manifest(
    *,
    decision_id: str,
    execution_intent_id: str,
    operation_id: str,
    action_class: str,
    target_system: str,
    target_resource: str,
    requested_scope: list[str],
    final_outcome: str,
    authority_evidence_id: str | None = None,
    authority_evidence_hash: str | None = None,
    human_approval_receipt_id: str | None = None,
    human_approval_receipt_hash: str | None = None,
    bind_receipt_id: str | None = None,
    bind_receipt_hash: str | None = None,
    outcome_receipt_id: str | None = None,
    outcome_receipt_hash: str | None = None,
    bind_coverage_operation_id: str | None = None,
    refusal_basis: list[str] | None = None,
    observed_effects_summary: list[dict[str, Any]] | None = None,
    generated_at: str,
    metadata: dict[str, Any] | None = None,
) -> EvidenceChainManifest:
    """Build a deterministic local/offline finalized EvidenceChainManifest."""
    missing_links: list[str] = []
    for label, value in (
        ("authority_evidence_hash", authority_evidence_hash),
        ("human_approval_receipt_hash", human_approval_receipt_hash),
        ("outcome_receipt_hash", outcome_receipt_hash),
        ("bind_coverage_operation_id", bind_coverage_operation_id),
    ):
        if not str(value or "").strip():
            missing_links.append(label)

    normalized_outcome = str(final_outcome).strip().lower()
    if normalized_outcome in _BLOCKED_OUTCOMES:
        chain_status = "blocked"
    elif normalized_outcome in _COMMITTED_OUTCOMES:
        chain_status = "complete" if not missing_links else "incomplete"
    elif normalized_outcome:
        chain_status = "incomplete" if missing_links else "indeterminate"
    else:
        chain_status = "indeterminate"

    manifest = EvidenceChainManifest(
        manifest_id=f"ecm-{operation_id}",
        decision_id=decision_id,
        execution_intent_id=execution_intent_id,
        operation_id=operation_id,
        action_class=action_class,
        target_system=target_system,
        target_resource=target_resource,
        requested_scope=list(requested_scope),
        authority_evidence_id=authority_evidence_id,
        authority_evidence_hash=authority_evidence_hash,
        human_approval_receipt_id=human_approval_receipt_id,
        human_approval_receipt_hash=human_approval_receipt_hash,
        bind_receipt_id=bind_receipt_id,
        bind_receipt_hash=bind_receipt_hash,
        outcome_receipt_id=outcome_receipt_id,
        outcome_receipt_hash=outcome_receipt_hash,
        bind_coverage_operation_id=bind_coverage_operation_id,
        final_outcome=final_outcome,
        chain_status=chain_status,
        missing_links=missing_links,
        refusal_basis=list(refusal_basis or []),
        observed_effects_summary=list(observed_effects_summary or []),
        generated_at=generated_at,
        manifest_hash="",
        metadata=dict(metadata or {}),
    )
    return with_manifest_hash(manifest)


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
