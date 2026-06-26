#!/usr/bin/env python3
"""Deterministic verifier lifecycle fixtures for reviewer packet audits."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from veritas_os.security.hash import sha256_of_canonical_json

VERIFIER_ID = "veritas-human-approval-verifier-v1"
VERIFIER_KEY_ID = "local-demo-verifier-key"
VERIFIER_POLICY_ID = "human-approval-verifier-policy-v1"
ROTATED_KEY_ID = "local-demo-verifier-key-rotated"
ROTATED_POLICY_ID = "human-approval-verifier-policy-v2"
VALID_FROM = "2026-04-01T00:00:00+00:00"
VALID_UNTIL = "2026-04-30T00:00:00+00:00"
ROTATED_AT = "2026-05-01T00:00:00+00:00"
REVOKED_AT = "2026-04-24T00:00:00+00:00"


def verifier_policy_hash(
    *,
    verifier_id: str = VERIFIER_ID,
    verifier_key_id: str = VERIFIER_KEY_ID,
    verifier_policy_id: str = VERIFIER_POLICY_ID,
) -> str:
    """Return the deterministic demo verifier policy hash."""
    return sha256_of_canonical_json(
        {
            "approved_human_approval_verifiers": [
                {
                    "verifier_id": verifier_id,
                    "trust_level": "production",
                    "verifier_key_id": verifier_key_id,
                    "policy_id": verifier_policy_id,
                }
            ],
            "fixture_only": True,
        }
    )


def verifier_lifecycle_record(
    *,
    lifecycle_status: str = "rotated",
    verifier_id: str = VERIFIER_ID,
    verifier_key_id: str = VERIFIER_KEY_ID,
    verifier_policy_id: str = VERIFIER_POLICY_ID,
    verifier_policy_hash_value: str | None = None,
    valid_from: str = VALID_FROM,
    valid_until: str | None = VALID_UNTIL,
    revoked_at: str | None = None,
    revocation_reason: str | None = None,
) -> dict[str, Any]:
    """Build one reviewer-facing verifier lifecycle snapshot record."""
    policy_hash = verifier_policy_hash_value or verifier_policy_hash(
        verifier_id=verifier_id,
        verifier_key_id=verifier_key_id,
        verifier_policy_id=verifier_policy_id,
    )
    return {
        "verifier_id": verifier_id,
        "verifier_key_id": verifier_key_id,
        "verifier_policy_id": verifier_policy_id,
        "verifier_policy_hash": policy_hash,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "revoked_at": revoked_at,
        "revocation_reason": revocation_reason,
        "lifecycle_status": lifecycle_status,
    }


def reviewer_packet_lifecycle_summary(
    record: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return the compact lifecycle section exposed in reviewer packets."""
    if record is None:
        return {
            "verifier_lifecycle_status": None,
            "verifier_valid_from": None,
            "verifier_valid_until": None,
            "verifier_revoked_at": None,
            "verifier_revocation_reason": None,
            "verifier_lifecycle_policy_hash": None,
        }
    return {
        "verifier_lifecycle_status": record.get("lifecycle_status"),
        "verifier_valid_from": record.get("valid_from"),
        "verifier_valid_until": record.get("valid_until"),
        "verifier_revoked_at": record.get("revoked_at"),
        "verifier_revocation_reason": record.get("revocation_reason"),
        "verifier_lifecycle_policy_hash": record.get("verifier_policy_hash"),
    }


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_human_approval_verifier_lifecycle_snapshot(
    *,
    proof: dict[str, Any] | None,
    lifecycle_snapshot: dict[str, Any] | None,
) -> list[str]:
    """Validate a proof against its deterministic reviewer lifecycle snapshot.

    This helper is intentionally local/offline fixture logic, not production key
    management. It preserves reviewer auditability for historical approvals by
    checking verifier identity, key, policy, policy hash, validity window, and
    revocation time as they were captured in the reviewer-facing artifacts.
    """
    if not proof:
        return []
    if lifecycle_snapshot is None:
        return ["reviewer_packet_verifier_lifecycle_missing"]

    reasons: list[str] = []
    if proof.get("verifier_id") != lifecycle_snapshot.get("verifier_id"):
        reasons.append("reviewer_packet_verifier_lifecycle_id_mismatch")
    proof_key_id = proof.get("verifier_key_id")
    if proof_key_id and proof_key_id != lifecycle_snapshot.get("verifier_key_id"):
        reasons.append("reviewer_packet_verifier_lifecycle_key_mismatch")
    if proof.get("verifier_policy_id") != lifecycle_snapshot.get(
        "verifier_policy_id"
    ):
        reasons.append("reviewer_packet_verifier_lifecycle_policy_id_mismatch")
    if proof.get("verifier_policy_hash") != lifecycle_snapshot.get(
        "verifier_policy_hash"
    ):
        reasons.append("reviewer_packet_verifier_lifecycle_policy_hash_mismatch")

    proof_time = _parse_timestamp(
        proof.get("verified_at") or proof.get("approved_at")
    )
    valid_from = _parse_timestamp(lifecycle_snapshot.get("valid_from"))
    valid_until = _parse_timestamp(lifecycle_snapshot.get("valid_until"))
    revoked_at = _parse_timestamp(lifecycle_snapshot.get("revoked_at"))
    if (
        proof_time is not None
        and valid_from is not None
        and proof_time < valid_from
    ):
        reasons.append("reviewer_packet_verifier_not_yet_valid")
    if (
        proof_time is not None
        and valid_until is not None
        and proof_time > valid_until
    ):
        reasons.append("reviewer_packet_verifier_expired_before_verification")
    if (
        proof_time is not None
        and revoked_at is not None
        and proof_time >= revoked_at
    ):
        reasons.append("reviewer_packet_verifier_revoked_before_verification")
    return reasons


