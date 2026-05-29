"""Tests for the Reviewer Evidence Packet validation report."""

from __future__ import annotations

import copy
import json
import subprocess
import sys

from scripts.demo.export_reviewer_evidence_packet import build_reviewer_evidence_packet
from scripts.demo.validate_reviewer_evidence_packet import (
    REPORT_ID,
    REPORT_VERSION,
    _build_report_for_packet,
    build_reviewer_evidence_packet_validation_report,
)


def test_build_reviewer_evidence_packet_validation_report_returns_dict() -> None:
    report = build_reviewer_evidence_packet_validation_report()

    assert isinstance(report, dict)


def test_validation_report_core_fields_pass() -> None:
    report = build_reviewer_evidence_packet_validation_report()

    assert report["report_id"] == REPORT_ID
    assert report["report_version"] == REPORT_VERSION
    assert report["local_offline_only"] is True
    assert report["status"] == "pass"


def test_validation_report_checks_pass() -> None:
    report = build_reviewer_evidence_packet_validation_report()
    checks = report["checks"]

    assert checks["generated_packet_matches_golden_fixture"] is True
    assert checks["packet_hash_recomputes"] is True
    assert checks["schema_file_exists"] is True
    assert checks["schema_json_parseable"] is True
    assert checks["required_top_level_fields_present"] is True
    assert checks["required_case_fields_present"] is True
    assert checks["case_expectations_passed"] is True
    assert checks["blocked_cases_have_refusal_basis"] is True
    assert checks["blocked_cases_have_outcome_failure_reasons"] is True
    assert checks["evidence_chain_verification_present"] is True
    assert checks["valid_case_chain_verified"] is True
    assert checks["no_mismatched_links_in_demo"] is True


def test_validation_report_aggregate_summary() -> None:
    report = build_reviewer_evidence_packet_validation_report()
    summary = report["aggregate_summary"]

    assert summary["total_cases"] == 5
    assert summary["blocked_cases"] == 4
    assert summary["committed_cases"] == 1
    assert summary["verified_chains"] == 5


def test_validation_report_failure_reasons_and_notes() -> None:
    report = build_reviewer_evidence_packet_validation_report()

    assert report["failure_reasons"] == []
    assert report["reviewer_notes"]


def test_validation_report_output_is_deterministic_across_calls() -> None:
    first = build_reviewer_evidence_packet_validation_report()
    second = build_reviewer_evidence_packet_validation_report()

    assert first == second


def test_validation_report_cli_exits_zero_and_prints_json() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/demo/validate_reviewer_evidence_packet.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["report_id"] == REPORT_ID
    assert payload["status"] == "pass"


def test_validation_report_requires_no_network_or_environment_dependency(
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("VERITAS_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    report = build_reviewer_evidence_packet_validation_report()

    assert report["status"] == "pass"
    assert report["local_offline_only"] is True


def _report_for_mutated_packet(packet: dict[str, object]) -> dict[str, object]:
    return _build_report_for_packet(
        packet,
        build_reviewer_evidence_packet(),
        None,
        fixture_exists=True,
        fixture_parseable=True,
        schema_exists=True,
        schema_parseable=True,
    )


def test_validation_report_detects_missing_packet_hash() -> None:
    packet = copy.deepcopy(build_reviewer_evidence_packet())
    packet.pop("packet_hash")

    report = _report_for_mutated_packet(packet)

    assert report["status"] == "fail"
    assert "packet_hash_missing" in report["failure_reasons"]


def test_validation_report_detects_invalid_packet_version() -> None:
    packet = copy.deepcopy(build_reviewer_evidence_packet())
    packet["packet_version"] = "v2"

    report = _report_for_mutated_packet(packet)

    assert report["status"] == "fail"
    assert "generated_packet_mismatch" in report["failure_reasons"]
    assert "schema_validation_failed" in report["failure_reasons"]


def test_validation_report_detects_missing_evidence_chain_verification() -> None:
    packet = copy.deepcopy(build_reviewer_evidence_packet())
    packet["cases"][0].pop("evidence_chain_verification_summary")

    report = _report_for_mutated_packet(packet)

    assert report["status"] == "fail"
    assert "required_case_fields_missing" in report["failure_reasons"]
    assert "evidence_chain_verification_missing" in report["failure_reasons"]
