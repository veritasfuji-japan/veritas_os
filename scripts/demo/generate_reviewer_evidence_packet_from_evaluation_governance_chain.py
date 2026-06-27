#!/usr/bin/env python3
"""Generate a reviewer packet from an offline Evaluation Governance chain.

This helper is intentionally local/offline and non-enforcing. It reads a chain
manifest produced by the Evaluation Governance offline chain runner, maps the
manifest's local artifact metadata into Reviewer Evidence Packet v1 attachment
entries, and emits a synthetic reviewer-facing packet. It does not call runtime
paths, does not dereference external artifact references, and does not establish
legitimacy or certify compliance.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEWER_PACKET_SCHEMA_PATH = (
    REPO_ROOT / "docs/en/demo/schemas/reviewer-evidence-packet-v1.schema.json"
)
REVIEWER_PACKET_TEMPLATE_PATH = (
    REPO_ROOT
    / "docs/en/demo/examples"
    / "reviewer-evidence-packet-with-evaluation-governance-v1.json"
)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.demo.reviewer_failure_reasons import (  # noqa: E402
    EVIDENCE_CHAIN_LIFECYCLE_SNAPSHOT_HASH_MISMATCH,
    EVIDENCE_CHAIN_MANIFEST_LIFECYCLE_SNAPSHOT_HASH_MISSING,
    EVIDENCE_CHAIN_OUTCOME_LIFECYCLE_SNAPSHOT_HASH_MISSING,
    REVIEWER_PACKET_VERIFICATION_PROOF_HASH_MISMATCH,
    REVIEWER_PACKET_VERIFIED_AT_MISMATCH,
    REVIEWER_PACKET_VERIFIER_ID_MISMATCH,
    REVIEWER_PACKET_VERIFIER_KEY_ID_MISMATCH,
    REVIEWER_PACKET_VERIFIER_POLICY_HASH_MISMATCH,
)
from scripts.demo.reviewer_key_provenance_metadata import key_provenance_metadata  # noqa: E402
from scripts.demo.verifier_lifecycle import (  # noqa: E402
    verifier_lifecycle_summary_from_human_approval,
)

SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")

ARTIFACT_TYPE_MAP = {
    "evaluation_receipt": "evaluation_receipt",
    "manifest_change_receipt": "manifest_change_receipt",
    "outcome_delta_attribution": "outcome_delta_attribution",
    "evaluation_drift_detection": "evaluation_drift_detection",
    "trajectory_admissibility_monitor": "trajectory_admissibility_monitor",
    "legitimacy_impact_review": "legitimacy_impact_review",
}

SCHEMA_REFS_BY_ARTIFACT_TYPE = {
    "evaluation_receipt": "docs/en/demo/schemas/evaluation-receipt-v1.schema.json",
    "manifest_change_receipt": (
        "docs/en/demo/schemas/manifest-change-receipt-v1.schema.json"
    ),
    "outcome_delta_attribution": (
        "docs/en/demo/schemas/outcome-delta-attribution-v1.schema.json"
    ),
    "evaluation_drift_detection": (
        "docs/en/demo/schemas/evaluation-drift-detection-v1.schema.json"
    ),
    "trajectory_admissibility_monitor": (
        "docs/en/demo/schemas/trajectory-admissibility-monitor-v1.schema.json"
    ),
    "legitimacy_impact_review": (
        "docs/en/demo/schemas/legitimacy-impact-review-v1.schema.json"
    ),
}

HUMAN_APPROVAL_SUMMARY_VERIFIER_FIELDS = (
    "verifier_id",
    "verifier_key_id",
    "verifier_policy_id",
    "verifier_policy_hash",
    "verification_proof_hash",
    "verified_at",
)
SYNTHETIC_VERIFIED_APPROVAL_VERIFIER_EVIDENCE = {
    "verifier_id": "veritas-human-approval-verifier-v1",
    "verifier_key_id": "local-demo-verifier-key",
    "verifier_policy_id": "human-approval-verifier-policy-v1",
    "verifier_policy_hash": (
        "b625a813408d3a1d6c55ff59e9661ac21c4a9017fda76e4369bd9407a743a2cd"
    ),
    "verification_proof_hash": (
        "4c5825bb7e0f647e705ca280a411695d052bfb8e65382f13804e86c0f485ef0c"
    ),
}

HUMAN_APPROVAL_CONTEXT_BINDING_FIELDS = (
    "request_ref",
    "ai_output_ref",
    "execution_intent_id",
    "decision_id",
    "action_class",
    "policy_snapshot_id",
    "authority_evidence_id",
    "bind_context_hash",
)

REVIEWER_NOTES = [
    (
        "This packet is a synthetic offline reviewer evidence packet generated "
        "from an Evaluation Governance offline chain manifest."
    ),
    (
        "Evaluation Governance artifacts are attached as optional reviewer "
        "evidence and are not runtime enforcement inputs."
    ),
    (
        "This helper does not call /v1/decide, change runtime admissibility, "
        "or introduce fail-closed behavior."
    ),
    (
        "This packet does not prove legitimacy, certify compliance, or include "
        "secrets, PII, customer data, or live external service data."
    ),
]

LIFECYCLE_HASH_FIELD = "human_approval_verifier_lifecycle_snapshot_hash"
LIFECYCLE_TAMPER_CASES = (
    (
        "lifecycle_snapshot_manifest_hash_outcome_missing",
        EVIDENCE_CHAIN_OUTCOME_LIFECYCLE_SNAPSHOT_HASH_MISSING,
        "Outcome metadata is missing the lifecycle snapshot hash while the "
        "manifest still carries it.",
    ),
    (
        "lifecycle_snapshot_outcome_hash_manifest_missing",
        EVIDENCE_CHAIN_MANIFEST_LIFECYCLE_SNAPSHOT_HASH_MISSING,
        "Manifest is missing the lifecycle snapshot hash while outcome "
        "metadata still carries it.",
    ),
    (
        "lifecycle_snapshot_hash_mismatch",
        EVIDENCE_CHAIN_LIFECYCLE_SNAPSHOT_HASH_MISMATCH,
        "Manifest and outcome metadata carry different lifecycle snapshot "
        "hash values.",
    ),
)
VERIFIER_CONTINUITY_TAMPER_CASES = (
    (
        "verifier_id_mismatch",
        REVIEWER_PACKET_VERIFIER_ID_MISMATCH,
        "human_approval_verifier_id",
        "verifier_id",
        "Human approval summary carries a different verifier identity than "
        "the manifest and outcome metadata.",
    ),
    (
        "verifier_key_id_mismatch",
        REVIEWER_PACKET_VERIFIER_KEY_ID_MISMATCH,
        "human_approval_verifier_key_id",
        "verifier_key_id",
        "Human approval summary carries a different verifier key identity "
        "than the manifest and outcome metadata.",
    ),
    (
        "verifier_policy_hash_mismatch",
        REVIEWER_PACKET_VERIFIER_POLICY_HASH_MISMATCH,
        "human_approval_verifier_policy_hash",
        "verifier_policy_hash",
        "Human approval summary carries a different verifier policy hash "
        "than the manifest and outcome metadata.",
    ),
    (
        "verification_proof_hash_mismatch",
        REVIEWER_PACKET_VERIFICATION_PROOF_HASH_MISMATCH,
        "verification_proof_hash",
        "verification_proof_hash",
        "Human approval summary carries a different proof hash than the "
        "manifest and outcome metadata.",
    ),
    (
        "verified_at_mismatch",
        REVIEWER_PACKET_VERIFIED_AT_MISMATCH,
        "verified_at",
        "verified_at",
        "Human approval summary carries a different verified_at timestamp "
        "than the lifecycle and evidence-chain verification summaries.",
    ),
)
TAMPERED_HEX = "3" * 64


def _jsonschema_module() -> Any | None:
    """Return the optional jsonschema module when available locally."""
    if importlib.util.find_spec("jsonschema") is None:
        return None

    import jsonschema

    return jsonschema


def load_json(path: Path) -> dict[str, Any]:
    """Load a local JSON object from ``path`` with clear helper errors."""
    if not path.is_file():
        raise FileNotFoundError(f"missing chain manifest or JSON file: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise TypeError(f"expected JSON object in {path}")
    return payload


def canonical_json_hash(payload: Any) -> str:
    """Return the SHA-256 digest of canonical JSON for local artifacts."""
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def map_artifact_type(chain_artifact_type: str) -> str:
    """Map a chain artifact type to a Reviewer Evidence Packet artifact type."""
    mapped_type = ARTIFACT_TYPE_MAP.get(chain_artifact_type)
    if mapped_type is None:
        supported = ", ".join(sorted(ARTIFACT_TYPE_MAP))
        raise ValueError(
            "unsupported Evaluation Governance chain artifact_type "
            f"{chain_artifact_type!r}; supported types: {supported}"
        )
    return mapped_type


def schema_ref_for_artifact_type(artifact_type: str) -> str:
    """Return the Reviewer Evidence Packet schema_ref for ``artifact_type``."""
    schema_ref = SCHEMA_REFS_BY_ARTIFACT_TYPE.get(artifact_type)
    if schema_ref is None:
        raise ValueError(f"no schema_ref mapping for artifact_type {artifact_type!r}")
    return schema_ref


def _is_external_ref(artifact_ref: str) -> bool:
    parsed = urlparse(artifact_ref)
    return bool(parsed.scheme and parsed.scheme not in {"", "file"})


def _local_artifact_path(artifact_base_dir: Path, artifact_ref: str) -> Path:
    """Return a safe local path for ``artifact_ref`` below artifact_base_dir."""
    artifact_path = Path(artifact_ref)
    if artifact_path.is_absolute():
        raise ValueError(
            f"artifact_ref must be relative for local hash computation: {artifact_ref}"
        )

    base = artifact_base_dir.resolve()
    candidate = (base / artifact_path).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise ValueError(
            f"artifact_ref escapes artifact_base_dir: {artifact_ref}"
        ) from exc
    return candidate


def _hash_local_artifact(artifact_base_dir: Path, artifact_ref: str) -> str:
    """Compute a local artifact hash without dereferencing external refs."""
    if _is_external_ref(artifact_ref):
        raise ValueError(
            "cannot compute artifact_hash for external artifact_ref without "
            f"dereferencing it: {artifact_ref}"
        )

    artifact_path = _local_artifact_path(artifact_base_dir, artifact_ref)
    if not artifact_path.is_file():
        raise FileNotFoundError(
            "missing local artifact file needed to compute artifact_hash: "
            f"{artifact_path}"
        )

    try:
        return canonical_json_hash(load_json(artifact_path))
    except (TypeError, ValueError):
        return hashlib.sha256(artifact_path.read_bytes()).hexdigest()


def _artifact_hash(
    manifest_artifact: dict[str, Any],
    artifact_base_dir: Path,
    artifact_ref: str,
) -> str:
    candidate_hash = manifest_artifact.get("artifact_hash")
    if isinstance(candidate_hash, str) and SHA256_HEX_PATTERN.fullmatch(
        candidate_hash
    ):
        return candidate_hash
    if candidate_hash is not None:
        raise ValueError(
            "artifact_hash must be a sha256 hex string when present for "
            f"artifact_ref {artifact_ref!r}"
        )
    return _hash_local_artifact(artifact_base_dir, artifact_ref)


def build_evaluation_governance_artifacts(
    chain_manifest: dict[str, Any], artifact_base_dir: Path
) -> list[dict[str, Any]]:
    """Build Reviewer Evidence Packet Evaluation Governance attachments."""
    artifacts = chain_manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("chain manifest must contain an artifacts array")

    reviewer_artifacts: list[dict[str, Any]] = []
    for index, manifest_artifact in enumerate(artifacts):
        if not isinstance(manifest_artifact, dict):
            raise TypeError(f"chain manifest artifacts[{index}] must be an object")

        chain_artifact_type = manifest_artifact.get("artifact_type")
        artifact_ref = manifest_artifact.get("artifact_ref")
        if not isinstance(chain_artifact_type, str) or not chain_artifact_type:
            raise ValueError(f"chain manifest artifacts[{index}] missing artifact_type")
        if not isinstance(artifact_ref, str) or not artifact_ref:
            raise ValueError(f"chain manifest artifacts[{index}] missing artifact_ref")

        artifact_type = map_artifact_type(chain_artifact_type)
        reviewer_artifacts.append(
            {
                "artifact_type": artifact_type,
                "artifact_ref": artifact_ref,
                "artifact_hash": _artifact_hash(
                    manifest_artifact,
                    artifact_base_dir,
                    artifact_ref,
                ),
                "schema_ref": schema_ref_for_artifact_type(artifact_type),
                "required_for_review": False,
            }
        )

    return reviewer_artifacts


def _sanitize_synthetic_template_values(payload: Any) -> Any:
    """Remove email-shaped demo strings from the reused packet template."""
    replacements = {
        "contractor:external.user@example.test": "synthetic_offline_resource",
        "human:manager.alex": "human:synthetic_reviewer",
        "engineering_manager": "synthetic_reviewer",
    }
    if isinstance(payload, dict):
        return {
            key: _sanitize_synthetic_template_values(value)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [_sanitize_synthetic_template_values(value) for value in payload]
    if isinstance(payload, str):
        return replacements.get(payload, payload)
    return payload


def _ensure_human_approval_context_binding(packet: dict[str, Any]) -> None:
    """Populate required human approval context binding on template cases.

    Older reviewer packet templates may predate the strict
    ``human_approval_summary.context_binding`` schema requirement. Synthetic
    Evaluation Governance reviewer packets must still make missing context
    explicit with null values rather than omitting the binding object.
    """
    cases = packet.get("cases")
    if not isinstance(cases, list):
        return

    for case in cases:
        if not isinstance(case, dict):
            continue
        summary = case.get("human_approval_summary")
        if not isinstance(summary, dict):
            continue
        manifest = case.get("evidence_chain_manifest_summary")
        outcome = case.get("outcome_receipt_summary")
        if not isinstance(manifest, dict):
            manifest = {}
        if not isinstance(outcome, dict):
            outcome = {}

        existing = summary.get("context_binding")
        if not isinstance(existing, dict):
            existing = {}
        summary["context_binding"] = {
            "request_ref": existing.get("request_ref"),
            "ai_output_ref": existing.get("ai_output_ref"),
            "execution_intent_id": existing.get("execution_intent_id")
            or manifest.get("execution_intent_id")
            or outcome.get("execution_intent_id"),
            "decision_id": existing.get("decision_id")
            or manifest.get("decision_id")
            or outcome.get("decision_id"),
            "action_class": existing.get("action_class")
            or manifest.get("action_class")
            or outcome.get("action_class"),
            "policy_snapshot_id": existing.get("policy_snapshot_id"),
            "authority_evidence_id": existing.get("authority_evidence_id")
            or manifest.get("authority_evidence_id"),
            "bind_context_hash": existing.get("bind_context_hash"),
        }
        for field in HUMAN_APPROVAL_CONTEXT_BINDING_FIELDS:
            summary["context_binding"].setdefault(field, None)
        for field in HUMAN_APPROVAL_SUMMARY_VERIFIER_FIELDS:
            summary.setdefault(field, None)
        case.setdefault("verifier_lifecycle_summary", None)


def _is_verified_approval_case(
    summary: dict[str, Any],
    manifest: dict[str, Any],
    outcome: dict[str, Any],
) -> bool:
    """Return whether a synthetic case claims a verified approval outcome."""
    return bool(
        summary.get("approved") is True
        and summary.get("receipt_hash_present") is True
        and manifest.get("human_approval_required") is True
        and not summary.get("failure_reasons")
    )


def _recompute_nested_hashes(
    manifest: dict[str, Any],
    outcome: dict[str, Any],
    verification: dict[str, Any],
    *,
    include_verified_proof_link: bool = True,
) -> None:
    """Refresh nested fixture hashes after verifier evidence backfill."""
    outcome_payload = copy.deepcopy(outcome)
    outcome_payload.pop("outcome_hash", None)
    outcome["outcome_hash"] = canonical_json_hash(outcome_payload)
    manifest["outcome_receipt_hash"] = outcome["outcome_hash"]

    manifest_payload = copy.deepcopy(manifest)
    manifest_payload.pop("manifest_hash", None)
    manifest["manifest_hash"] = canonical_json_hash(manifest_payload)

    verification["recomputed_manifest_hash"] = manifest["manifest_hash"]
    verification["manifest_hash_matches"] = True
    verified_links = verification.setdefault("verified_links", [])
    if (
        include_verified_proof_link
        and isinstance(verified_links, list)
        and "verified_human_approval_proof_hash" not in verified_links
    ):
        verified_links.append("verified_human_approval_proof_hash")


def _ensure_human_approval_verifier_evidence(packet: dict[str, Any]) -> None:
    """Populate required verifier evidence on synthetic verified approvals.

    The Evaluation Governance packet reuses a sanitized reviewer template. When
    that template claims a committed, approval-required success, the synthetic
    reviewer packet must keep the verifier identity, verifier policy snapshot,
    and approval proof hash coherent across the human approval summary,
    manifest summary, and outcome metadata. Non-verified or failed cases keep
    explicit ``null`` fields to satisfy the strict reviewer packet schema
    without claiming verifier proof.
    """
    cases = packet.get("cases")
    if not isinstance(cases, list):
        return

    for case in cases:
        if not isinstance(case, dict):
            continue
        summary = case.get("human_approval_summary")
        manifest = case.get("evidence_chain_manifest_summary")
        outcome = case.get("outcome_receipt_summary")
        verification = case.get("evidence_chain_verification_summary")
        if not isinstance(summary, dict):
            continue
        if not isinstance(manifest, dict):
            manifest = {}
        if not isinstance(outcome, dict):
            outcome = {}
        if not isinstance(verification, dict):
            verification = {}

        for field in HUMAN_APPROVAL_SUMMARY_VERIFIER_FIELDS:
            summary.setdefault(field, None)

        if not _is_verified_approval_case(summary, manifest, outcome):
            case["verifier_lifecycle_summary"] = None
            manifest.setdefault(
                "human_approval_verifier_lifecycle_snapshot_hash",
                None,
            )
            _recompute_nested_hashes(
                manifest,
                outcome,
                verification,
                include_verified_proof_link=False,
            )
            continue

        metadata = outcome.setdefault("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
            outcome["metadata"] = metadata

        proof_hash = (
            summary.get("verification_proof_hash")
            or manifest.get("verified_human_approval_proof_hash")
            or metadata.get("verified_human_approval_proof_hash")
            or SYNTHETIC_VERIFIED_APPROVAL_VERIFIER_EVIDENCE[
                "verification_proof_hash"
            ]
        )
        verifier_id = (
            summary.get("verifier_id")
            or manifest.get("human_approval_verifier_id")
            or metadata.get("human_approval_verifier_id")
            or SYNTHETIC_VERIFIED_APPROVAL_VERIFIER_EVIDENCE["verifier_id"]
        )
        verifier_key_id = (
            summary.get("verifier_key_id")
            or manifest.get("human_approval_verifier_key_id")
            or metadata.get("human_approval_verifier_key_id")
            or SYNTHETIC_VERIFIED_APPROVAL_VERIFIER_EVIDENCE["verifier_key_id"]
        )
        verifier_policy_id = (
            summary.get("verifier_policy_id")
            or manifest.get("human_approval_verifier_policy_id")
            or metadata.get("human_approval_verifier_policy_id")
            or SYNTHETIC_VERIFIED_APPROVAL_VERIFIER_EVIDENCE["verifier_policy_id"]
        )
        verifier_policy_hash = (
            summary.get("verifier_policy_hash")
            or manifest.get("human_approval_verifier_policy_hash")
            or metadata.get("human_approval_verifier_policy_hash")
            or SYNTHETIC_VERIFIED_APPROVAL_VERIFIER_EVIDENCE[
                "verifier_policy_hash"
            ]
        )

        verified_at = (
            summary.get("verified_at")
            or verification.get("verified_at")
            or packet.get("generated_at")
        )
        summary.update(
            {
                "verifier_id": verifier_id,
                "verifier_key_id": verifier_key_id,
                "verifier_policy_id": verifier_policy_id,
                "verifier_policy_hash": verifier_policy_hash,
                "verification_proof_hash": proof_hash,
                "verified_at": verified_at,
            }
        )
        manifest.update(
            {
                "verified_human_approval_proof_hash": proof_hash,
                "human_approval_verifier_id": verifier_id,
                "human_approval_verifier_key_id": verifier_key_id,
                "human_approval_verifier_policy_id": verifier_policy_id,
                "human_approval_verifier_policy_hash": verifier_policy_hash,
            }
        )
        metadata.update(
            {
                "verified_human_approval_proof_hash": proof_hash,
                "verified_human_approval_receipt_id": summary.get(
                    "approval_receipt_id"
                ),
                "human_approval_verification_source": (
                    "signed_human_approval_artifact"
                ),
                "human_approval_verifier_id": verifier_id,
                "human_approval_verifier_key_id": verifier_key_id,
                "human_approval_verifier_policy_id": verifier_policy_id,
                "human_approval_verifier_policy_hash": verifier_policy_hash,
            }
        )
        case["verifier_lifecycle_summary"] = (
            verifier_lifecycle_summary_from_human_approval(summary)
        )
        lifecycle_summary = case["verifier_lifecycle_summary"]
        lifecycle_hash = (
            lifecycle_summary.get("verifier_lifecycle_snapshot_hash")
            if isinstance(lifecycle_summary, dict)
            else None
        )
        manifest[
            "human_approval_verifier_lifecycle_snapshot_hash"
        ] = lifecycle_hash
        metadata[
            "human_approval_verifier_lifecycle_snapshot_hash"
        ] = lifecycle_hash
        _recompute_nested_hashes(manifest, outcome, verification)


def _commit_safety_fields(case: dict[str, Any], failure_reason: str) -> None:
    """Mark a tampered lifecycle snapshot case as non-commit-eligible."""
    case["expected_outcome"] = "block"
    case["actual_outcome"] = "block"
    case["runtime_recommended_outcome"] = "block"
    case["passed"] = True
    reasons = case.setdefault("failure_reasons", [])
    if isinstance(reasons, list) and failure_reason not in reasons:
        reasons.append(failure_reason)


def _mark_lifecycle_continuity_failure(
    case: dict[str, Any],
    failure_reason: str,
) -> None:
    """Expose lifecycle snapshot tampering in reviewer-facing summaries."""
    verification = case.get("evidence_chain_verification_summary")
    if not isinstance(verification, dict):
        return

    verification["is_valid"] = False
    verification["verification_status"] = "failed"
    verification["manifest_hash_matches"] = True
    verification["human_approval_verifier_lifecycle_snapshot_hash_continuity_verified"] = False
    verification[
        "human_approval_verifier_lifecycle_snapshot_hash_continuity_failure_reasons"
    ] = [failure_reason]
    verification["failure_reasons"] = [failure_reason]
    verification["missing_links"] = []
    verification["mismatched_links"] = [LIFECYCLE_HASH_FIELD]
    verified_links = verification.get("verified_links")
    if isinstance(verified_links, list):
        verification["verified_links"] = [
            link
            for link in verified_links
            if link != f"{LIFECYCLE_HASH_FIELD}_continuity"
        ]


def _tamper_lifecycle_hash_fields(case: dict[str, Any], failure_reason: str) -> None:
    """Apply deterministic lifecycle snapshot hash tampering to a case copy."""
    manifest = case.get("evidence_chain_manifest_summary")
    outcome = case.get("outcome_receipt_summary")
    if not isinstance(manifest, dict) or not isinstance(outcome, dict):
        return

    metadata = outcome.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
        outcome["metadata"] = metadata

    if failure_reason == EVIDENCE_CHAIN_OUTCOME_LIFECYCLE_SNAPSHOT_HASH_MISSING:
        metadata.pop(LIFECYCLE_HASH_FIELD, None)
    elif failure_reason == EVIDENCE_CHAIN_MANIFEST_LIFECYCLE_SNAPSHOT_HASH_MISSING:
        manifest[LIFECYCLE_HASH_FIELD] = None
    elif failure_reason == EVIDENCE_CHAIN_LIFECYCLE_SNAPSHOT_HASH_MISMATCH:
        metadata[LIFECYCLE_HASH_FIELD] = "2" * 64

    _mark_lifecycle_continuity_failure(case, failure_reason)
    _commit_safety_fields(case, failure_reason)
    verification = case.get("evidence_chain_verification_summary")
    if isinstance(verification, dict):
        _recompute_nested_hashes(manifest, outcome, verification)


def _mark_verifier_continuity_failure(
    case: dict[str, Any],
    failure_reason: str,
    affected_field: str,
) -> None:
    """Expose verifier continuity tampering in reviewer-facing summaries."""
    verification = case.get("evidence_chain_verification_summary")
    if not isinstance(verification, dict):
        return

    verification["is_valid"] = False
    verification["verification_status"] = "failed"
    verification["manifest_hash_matches"] = True
    verification["failure_reasons"] = [failure_reason]
    verification["missing_links"] = []
    verification["mismatched_links"] = [affected_field]


def _tampered_value(summary_field: str) -> str:
    """Return a deterministic local/offline tamper value for a proof field."""
    if summary_field == "verified_at":
        return "2027-01-01T00:00:00+00:00"
    if summary_field == "verifier_id":
        return "tampered-human-approval-verifier-v1"
    if summary_field == "verifier_key_id":
        return "tampered-local-demo-verifier-key"
    return TAMPERED_HEX


def _tamper_verifier_continuity_fields(
    case: dict[str, Any],
    failure_reason: str,
    affected_field: str,
    summary_field: str,
) -> None:
    """Apply deterministic verifier continuity tampering to a case copy."""
    summary = case.get("human_approval_summary")
    manifest = case.get("evidence_chain_manifest_summary")
    outcome = case.get("outcome_receipt_summary")
    verification = case.get("evidence_chain_verification_summary")
    if not isinstance(summary, dict):
        return
    if not isinstance(manifest, dict):
        manifest = {}
    if not isinstance(outcome, dict):
        outcome = {}
    if not isinstance(verification, dict):
        verification = {}

    summary[summary_field] = _tampered_value(summary_field)
    _mark_verifier_continuity_failure(case, failure_reason, affected_field)
    _commit_safety_fields(case, failure_reason)

    if isinstance(manifest, dict) and isinstance(outcome, dict):
        _recompute_nested_hashes(
            manifest,
            outcome,
            verification,
            include_verified_proof_link=summary_field != "verification_proof_hash",
        )


def _append_verifier_continuity_tamper_regression_cases(
    packet: dict[str, Any],
) -> None:
    """Add local/offline negative fixtures for verifier proof continuity.

    These synthetic cases make verifier identity, key, policy, proof hash, and
    proof timestamp tampering visible to reviewers without changing production
    verifier allowlists, runtime admissibility behavior, or live integrations.
    """
    cases = packet.get("cases")
    if not isinstance(cases, list):
        return

    source_case = next(
        (
            case
            for case in cases
            if isinstance(case, dict)
            and case.get("case_id") == "valid_authority_and_approval"
        ),
        None,
    )
    if source_case is None:
        return

    for (
        suffix,
        failure_reason,
        affected_field,
        summary_field,
        interpretation,
    ) in VERIFIER_CONTINUITY_TAMPER_CASES:
        case = copy.deepcopy(source_case)
        case["case_id"] = f"{source_case['case_id']}_{suffix}"
        case["reviewer_interpretation"] = interpretation
        case["boundary_note"] = (
            "local/offline synthetic tamper regression fixture only; no "
            "runtime admissibility change or live verifier integration"
        )
        _tamper_verifier_continuity_fields(
            case,
            failure_reason,
            affected_field,
            summary_field,
        )
        cases.append(case)


def _append_lifecycle_tamper_regression_cases(packet: dict[str, Any]) -> None:
    """Add local/offline negative fixtures for lifecycle hash continuity.

    These deterministic reviewer/demo cases prove that lifecycle snapshot hash
    tampering is visible end-to-end in the generated Reviewer Evidence Packet.
    They are synthetic evidence-only fixtures and do not change runtime verifier
    allowlists, production admissibility, or live service behavior.
    """
    cases = packet.get("cases")
    if not isinstance(cases, list):
        return

    source_case = next(
        (
            case
            for case in cases
            if isinstance(case, dict)
            and case.get("case_id") == "valid_authority_and_approval"
        ),
        None,
    )
    if source_case is None:
        return

    for suffix, failure_reason, interpretation in LIFECYCLE_TAMPER_CASES:
        case = copy.deepcopy(source_case)
        case["case_id"] = f"{source_case['case_id']}_{suffix}"
        case["reviewer_interpretation"] = interpretation
        case["boundary_note"] = (
            "local/offline synthetic tamper regression fixture only; no "
            "runtime admissibility change or live verifier integration"
        )
        _tamper_lifecycle_hash_fields(case, failure_reason)
        cases.append(case)


def _packet_hash(packet: dict[str, Any]) -> str:
    """Compute Reviewer Evidence Packet hash excluding packet_hash itself."""
    payload = copy.deepcopy(packet)
    payload.pop("packet_hash", None)
    return canonical_json_hash(payload)


def validate_reviewer_packet(packet: dict[str, Any]) -> None:
    """Validate generated packet against Reviewer Evidence Packet v1 if possible."""
    jsonschema = _jsonschema_module()
    if jsonschema is None:
        return

    schema = load_json(REVIEWER_PACKET_SCHEMA_PATH)
    try:
        jsonschema.Draft202012Validator(schema).validate(packet)
    except jsonschema.ValidationError as exc:
        raise ValueError("Reviewer Evidence Packet schema validation failed") from exc


def generate_reviewer_evidence_packet_from_chain(
    chain_manifest: dict[str, Any], artifact_base_dir: Path
) -> dict[str, Any]:
    """Generate a Reviewer Evidence Packet v1 from an offline chain manifest.

    The returned packet is synthetic, local/offline-only, and non-enforcing. It
    preserves the existing Reviewer Evidence Packet v1 shape while replacing
    Evaluation Governance attachments with artifacts listed in the chain
    manifest.
    """
    reviewer_artifacts = build_evaluation_governance_artifacts(
        chain_manifest,
        artifact_base_dir,
    )
    chain_id = chain_manifest.get("chain_id", "evaluation-governance-chain")
    issued_at = chain_manifest.get("issued_at", "2026-01-01T00:00:00Z")

    packet = _sanitize_synthetic_template_values(
        load_json(REVIEWER_PACKET_TEMPLATE_PATH)
    )
    _ensure_human_approval_context_binding(packet)
    _ensure_human_approval_verifier_evidence(packet)
    _append_lifecycle_tamper_regression_cases(packet)
    _append_verifier_continuity_tamper_regression_cases(packet)
    packet["demo_id"] = "evaluation_governance_offline_chain_reviewer_packet_v1"
    packet["generated_at"] = issued_at
    packet["title"] = "Evaluation Governance Offline Chain Reviewer Evidence Packet"
    packet["summary"] = (
        "Synthetic local/offline reviewer packet generated from Evaluation "
        f"Governance offline chain manifest {chain_id!r}. It attaches chain "
        "artifacts as optional reviewer evidence and does not establish "
        "legitimacy or certify compliance."
    )
    packet["boundary_note"] = (
        "local/offline synthetic reviewer evidence only; no /v1/decide call, "
        "runtime admissibility change, live service integration, legitimacy "
        "determination, or compliance certification"
    )
    packet["local_offline_only"] = True
    packet.setdefault("evaluation_governance_artifacts", reviewer_artifacts)
    packet["key_provenance"] = key_provenance_metadata()
    packet["reviewer_notes"] = list(REVIEWER_NOTES)
    packet["packet_hash"] = _packet_hash(packet)

    validate_reviewer_packet(packet)
    return packet


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"{json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)}\n",
        encoding="utf-8",
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a synthetic Reviewer Evidence Packet from an offline "
            "Evaluation Governance chain manifest."
        )
    )
    parser.add_argument(
        "--chain-manifest",
        required=True,
        type=Path,
        help="Path to the Evaluation Governance offline chain manifest JSON.",
    )
    parser.add_argument(
        "--artifact-base-dir",
        required=True,
        type=Path,
        help="Base directory for resolving local chain artifact refs if needed.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output JSON path; stdout is used when omitted.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the offline reviewer packet helper."""
    args = _parse_args(argv)
    try:
        chain_manifest = load_json(args.chain_manifest)
        packet = generate_reviewer_evidence_packet_from_chain(
            chain_manifest,
            args.artifact_base_dir,
        )
    except Exception as exc:  # noqa: BLE001 - CLI must present clear errors.
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.output is None:
        print(json.dumps(packet, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        _write_json(args.output, packet)
        print(
            "Generated Reviewer Evidence Packet from Evaluation Governance "
            f"offline chain: {args.output} "
            f"({len(packet['evaluation_governance_artifacts'])} artifacts)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
