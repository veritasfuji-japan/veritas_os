"""Regression guards for reviewer verifier-policy snapshot continuity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


REVIEWER_PACKET_FIXTURES = (
    Path(
        "docs/en/demo/fixtures/"
        "reviewer-evidence-packet-saas-permission-change-v1.json"
    ),
    Path("docs/en/demo/examples/context-bound-approval-replay-prevention-v1.json"),
    Path(
        "docs/en/demo/examples/"
        "evaluation-governance-chain-reviewer-packet-v1/"
        "reviewer-evidence-packet.generated.example.json"
    ),
    Path(
        "samples/evidence_bundle/key_provenance_review/"
        "reviewer-evidence-packet.json"
    ),
)

SNAPSHOT_FIELD_MAPPINGS = (
    (
        "verifier_id",
        "human_approval_verifier_id",
        "human_approval_verifier_id",
    ),
    (
        "verifier_key_id",
        "human_approval_verifier_key_id",
        "human_approval_verifier_key_id",
    ),
    (
        "verifier_policy_id",
        "human_approval_verifier_policy_id",
        "human_approval_verifier_policy_id",
    ),
    (
        "verifier_policy_hash",
        "human_approval_verifier_policy_hash",
        "human_approval_verifier_policy_hash",
    ),
    (
        "verification_proof_hash",
        "verified_human_approval_proof_hash",
        "verified_human_approval_proof_hash",
    ),
)


def _load_reviewer_packet(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _cases(packet: dict[str, Any], path: Path) -> list[dict[str, Any]]:
    cases = packet.get("cases")
    if not isinstance(cases, list):
        pytest.skip(f"{path} does not contain reviewer packet cases")
    return cases


def _case_id(case: dict[str, Any]) -> str:
    return str(case.get("case_id", "<missing case_id>"))


def _is_valid_approval_case(case: dict[str, Any]) -> bool:
    human_approval = case.get("human_approval_summary", {})
    manifest = case.get("evidence_chain_manifest_summary", {})
    verification = case.get("evidence_chain_verification_summary", {})

    if not isinstance(human_approval, dict) or not isinstance(manifest, dict):
        return False

    has_success_outcome = case.get("expected_outcome") in {
        "commit_eligible",
        "commit",
    } or verification.get("verification_status") == "verified"

    return bool(
        manifest.get("human_approval_required") is True
        and human_approval.get("receipt_hash_present") is True
        and human_approval.get("verification_proof_hash")
        and has_success_outcome
    )


def _failure_reasons(case: dict[str, Any]) -> list[Any]:
    reasons: list[Any] = []
    for summary_name in (
        "human_approval_summary",
        "outcome_receipt_summary",
        "evidence_chain_verification_summary",
    ):
        summary = case.get(summary_name, {})
        if not isinstance(summary, dict):
            continue
        reasons.extend(summary.get("failure_reasons") or [])
    reasons.extend(case.get("failure_reasons") or [])
    return reasons


@pytest.mark.parametrize("fixture_path", REVIEWER_PACKET_FIXTURES)
def test_verifier_policy_snapshot_continuity_across_reviewer_packets(
    fixture_path: Path,
) -> None:
    packet = _load_reviewer_packet(fixture_path)

    for case in _cases(packet, fixture_path):
        if not _is_valid_approval_case(case):
            continue

        human_approval = case["human_approval_summary"]
        manifest = case["evidence_chain_manifest_summary"]
        metadata = case["outcome_receipt_summary"]["metadata"]
        case_label = f"{fixture_path}:{_case_id(case)}"

        for approval_field, manifest_field, metadata_field in SNAPSHOT_FIELD_MAPPINGS:
            approval_value = human_approval.get(approval_field)
            manifest_value = manifest.get(manifest_field)
            metadata_value = metadata.get(metadata_field)

            assert approval_value, f"{case_label} missing {approval_field}"
            assert manifest_value, f"{case_label} missing {manifest_field}"
            assert metadata_value, f"{case_label} missing metadata.{metadata_field}"
            assert approval_value == manifest_value == metadata_value, (
                f"{case_label} mismatched verifier snapshot field "
                f"{approval_field}/{manifest_field}/{metadata_field}"
            )


@pytest.mark.parametrize("fixture_path", REVIEWER_PACKET_FIXTURES)
def test_verified_approval_cases_include_verified_proof_hash_link(
    fixture_path: Path,
) -> None:
    packet = _load_reviewer_packet(fixture_path)

    for case in _cases(packet, fixture_path):
        if not _is_valid_approval_case(case):
            continue

        verification = case["evidence_chain_verification_summary"]
        verified_links = verification.get("verified_links") or []

        assert "verified_human_approval_proof_hash" in verified_links, (
            f"{fixture_path}:{_case_id(case)} missing "
            "verified_human_approval_proof_hash verified link"
        )


@pytest.mark.parametrize("fixture_path", REVIEWER_PACKET_FIXTURES)
def test_failed_or_negative_approval_cases_with_null_verifier_fields_are_unambiguous(
    fixture_path: Path,
) -> None:
    packet = _load_reviewer_packet(fixture_path)

    for case in _cases(packet, fixture_path):
        human_approval = case.get("human_approval_summary", {})
        if not isinstance(human_approval, dict):
            continue

        verifier_fields_are_null = all(
            human_approval.get(field) is None
            for field in (
                "verification_proof_hash",
                "verifier_id",
                "verifier_key_id",
                "verifier_policy_id",
                "verifier_policy_hash",
            )
        )
        if not verifier_fields_are_null:
            continue

        receipt_missing = human_approval.get("receipt_hash_present") is False
        expected_block = case.get("expected_outcome") == "block"
        has_failure_reasons = bool(_failure_reasons(case))

        assert receipt_missing or expected_block or has_failure_reasons, (
            f"{fixture_path}:{_case_id(case)} has receipt_hash_present=true, "
            "null verifier/proof fields, and no failure reason"
        )
