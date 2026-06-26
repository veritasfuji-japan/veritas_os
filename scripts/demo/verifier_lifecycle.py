"""Deterministic reviewer-facing verifier lifecycle fixtures.

This module models only local/offline audit evidence for reviewer packets. It is
not a production KMS, HSM, verifier allowlist, or revocation service.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from veritas_os.security.hash import sha256_of_canonical_json

LIFECYCLE_SNAPSHOT_HASH_FIELDS = (
    "verifier_id",
    "verifier_key_id",
    "verifier_policy_id",
    "verifier_policy_hash",
    "verifier_lifecycle_status",
    "verifier_valid_from",
    "verifier_valid_until",
    "verifier_revoked_at",
    "verifier_revocation_reason",
    "verifier_lifecycle_policy_hash",
)

VERIFIER_ID = "veritas-human-approval-verifier-v1"
VERIFIER_KEY_ID = "local-demo-verifier-key"
VERIFIER_POLICY_ID = "human-approval-verifier-policy-v1"
VERIFIER_POLICY_HASH = sha256_of_canonical_json(
    {
        "approved_human_approval_verifiers": [
            {
                "verifier_id": VERIFIER_ID,
                "trust_level": "production",
                "verifier_key_id": VERIFIER_KEY_ID,
                "policy_id": VERIFIER_POLICY_ID,
            }
        ],
        "fixture_only": True,
    }
)


def verifier_lifecycle_snapshot(
    *,
    lifecycle_status: str = "rotated",
    valid_from: str = "2026-01-01T00:00:00+00:00",
    valid_until: str | None = "2026-12-31T00:00:00+00:00",
    revoked_at: str | None = None,
    revocation_reason: str | None = None,
    verifier_id: str = VERIFIER_ID,
    verifier_key_id: str | None = VERIFIER_KEY_ID,
    verifier_policy_id: str = VERIFIER_POLICY_ID,
    verifier_policy_hash: str = VERIFIER_POLICY_HASH,
) -> dict[str, Any]:
    """Return a deterministic local/offline verifier lifecycle snapshot."""
    return {
        "verifier_id": verifier_id,
        "verifier_key_id": verifier_key_id,
        "verifier_policy_id": verifier_policy_id,
        "verifier_policy_hash": verifier_policy_hash,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "revoked_at": revoked_at,
        "revocation_reason": revocation_reason,
        "lifecycle_status": lifecycle_status,
    }


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def verifier_lifecycle_summary_from_human_approval(
    human_approval_summary: dict[str, Any],
) -> dict[str, Any] | None:
    """Build reviewer packet lifecycle summary from Human Approval evidence.

    Returns ``None`` for cases without a verified approval proof. For proof
    cases, the deterministic fixture lifecycle mirrors the proof's verifier
    identity and policy fields and includes validation failure reasons.
    """
    if not human_approval_summary.get("verification_proof_hash"):
        return None

    lifecycle = verifier_lifecycle_snapshot(
        verifier_id=str(human_approval_summary.get("verifier_id") or VERIFIER_ID),
        verifier_key_id=human_approval_summary.get("verifier_key_id")
        or VERIFIER_KEY_ID,
        verifier_policy_id=str(
            human_approval_summary.get("verifier_policy_id") or VERIFIER_POLICY_ID
        ),
        verifier_policy_hash=str(
            human_approval_summary.get("verifier_policy_hash")
            or VERIFIER_POLICY_HASH
        ),
    )
    failure_reasons = validate_human_approval_verifier_lifecycle_snapshot(
        human_approval_summary=human_approval_summary,
        lifecycle_snapshot=lifecycle,
        proof_verified_at=human_approval_summary.get("verified_at"),
    )
    summary = {
        "verifier_id": lifecycle["verifier_id"],
        "verifier_key_id": lifecycle["verifier_key_id"],
        "verifier_policy_id": lifecycle["verifier_policy_id"],
        "verifier_policy_hash": lifecycle["verifier_policy_hash"],
        "verifier_lifecycle_status": lifecycle["lifecycle_status"],
        "verifier_valid_from": lifecycle["valid_from"],
        "verifier_valid_until": lifecycle["valid_until"],
        "verifier_revoked_at": lifecycle["revoked_at"],
        "verifier_revocation_reason": lifecycle["revocation_reason"],
        "verifier_lifecycle_policy_hash": lifecycle["verifier_policy_hash"],
        "failure_reasons": failure_reasons,
    }
    summary["verifier_lifecycle_snapshot_hash"] = (
        compute_verifier_lifecycle_snapshot_hash(summary)
    )
    return summary


def compute_verifier_lifecycle_snapshot_hash(
    lifecycle_summary: dict[str, Any],
) -> str:
    """Compute the canonical SHA-256 hash of lifecycle-relevant fields.

    The hash intentionally excludes validation failure reasons and the hash
    field itself so reviewer packets can verify that the lifecycle evidence used
    for validation is exactly the lifecycle field snapshot presented to them.
    """
    payload = {
        field: lifecycle_summary.get(field)
        for field in LIFECYCLE_SNAPSHOT_HASH_FIELDS
    }
    return sha256_of_canonical_json(payload)


def validate_human_approval_verifier_lifecycle_snapshot(
    *,
    human_approval_summary: dict[str, Any],
    lifecycle_snapshot: dict[str, Any] | None,
    proof_verified_at: str | None = None,
) -> list[str]:
    """Validate reviewer-facing Human Approval verifier lifecycle evidence.

    The helper is deterministic and fixture-scoped: it checks whether the
    verifier identity, key, policy, and proof timestamp match the lifecycle
    snapshot carried by a reviewer packet. It does not contact external
    revocation services or alter production verifier allowlist behavior.
    """
    proof_hash = human_approval_summary.get("verification_proof_hash")
    if not proof_hash:
        return []
    if not isinstance(lifecycle_snapshot, dict):
        return ["reviewer_packet_verifier_lifecycle_missing"]

    if "verifier_lifecycle_status" in lifecycle_snapshot:
        snapshot_hash = lifecycle_snapshot.get("verifier_lifecycle_snapshot_hash")
        if not isinstance(snapshot_hash, str) or not snapshot_hash.strip():
            return ["reviewer_packet_verifier_lifecycle_snapshot_hash_missing"]
        if snapshot_hash != compute_verifier_lifecycle_snapshot_hash(
            lifecycle_snapshot
        ):
            return ["reviewer_packet_verifier_lifecycle_snapshot_hash_mismatch"]

    checks = (
        ("verifier_id", "reviewer_packet_verifier_lifecycle_id_mismatch"),
        ("verifier_key_id", "reviewer_packet_verifier_lifecycle_key_mismatch"),
        ("verifier_policy_id", "reviewer_packet_verifier_lifecycle_id_mismatch"),
        (
            "verifier_policy_hash",
            "reviewer_packet_verifier_lifecycle_policy_hash_mismatch",
        ),
    )
    for field, reason in checks:
        summary_value = human_approval_summary.get(field)
        lifecycle_value = lifecycle_snapshot.get(field)
        if summary_value and lifecycle_value and summary_value != lifecycle_value:
            return [reason]
        if summary_value and lifecycle_value is None and field != "verifier_key_id":
            return [reason]

    verified_at = _parse_timestamp(
        proof_verified_at or human_approval_summary.get("verified_at")
    )
    valid_from = _parse_timestamp(
        lifecycle_snapshot.get("verifier_valid_from")
        or lifecycle_snapshot.get("valid_from")
    )
    valid_until = _parse_timestamp(
        lifecycle_snapshot.get("verifier_valid_until")
        or lifecycle_snapshot.get("valid_until")
    )
    revoked_at = _parse_timestamp(
        lifecycle_snapshot.get("verifier_revoked_at")
        or lifecycle_snapshot.get("revoked_at")
    )

    if verified_at is None:
        return ["reviewer_packet_verifier_lifecycle_missing"]
    if valid_from is not None and verified_at < valid_from:
        return ["reviewer_packet_verifier_not_yet_valid"]
    if valid_until is not None and verified_at >= valid_until:
        return ["reviewer_packet_verifier_expired_before_verification"]
    if revoked_at is not None and verified_at >= revoked_at:
        return ["reviewer_packet_verifier_revoked_before_verification"]
    return []
