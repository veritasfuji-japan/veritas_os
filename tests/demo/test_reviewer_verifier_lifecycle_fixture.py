"""Tests for deterministic reviewer verifier lifecycle audit fixtures."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.demo.export_reviewer_evidence_packet import build_reviewer_evidence_packet
from scripts.demo.validate_reviewer_evidence_packet import (
    _case_verifier_lifecycle_reasons,
)
from scripts.demo.verifier_lifecycle_fixture import (
    demo_lifecycle_audit_fixtures,
    validate_human_approval_verifier_lifecycle_snapshot,
    verifier_lifecycle_record,
)

FIXTURE_PATH = Path(
    "docs/en/demo/fixtures/verifier-lifecycle-audit-fixtures-v1.json"
)


def _case(case_id: str) -> dict[str, Any]:
    fixtures = demo_lifecycle_audit_fixtures()
    return next(case for case in fixtures["cases"] if case["case_id"] == case_id)


@pytest.mark.parametrize(
    ("case_id", "expected_reasons"),
    [
        ("valid_at_verification_time", []),
        (
            "revoked_before_verification",
            ["reviewer_packet_verifier_revoked_before_verification"],
        ),
        (
            "policy_hash_mismatch_after_rotation",
            [
                "reviewer_packet_verifier_lifecycle_key_mismatch",
                "reviewer_packet_verifier_lifecycle_policy_hash_mismatch",
            ],
        ),
        ("no_approval_required", []),
    ],
)
def test_lifecycle_fixture_cases_validate_deterministically(
    case_id: str,
    expected_reasons: list[str],
) -> None:
    case = _case(case_id)

    assert validate_human_approval_verifier_lifecycle_snapshot(
        proof=case["proof"],
        lifecycle_snapshot=case["lifecycle_snapshot"],
    ) == expected_reasons


def test_expired_before_verification_fails() -> None:
    case = _case("valid_at_verification_time")
    expired_snapshot = verifier_lifecycle_record(
        lifecycle_status="expired",
        valid_until="2026-04-25T00:00:00+00:00",
    )

    assert validate_human_approval_verifier_lifecycle_snapshot(
        proof=case["proof"],
        lifecycle_snapshot=expired_snapshot,
    ) == ["reviewer_packet_verifier_expired_before_verification"]


def test_missing_lifecycle_snapshot_fails_only_when_approval_proof_is_present() -> None:
    case = _case("valid_at_verification_time")

    assert validate_human_approval_verifier_lifecycle_snapshot(
        proof=case["proof"],
        lifecycle_snapshot=None,
    ) == ["reviewer_packet_verifier_lifecycle_missing"]
    assert validate_human_approval_verifier_lifecycle_snapshot(
        proof=None,
        lifecycle_snapshot=None,
    ) == []


def test_reviewer_packet_exposes_valid_lifecycle_for_historical_rotation() -> None:
    packet = build_reviewer_evidence_packet()
    valid_case = next(
        case
        for case in packet["cases"]
        if case["case_id"] == "valid_authority_and_approval"
    )
    summary = valid_case["human_approval_summary"]

    assert summary["verifier_lifecycle_status"] == "rotated"
    assert summary["verifier_valid_from"] == "2026-04-01T00:00:00+00:00"
    assert summary["verifier_valid_until"] == "2026-04-30T00:00:00+00:00"
    assert summary["verifier_revoked_at"] is None
    assert (
        summary["verifier_lifecycle_policy_hash"]
        == summary["verifier_policy_hash"]
    )
    assert _case_verifier_lifecycle_reasons(valid_case) == []


def test_reviewer_packet_policy_hash_mismatch_fails_closed() -> None:
    packet = build_reviewer_evidence_packet()
    valid_case = copy.deepcopy(
        next(
            case
            for case in packet["cases"]
            if case["case_id"] == "valid_authority_and_approval"
        )
    )
    valid_case["human_approval_summary"][
        "verifier_lifecycle_policy_hash"
    ] = "0" * 64

    assert _case_verifier_lifecycle_reasons(valid_case) == [
        "reviewer_packet_verifier_lifecycle_policy_hash_mismatch"
    ]


def test_no_approval_required_path_does_not_require_lifecycle_snapshot() -> None:
    packet = build_reviewer_evidence_packet()
    no_approval_case = next(
        case for case in packet["cases"] if case["case_id"] == "missing_human_approval"
    )

    assert (
        no_approval_case["human_approval_summary"]["verification_proof_hash"]
        is None
    )
    assert _case_verifier_lifecycle_reasons(no_approval_case) == []


def test_lifecycle_fixture_file_matches_generated_fixture() -> None:
    assert json.loads(FIXTURE_PATH.read_text(encoding="utf-8")) == (
        demo_lifecycle_audit_fixtures()
    )
