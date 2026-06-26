"""Tests for deterministic reviewer verifier lifecycle fixtures."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from scripts.demo.verifier_lifecycle import (
    compute_verifier_lifecycle_snapshot_hash,
    validate_human_approval_verifier_lifecycle_snapshot,
    verifier_lifecycle_summary_from_human_approval,
)

FIXTURE_PATH = Path("docs/en/demo/fixtures/verifier-policy-lifecycle-audit-v1.json")


def _fixture_cases() -> dict[str, dict[str, Any]]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return {case["case_id"]: case for case in payload["cases"]}


def _validate(case: dict[str, Any]) -> list[str]:
    return validate_human_approval_verifier_lifecycle_snapshot(
        human_approval_summary=case["human_approval_summary"],
        lifecycle_snapshot=case.get("verifier_lifecycle_snapshot"),
        proof_verified_at=case.get("proof_verified_at"),
    )


def test_valid_historical_verifier_passes_after_later_rotation() -> None:
    case = _fixture_cases()["valid_at_verification_time"]

    assert _validate(case) == []


def test_revoked_before_verification_fails_closed() -> None:
    case = _fixture_cases()["revoked_before_verification"]

    assert _validate(case) == [
        "reviewer_packet_verifier_revoked_before_verification"
    ]


def test_expired_before_verification_fails_closed() -> None:
    case = copy.deepcopy(_fixture_cases()["valid_at_verification_time"])
    case["verifier_lifecycle_snapshot"]["valid_until"] = (
        "2026-04-25T00:00:00+00:00"
    )

    assert _validate(case) == [
        "reviewer_packet_verifier_expired_before_verification"
    ]


def test_policy_hash_mismatch_after_rotation_fails_closed() -> None:
    case = copy.deepcopy(_fixture_cases()["valid_at_verification_time"])
    case["human_approval_summary"]["verifier_policy_hash"] = (
        "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
    )

    assert _validate(case) == [
        "reviewer_packet_verifier_lifecycle_policy_hash_mismatch"
    ]


def test_missing_lifecycle_snapshot_fails_only_when_approval_proof_present() -> None:
    proof_case = copy.deepcopy(_fixture_cases()["valid_at_verification_time"])
    proof_case["verifier_lifecycle_snapshot"] = None
    no_approval_case = _fixture_cases()["no_approval_required"]

    assert _validate(proof_case) == ["reviewer_packet_verifier_lifecycle_missing"]
    assert _validate(no_approval_case) == []


def test_not_yet_valid_fails_closed() -> None:
    case = copy.deepcopy(_fixture_cases()["valid_at_verification_time"])
    case["verifier_lifecycle_snapshot"]["valid_from"] = (
        "2026-04-27T00:00:00+00:00"
    )

    assert _validate(case) == ["reviewer_packet_verifier_not_yet_valid"]


def test_lifecycle_fixture_expected_failure_reasons_are_deterministic() -> None:
    for case in _fixture_cases().values():
        assert _validate(case) == case["expected_failure_reasons"]
        assert (_validate(case) == []) is case["expected_valid"]


def test_lifecycle_snapshot_hash_is_deterministic() -> None:
    """Lifecycle summary hash is canonical and repeatable."""
    case = _fixture_cases()["valid_at_verification_time"]
    summary = verifier_lifecycle_summary_from_human_approval(
        case["human_approval_summary"]
    )

    assert summary is not None
    assert summary["verifier_lifecycle_snapshot_hash"] == (
        compute_verifier_lifecycle_snapshot_hash(summary)
    )
    assert verifier_lifecycle_summary_from_human_approval(
        case["human_approval_summary"]
    )["verifier_lifecycle_snapshot_hash"] == summary[
        "verifier_lifecycle_snapshot_hash"
    ]


def test_lifecycle_snapshot_hash_changes_when_valid_until_changes() -> None:
    """Changing verifier_valid_until changes lifecycle hash continuity."""
    case = _fixture_cases()["valid_at_verification_time"]
    summary = verifier_lifecycle_summary_from_human_approval(
        case["human_approval_summary"]
    )
    changed = copy.deepcopy(summary)
    changed["verifier_valid_until"] = "2026-04-25T00:00:00+00:00"

    assert summary is not None
    assert compute_verifier_lifecycle_snapshot_hash(changed) != summary[
        "verifier_lifecycle_snapshot_hash"
    ]


def test_lifecycle_snapshot_hash_changes_when_policy_hash_changes() -> None:
    """Changing verifier_policy_hash changes lifecycle hash continuity."""
    case = _fixture_cases()["valid_at_verification_time"]
    summary = verifier_lifecycle_summary_from_human_approval(
        case["human_approval_summary"]
    )
    changed = copy.deepcopy(summary)
    changed["verifier_policy_hash"] = (
        "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
    )

    assert summary is not None
    assert compute_verifier_lifecycle_snapshot_hash(changed) != summary[
        "verifier_lifecycle_snapshot_hash"
    ]
