"""Tests for the Reviewer Evidence Packet golden fixture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.demo.export_reviewer_evidence_packet import (
    build_reviewer_evidence_packet,
    compute_reviewer_packet_hash,
)

FIXTURE_PATH = Path(
    "docs/en/demo/fixtures/reviewer-evidence-packet-saas-permission-change-v1.json"
)
BLOCKED_CASE_IDS = {
    "missing_authority",
    "missing_human_approval",
    "expired_human_approval",
    "scope_mismatch",
}


def _load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _case_by_id(packet: dict[str, Any], case_id: str) -> dict[str, Any]:
    return next(case for case in packet["cases"] if case["case_id"] == case_id)


def test_golden_fixture_file_exists() -> None:
    assert FIXTURE_PATH.is_file()


def test_golden_fixture_parses_as_json() -> None:
    fixture = _load_fixture()
    assert isinstance(fixture, dict)


def test_golden_fixture_identity_fields_are_stable() -> None:
    fixture = _load_fixture()
    assert fixture["packet_id"] == "reviewer-evidence-packet-saas-permission-change-v1"
    assert fixture["packet_version"] == "v1"
    assert fixture["local_offline_only"] is True


def test_golden_fixture_is_pretty_printed_with_sorted_keys() -> None:
    fixture = _load_fixture()
    expected = json.dumps(fixture, indent=2, sort_keys=True) + "\n"
    assert FIXTURE_PATH.read_text(encoding="utf-8") == expected


def test_golden_fixture_contains_non_empty_packet_hash() -> None:
    fixture = _load_fixture()
    assert fixture["packet_hash"]
    assert len(fixture["packet_hash"]) == 64


def test_generated_packet_matches_golden_fixture() -> None:
    assert build_reviewer_evidence_packet() == _load_fixture()


def test_golden_fixture_packet_hash_recomputes() -> None:
    fixture = _load_fixture()
    assert compute_reviewer_packet_hash(fixture) == fixture["packet_hash"]


def test_golden_fixture_contains_required_top_level_sections() -> None:
    fixture = _load_fixture()
    assert fixture["cases"]
    assert fixture["aggregate_summary"]
    assert fixture["reviewer_notes"]


def test_every_golden_fixture_case_contains_required_summaries() -> None:
    fixture = _load_fixture()
    for case in fixture["cases"]:
        assert case["outcome_receipt_summary"]
        assert case["evidence_chain_manifest_summary"]
        assert case["evidence_chain_verification_summary"]


def test_valid_authority_and_approval_case_remains_verified() -> None:
    fixture = _load_fixture()
    case = _case_by_id(fixture, "valid_authority_and_approval")
    summary = case["evidence_chain_verification_summary"]
    assert summary["verification_status"] == "verified"


def test_blocked_cases_remain_blocked() -> None:
    fixture = _load_fixture()
    for case_id in BLOCKED_CASE_IDS:
        case = _case_by_id(fixture, case_id)
        assert case["actual_outcome"] == "block"
        assert case["outcome_receipt_summary"]["blocked"] is True


def test_golden_fixture_requires_no_network_or_environment_dependency(
    monkeypatch,
) -> None:
    monkeypatch.delenv("VERITAS_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert build_reviewer_evidence_packet() == _load_fixture()