def demo_lifecycle_audit_fixtures() -> dict[str, Any]:
    """Return deterministic verifier lifecycle audit fixture cases."""
    active_record = verifier_lifecycle_record()
    proof = {
        "verifier_id": VERIFIER_ID,
        "verifier_key_id": VERIFIER_KEY_ID,
        "verifier_policy_id": VERIFIER_POLICY_ID,
        "verifier_policy_hash": active_record["verifier_policy_hash"],
        "verified_at": "2026-04-26T00:00:00+00:00",
    }
    rotated_hash = verifier_policy_hash(
        verifier_key_id=ROTATED_KEY_ID,
        verifier_policy_id=ROTATED_POLICY_ID,
    )
    return {
        "fixture_id": "human-approval-verifier-lifecycle-audit-v1",
        "generated_at": "2026-04-26T00:00:00+00:00",
        "cases": [
            {
                "case_id": "valid_at_verification_time",
                "proof": proof,
                "lifecycle_snapshot": active_record,
                "later_lifecycle_event": {
                    "event_type": "rotated",
                    "rotated_at": ROTATED_AT,
                    "verifier_key_id": ROTATED_KEY_ID,
                    "verifier_policy_id": ROTATED_POLICY_ID,
                    "verifier_policy_hash": rotated_hash,
                },
                "expected_reasons": [],
            },
            {
                "case_id": "revoked_before_verification",
                "proof": proof,
                "lifecycle_snapshot": verifier_lifecycle_record(
                    lifecycle_status="revoked",
                    revoked_at=REVOKED_AT,
                    revocation_reason="demo_compromise_drill",
                ),
                "expected_reasons": [
                    "reviewer_packet_verifier_revoked_before_verification"
                ],
            },
            {
                "case_id": "policy_hash_mismatch_after_rotation",
                "proof": proof,
                "lifecycle_snapshot": verifier_lifecycle_record(
                    lifecycle_status="active",
                    verifier_key_id=ROTATED_KEY_ID,
                    verifier_policy_id=VERIFIER_POLICY_ID,
                    verifier_policy_hash_value=rotated_hash,
                ),
                "expected_reasons": [
                    "reviewer_packet_verifier_lifecycle_key_mismatch",
                    "reviewer_packet_verifier_lifecycle_policy_hash_mismatch",
                ],
            },
            {
                "case_id": "no_approval_required",
                "proof": None,
                "lifecycle_snapshot": None,
                "expected_reasons": [],
            },
        ],
    }
