"""Stable reviewer/demo failure reason taxonomy guards.

This module is deterministic, local/offline, and intentionally limited to
reviewer/demo artifacts. It does not change runtime admissibility behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True, order=True)
class UnknownFailureReason:
    """Unknown reviewer/demo failure reason with its artifact path."""

    path: str
    reason: str


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
