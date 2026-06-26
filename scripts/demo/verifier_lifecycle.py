"""Deterministic reviewer-facing verifier lifecycle fixtures.

This module models only local/offline audit evidence for reviewer packets. It is
not a production KMS, HSM, verifier allowlist, or revocation service.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from veritas_os.security.hash import sha256_of_canonical_json

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
    valid_from: str = "2026-04-01T00:00:00+00:00",
    valid_until: str | None = "2026-05-01T00:00:00+00:00",
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
    valid_from = _parse_timestamp(lifecycle_snapshot.get("valid_from"))
    valid_until = _parse_timestamp(lifecycle_snapshot.get("valid_until"))
    revoked_at = _parse_timestamp(lifecycle_snapshot.get("revoked_at"))

    if verified_at is None:
        return ["reviewer_packet_verifier_lifecycle_missing"]
    if valid_from is not None and verified_at < valid_from:
        return ["reviewer_packet_verifier_not_yet_valid"]
    if valid_until is not None and verified_at >= valid_until:
        return ["reviewer_packet_verifier_expired_before_verification"]
    if revoked_at is not None and verified_at >= revoked_at:
        return ["reviewer_packet_verifier_revoked_before_verification"]
    return []
