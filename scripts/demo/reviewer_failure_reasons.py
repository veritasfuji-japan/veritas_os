"""Stable reviewer/demo failure reason taxonomy guards.

This module is deterministic, local/offline, and intentionally limited to
reviewer/demo artifacts. It does not change runtime admissibility behavior.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

EVIDENCE_CHAIN_MANIFEST_LIFECYCLE_SNAPSHOT_HASH_MISSING = (
    "evidence_chain_manifest_lifecycle_snapshot_hash_missing"
)
EVIDENCE_CHAIN_OUTCOME_LIFECYCLE_SNAPSHOT_HASH_MISSING = (
    "evidence_chain_outcome_lifecycle_snapshot_hash_missing"
)
EVIDENCE_CHAIN_LIFECYCLE_SNAPSHOT_HASH_MISMATCH = (
    "evidence_chain_lifecycle_snapshot_hash_mismatch"
)
REVIEWER_PACKET_VERIFIER_ID_MISMATCH = "reviewer_packet_verifier_id_mismatch"
REVIEWER_PACKET_VERIFIER_KEY_ID_MISMATCH = (
    "reviewer_packet_verifier_key_id_mismatch"
)
REVIEWER_PACKET_VERIFIER_POLICY_HASH_MISMATCH = (
    "reviewer_packet_verifier_policy_hash_mismatch"
)
REVIEWER_PACKET_VERIFICATION_PROOF_HASH_MISMATCH = (
    "reviewer_packet_verification_proof_hash_mismatch"
)
REVIEWER_PACKET_VERIFIED_AT_MISMATCH = "reviewer_packet_verified_at_mismatch"
REVIEWER_FAILURE_REASON_TAXONOMY_UNKNOWN = (
    "reviewer_failure_reason_taxonomy_unknown"
)

_FAILURE_REASON_FIELDS = frozenset(
    {
        "failure_reasons",
        "human_approval_verifier_lifecycle_snapshot_hash_continuity_failure_reasons",
        "expected_failure_reasons",
    }
)

REVIEWER_FAILURE_REASONS = frozenset(
    {
        "artifact_manifest_artifact_name_invalid",
        "artifact_manifest_file_hash_mismatch",
        "artifact_manifest_file_size_mismatch",
        "artifact_manifest_hash_mismatch",
        "artifact_manifest_json_unparseable",
        "artifact_manifest_missing",
        "artifact_manifest_required_file_missing",
        "authority_expired_or_missing",
        "authority_invalid",
        "authority_missing",
        "blocked_case_outcome_failure_reasons_missing",
        "blocked_case_refusal_basis_missing",
        "case_expectations_failed",
        "demo_mismatched_links_present",
        EVIDENCE_CHAIN_LIFECYCLE_SNAPSHOT_HASH_MISMATCH,
        EVIDENCE_CHAIN_MANIFEST_LIFECYCLE_SNAPSHOT_HASH_MISSING,
        EVIDENCE_CHAIN_OUTCOME_LIFECYCLE_SNAPSHOT_HASH_MISSING,
        "evidence_chain_verification_missing",
        "generated_packet_mismatch",
        "golden_fixture_json_unparseable",
        "golden_fixture_missing",
        "human_approval_action_class_mismatch",
        "human_approval_bind_context_hash_mismatch",
        "human_approval_expired",
        "human_approval_missing",
        "human_approval_request_ref_mismatch",
        "human_approval_scope_not_granted",
        "local_offline_boundary_missing",
        "packet_hash_length_invalid",
        "packet_hash_missing",
        "packet_hash_recompute_mismatch",
        "required_case_fields_missing",
        "required_top_level_fields_missing",
        "reviewer_evidence_bundle_output_dir_invalid",
        REVIEWER_FAILURE_REASON_TAXONOMY_UNKNOWN,
        "reviewer_packet_committed_lifecycle_status_not_clean",
        "reviewer_packet_human_approval_proof_continuity_invalid",
        "reviewer_packet_manifest_lifecycle_snapshot_hash_mismatch",
        "reviewer_packet_outcome_lifecycle_snapshot_hash_mismatch",
        REVIEWER_PACKET_VERIFICATION_PROOF_HASH_MISMATCH,
        REVIEWER_PACKET_VERIFIED_AT_MISMATCH,
        "reviewer_packet_verifier_expired_before_verification",
        REVIEWER_PACKET_VERIFIER_ID_MISMATCH,
        "reviewer_packet_verifier_id_missing",
        REVIEWER_PACKET_VERIFIER_KEY_ID_MISMATCH,
        "reviewer_packet_verifier_lifecycle_invalid",
        "reviewer_packet_verifier_lifecycle_policy_hash_mismatch",
        "reviewer_packet_verifier_lifecycle_snapshot_hash_missing",
        "reviewer_packet_verifier_lifecycle_snapshot_hash_mismatch",
        "reviewer_packet_verifier_not_yet_valid",
        REVIEWER_PACKET_VERIFIER_POLICY_HASH_MISMATCH,
        "reviewer_packet_verifier_policy_hash_missing",
        "reviewer_packet_verifier_policy_id_missing",
        "reviewer_packet_verifier_revoked_before_verification",
        "schema_file_json_unparseable",
        "schema_file_missing",
        "schema_json_unparseable",
        "schema_validation_failed",
        "valid_case_chain_not_verified",
    }
)

REVIEWER_FAILURE_REASON_CATEGORIES = frozenset(
    {
        "schema",
        "artifact_manifest",
        "authority",
        "human_approval",
        "verifier_lifecycle",
        "verifier_continuity",
        "lifecycle_snapshot_continuity",
        "packet_integrity",
        "demo_generation",
        "taxonomy",
    }
)

REVIEWER_FAILURE_REASON_SEVERITIES = frozenset(
    {"info", "warning", "error", "critical"}
)


@dataclass(frozen=True, order=True)
class UnknownFailureReason:
    """Unknown reviewer/demo failure reason with its artifact path."""

    path: str
    reason: str


@dataclass(frozen=True)
class FailureReasonMetadata:
    """Reviewer-facing metadata for a stable demo failure reason code."""

    reason: str
    category: str
    severity: str
    reviewer_label: str
    reviewer_explanation: str
    remediation_hint: str
    affected_artifacts: tuple[str, ...]


_CATEGORY_BY_PREFIX = {
    "artifact_manifest_": "artifact_manifest",
    "authority_": "authority",
    "blocked_case_": "demo_generation",
    "case_expectations_": "demo_generation",
    "demo_": "demo_generation",
    "evidence_chain_lifecycle_snapshot_": "lifecycle_snapshot_continuity",
    "evidence_chain_manifest_lifecycle_snapshot_": (
        "lifecycle_snapshot_continuity"
    ),
    "evidence_chain_outcome_lifecycle_snapshot_": (
        "lifecycle_snapshot_continuity"
    ),
    "evidence_chain_": "packet_integrity",
    "generated_packet_": "demo_generation",
    "golden_fixture_": "demo_generation",
    "human_approval_": "human_approval",
    "local_offline_": "demo_generation",
    "packet_hash_": "packet_integrity",
    "required_case_fields_": "schema",
    "required_top_level_fields_": "schema",
    "reviewer_evidence_bundle_": "demo_generation",
    "reviewer_failure_reason_taxonomy_": "taxonomy",
    "reviewer_packet_committed_lifecycle_": "verifier_lifecycle",
    "reviewer_packet_human_approval_proof_": "verifier_continuity",
    "reviewer_packet_manifest_lifecycle_snapshot_": (
        "lifecycle_snapshot_continuity"
    ),
    "reviewer_packet_outcome_lifecycle_snapshot_": (
        "lifecycle_snapshot_continuity"
    ),
    "reviewer_packet_verification_proof_": "packet_integrity",
    "reviewer_packet_verified_at_": "verifier_continuity",
    "reviewer_packet_verifier_lifecycle_snapshot_": (
        "lifecycle_snapshot_continuity"
    ),
    "reviewer_packet_verifier_lifecycle_": "verifier_lifecycle",
    "reviewer_packet_verifier_": "verifier_continuity",
    "schema_": "schema",
    "valid_case_chain_": "packet_integrity",
}

_AFFECTED_ARTIFACTS_BY_CATEGORY = {
    "schema": ("reviewer_packet_schema", "validation_report"),
    "artifact_manifest": ("artifact_manifest", "reviewer_evidence_bundle"),
    "authority": ("reviewer_packet", "authority_summary"),
    "human_approval": ("reviewer_packet", "human_approval_summary"),
    "verifier_lifecycle": ("reviewer_packet", "verifier_lifecycle_summary"),
    "verifier_continuity": (
        "reviewer_packet",
        "human_approval_summary",
        "evidence_chain_manifest",
        "outcome_receipt",
    ),
    "lifecycle_snapshot_continuity": (
        "reviewer_packet",
        "verifier_lifecycle_summary",
        "evidence_chain_manifest",
        "outcome_receipt",
    ),
    "packet_integrity": (
        "reviewer_packet",
        "evidence_chain_manifest",
        "outcome_receipt",
    ),
    "demo_generation": ("demo_fixture", "validation_report"),
    "taxonomy": ("reviewer_packet", "validation_report"),
}


def _category_for_reason(reason: str) -> str:
    """Return the reviewer metadata category for a taxonomy reason."""
    for prefix, category in _CATEGORY_BY_PREFIX.items():
        if reason.startswith(prefix):
            return category
    return "taxonomy"


def _severity_for_reason(reason: str, category: str) -> str:
    """Return a deterministic reviewer severity for a taxonomy reason."""
    if "taxonomy_unknown" in reason:
        return "critical"
    if any(token in reason for token in ("mismatch", "invalid", "failed")):
        return "error"
    if any(token in reason for token in ("missing", "unparseable")):
        return "error"
    if category in {"verifier_lifecycle", "verifier_continuity"} and any(
        token in reason for token in ("expired", "revoked", "not_yet_valid")
    ):
        return "critical"
    return "warning"


def _label_for_reason(reason: str) -> str:
    """Return a compact title-case reviewer label for a taxonomy reason."""
    return reason.replace("_", " ").capitalize()


def _metadata_for_reason(reason: str) -> FailureReasonMetadata:
    """Build metadata for a stable reviewer/demo failure reason."""
    category = _category_for_reason(reason)
    severity = _severity_for_reason(reason, category)
    label = _label_for_reason(reason)
    return FailureReasonMetadata(
        reason=reason,
        category=category,
        severity=severity,
        reviewer_label=label,
        reviewer_explanation=(
            f"{label} indicates a {category.replace('_', ' ')} validation "
            "condition failed in the local/offline reviewer demo artifacts."
        ),
        remediation_hint=(
            "Regenerate or repair the affected local demo artifact, then rerun "
            "the reviewer validation commands before review."
        ),
        affected_artifacts=_AFFECTED_ARTIFACTS_BY_CATEGORY[category],
    )


REVIEWER_FAILURE_REASON_METADATA = {
    reason: _metadata_for_reason(reason)
    for reason in sorted(REVIEWER_FAILURE_REASONS)
}


def _format_path(path: Iterable[str]) -> str:
    return ".".join(path)


def iter_failure_reasons(
    payload: Any,
    *,
    path: tuple[str, ...] = (),
) -> Iterable[tuple[str, str]]:
    """Yield reviewer/demo failure reason strings and JSON-style paths."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            child_path = (*path, key)
            if key in _FAILURE_REASON_FIELDS and isinstance(value, list):
                for index, reason in enumerate(value):
                    if isinstance(reason, str):
                        yield _format_path((*child_path, str(index))), reason
            yield from iter_failure_reasons(value, path=child_path)
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            yield from iter_failure_reasons(item, path=(*path, str(index)))


