"""Regression guards for committed reviewer verifier lifecycle evidence."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

REVIEWER_PACKET_PATHS = (
    Path("docs/en/demo/fixtures/reviewer-evidence-packet-saas-permission-change-v1.json"),
    Path("docs/en/demo/examples/context-bound-approval-replay-prevention-v1.json"),
    Path(
        "docs/en/demo/examples/"
        "evaluation-governance-chain-reviewer-packet-v1/"
        "reviewer-evidence-packet.generated.example.json"
    ),
    Path(
        "docs/en/demo/examples/evaluation-governance-reviewer-demo-v1/"
        "generated/reviewer-evidence-packet.generated.example.json"
    ),
    Path("samples/evidence_bundle/key_provenance_review/reviewer-evidence-packet.json"),
)


def _load_reviewer_cases(path: Path) -> list[dict[str, Any]]:
    packet = json.loads(path.read_text(encoding="utf-8"))
    cases = packet.get("cases") if isinstance(packet, dict) else None
    if not isinstance(cases, list):
        pytest.skip(f"{path} is not a reviewer packet structure")
    return [case for case in cases if isinstance(case, dict)]


def _is_commit_eligible(case: dict[str, Any]) -> bool:
    return (
        case.get("actual_outcome") == "commit"
        or case.get("runtime_recommended_outcome") == "commit"
        or case.get("expected_outcome") == "commit_eligible"
    )


def _has_verification_proof(case: dict[str, Any]) -> bool:
    human_approval = case.get("human_approval_summary")
    return (
        isinstance(human_approval, dict)
        and human_approval.get("verification_proof_hash") is not None
    )


def _parse_timestamp(value: str | None, field_name: str) -> datetime:
    assert value is not None, f"{field_name} must be present"
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.mark.parametrize("packet_path", REVIEWER_PACKET_PATHS)
def test_commit_eligible_reviewer_cases_have_clean_lifecycle_evidence(
    packet_path: Path,
) -> None:
    """Committed approval cases must not carry verifier lifecycle failures."""
    for case in _load_reviewer_cases(packet_path):
        if not (_is_commit_eligible(case) and _has_verification_proof(case)):
            continue

        case_id = case.get("case_id", "<unknown>")
        human_approval = case["human_approval_summary"]
        lifecycle = case.get("verifier_lifecycle_summary")

        assert lifecycle is not None, f"{packet_path}:{case_id} lifecycle missing"
        assert lifecycle.get("failure_reasons") == [], (
            f"{packet_path}:{case_id} committed approval must not carry "
            "verifier lifecycle failure reasons"
        )

        verified_at = _parse_timestamp(
            human_approval.get("verified_at"),
            f"{packet_path}:{case_id} human_approval_summary.verified_at",
        )
        valid_from = _parse_timestamp(
            lifecycle.get("verifier_valid_from"),
            f"{packet_path}:{case_id} verifier_valid_from",
        )
        assert verified_at >= valid_from, (
            f"{packet_path}:{case_id} verified_at precedes verifier_valid_from"
        )

        valid_until = lifecycle.get("verifier_valid_until")
        if valid_until is not None:
            assert verified_at <= _parse_timestamp(
                valid_until,
                f"{packet_path}:{case_id} verifier_valid_until",
            ), f"{packet_path}:{case_id} verified_at exceeds verifier_valid_until"

        revoked_at = lifecycle.get("verifier_revoked_at")
        if revoked_at is not None:
            assert verified_at < _parse_timestamp(
                revoked_at,
                f"{packet_path}:{case_id} verifier_revoked_at",
            ), f"{packet_path}:{case_id} verified_at is not before verifier_revoked_at"


@pytest.mark.parametrize("packet_path", REVIEWER_PACKET_PATHS)
def test_lifecycle_failure_reasons_are_never_commit_eligible(
    packet_path: Path,
) -> None:
    """Lifecycle failure reasons are allowed only on non-commit cases."""
    for case in _load_reviewer_cases(packet_path):
        lifecycle = case.get("verifier_lifecycle_summary")
        if not isinstance(lifecycle, dict) or not lifecycle.get("failure_reasons"):
            continue

        case_id = case.get("case_id", "<unknown>")
        assert case.get("actual_outcome") != "commit", (
            f"{packet_path}:{case_id} lifecycle failure must not commit"
        )
        assert case.get("runtime_recommended_outcome") != "commit", (
            f"{packet_path}:{case_id} lifecycle failure must not recommend commit"
        )
        assert case.get("expected_outcome") != "commit_eligible", (
            f"{packet_path}:{case_id} lifecycle failure must not be commit eligible"
        )


@pytest.mark.parametrize("packet_path", REVIEWER_PACKET_PATHS)
def test_lifecycle_continuity_failures_are_never_commit_eligible(
    packet_path: Path,
) -> None:
    """Lifecycle hash continuity failures are allowed only on block cases."""
    for case in _load_reviewer_cases(packet_path):
        verification = case.get("evidence_chain_verification_summary")
        if not isinstance(verification, dict):
            continue
        continuity_verified = verification.get(
            "human_approval_verifier_lifecycle_snapshot_hash_continuity_verified"
        )
        failure_reasons = verification.get(
            "human_approval_verifier_lifecycle_snapshot_hash_continuity_failure_reasons"
        )
        if continuity_verified is True and failure_reasons == []:
            continue

        case_id = case.get("case_id", "<unknown>")
        assert case.get("actual_outcome") != "commit", (
            f"{packet_path}:{case_id} lifecycle continuity failure must not commit"
        )
        assert case.get("runtime_recommended_outcome") != "commit", (
            f"{packet_path}:{case_id} lifecycle continuity failure must not "
            "recommend commit"
        )
        assert case.get("expected_outcome") != "commit_eligible", (
            f"{packet_path}:{case_id} lifecycle continuity failure must not be "
            "commit eligible"
        )