def unknown_failure_reasons(payload: Any) -> tuple[UnknownFailureReason, ...]:
    """Return unknown reviewer/demo failure reasons found in a payload."""
    unknown = {
        UnknownFailureReason(path=path, reason=reason)
        for path, reason in iter_failure_reasons(payload)
        if reason not in REVIEWER_FAILURE_REASONS
    }
    return tuple(sorted(unknown))


def assert_known_failure_reasons(payload: Any) -> None:
    """Raise AssertionError when a payload contains non-taxonomy reasons."""
    unknown = unknown_failure_reasons(payload)
    if unknown:
        details = ", ".join(f"{item.path}={item.reason}" for item in unknown)
        raise AssertionError(f"Unknown reviewer/demo failure reasons: {details}")


def get_failure_reason_metadata(reason: str) -> FailureReasonMetadata | None:
    """Return reviewer-facing metadata for a stable failure reason code."""
    return REVIEWER_FAILURE_REASON_METADATA.get(reason)


def failure_reason_metadata_for_payload(
    payload: Any,
) -> dict[str, FailureReasonMetadata]:
    """Return metadata for known failure reasons found in a payload."""
    reasons_seen = {
        reason
        for _, reason in iter_failure_reasons(payload)
        if reason in REVIEWER_FAILURE_REASON_METADATA
    }
    return {
        reason: REVIEWER_FAILURE_REASON_METADATA[reason]
        for reason in sorted(reasons_seen)
    }


def failure_reason_metadata_summary_for_payload(payload: Any) -> dict[str, Any]:
    """Return a compact reviewer metadata summary for reasons in a payload."""
    metadata = failure_reason_metadata_for_payload(payload)
    unknown = unknown_failure_reasons(payload)
    categories_seen = sorted({item.category for item in metadata.values()})
    severities_seen = sorted({item.severity for item in metadata.values()})
    return {
        "unknown_reasons": [
            {"path": item.path, "reason": item.reason} for item in unknown
        ],
        "known_reasons_seen": sorted(metadata),
        "categories_seen": categories_seen,
        "severities_seen": severities_seen,
        "metadata": {
            reason: asdict(entry) for reason, entry in metadata.items()
        },
    }
