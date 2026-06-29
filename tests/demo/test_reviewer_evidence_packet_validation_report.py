"""Tests for the Reviewer Evidence Packet validation report."""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys

from scripts.demo.export_reviewer_evidence_packet import build_reviewer_evidence_packet
from scripts.demo.validate_reviewer_evidence_packet import (
    REPORT_ID,
    REPORT_VERSION,
    _build_report_for_packet,
    build_reviewer_evidence_packet_validation_report,
)

SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


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


def test_validation_report_includes_failure_reason_catalog_provenance() -> None:
    report = build_reviewer_evidence_packet_validation_report()
    provenance = report["failure_reason_catalog_provenance"]

    assert provenance["catalog_version"] == "reviewer-failure-reason-catalog-v1"
    assert provenance["total_reasons"] > 0
    assert SHA256_HEX_RE.fullmatch(provenance["catalog_json_sha256"])
    assert SHA256_HEX_RE.fullmatch(provenance["catalog_schema_sha256"])


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

def _valid_case_packet() -> dict[str, object]:
    packet = copy.deepcopy(build_reviewer_evidence_packet())
    packet["cases"] = [
        case
        for case in packet["cases"]
        if case["case_id"] == "valid_authority_and_approval"
    ]
    return packet


def test_approval_required_packet_passes_with_matching_proof_hashes() -> None:
    report = _report_for_mutated_packet(_valid_case_packet())

    assert report["checks"]["approval_proof_continuity_valid"] is True
    assert report["checks"]["approval_proof_continuity_reasons"] == []
    assert (
        report["checks"]["verifier_lifecycle_snapshot_hash_continuity_valid"]
        is True
    )
    assert (
        report["checks"][
            "verifier_lifecycle_snapshot_hash_continuity_reasons"
        ]
        == []
    )


def test_committed_verified_approval_packet_binds_lifecycle_hash() -> None:
    packet = _valid_case_packet()
    case = packet["cases"][0]
    lifecycle_hash = case["verifier_lifecycle_summary"][
        "verifier_lifecycle_snapshot_hash"
    ]

    assert (
        case["evidence_chain_manifest_summary"][
            "human_approval_verifier_lifecycle_snapshot_hash"
        ]
        == lifecycle_hash
    )
    assert (
        case["outcome_receipt_summary"]["metadata"][
            "human_approval_verifier_lifecycle_snapshot_hash"
        ]
        == lifecycle_hash
    )


def test_validation_report_fails_when_manifest_lifecycle_hash_differs() -> None:
    packet = _valid_case_packet()
    packet["cases"][0]["evidence_chain_manifest_summary"][
        "human_approval_verifier_lifecycle_snapshot_hash"
    ] = "f" * 64

    report = _report_for_mutated_packet(packet)

    assert report["status"] == "fail"
    assert (
        "reviewer_packet_manifest_lifecycle_snapshot_hash_mismatch"
        in report["failure_reasons"]
    )


def test_validation_report_fails_when_outcome_lifecycle_hash_differs() -> None:
    packet = _valid_case_packet()
    packet["cases"][0]["outcome_receipt_summary"]["metadata"][
        "human_approval_verifier_lifecycle_snapshot_hash"
    ] = "f" * 64

    report = _report_for_mutated_packet(packet)

    assert report["status"] == "fail"
    assert (
        "reviewer_packet_outcome_lifecycle_snapshot_hash_mismatch"
        in report["failure_reasons"]
    )


def test_approval_required_packet_fails_when_manifest_proof_hash_missing() -> None:
    packet = _valid_case_packet()
    packet["cases"][0]["evidence_chain_manifest_summary"][
        "verified_human_approval_proof_hash"
    ] = None

    report = _report_for_mutated_packet(packet)

    assert report["status"] == "fail"
    assert (
        "reviewer_packet_human_approval_proof_hash_missing"
        in report["failure_reasons"]
    )


def test_approval_required_packet_fails_when_outcome_proof_hash_missing() -> None:
    packet = _valid_case_packet()
    packet["cases"][0]["outcome_receipt_summary"]["metadata"].pop(
        "verified_human_approval_proof_hash"
    )

    report = _report_for_mutated_packet(packet)

    assert report["status"] == "fail"
    assert (
        "reviewer_packet_outcome_human_approval_proof_hash_missing"
        in report["failure_reasons"]
    )


def test_approval_required_packet_fails_when_proof_hashes_differ() -> None:
    packet = _valid_case_packet()
    packet["cases"][0]["outcome_receipt_summary"]["metadata"][
        "verified_human_approval_proof_hash"
    ] = "f" * 64

    report = _report_for_mutated_packet(packet)

    assert report["status"] == "fail"
    assert (
        "reviewer_packet_human_approval_proof_hash_mismatch"
        in report["failure_reasons"]
    )


def test_approval_required_verified_packet_fails_when_link_not_verified() -> None:
    packet = _valid_case_packet()
    links = packet["cases"][0]["evidence_chain_verification_summary"][
        "verified_links"
    ]
    links.remove("verified_human_approval_proof_hash")

    report = _report_for_mutated_packet(packet)

    assert report["status"] == "fail"
    assert (
        "reviewer_packet_human_approval_proof_link_not_verified"
        in report["failure_reasons"]
    )


def test_no_approval_required_packet_passes_without_proof_hash() -> None:
    packet = _valid_case_packet()
    case = packet["cases"][0]
    case["evidence_chain_manifest_summary"]["human_approval_required"] = False
    case["evidence_chain_manifest_summary"][
        "verified_human_approval_proof_hash"
    ] = None
    case["outcome_receipt_summary"]["metadata"].pop(
        "verified_human_approval_proof_hash", None
    )
    case["evidence_chain_verification_summary"]["verified_links"].remove(
        "verified_human_approval_proof_hash"
    )

    report = _report_for_mutated_packet(packet)

    assert "reviewer_packet_human_approval_proof_hash_missing" not in report[
        "failure_reasons"
    ]
    assert "reviewer_packet_outcome_human_approval_proof_hash_missing" not in report[
        "failure_reasons"
    ]
    assert "reviewer_packet_human_approval_proof_link_not_verified" not in report[
        "failure_reasons"
    ]


def test_approval_required_packet_fails_when_verifier_id_missing() -> None:
    packet = _valid_case_packet()
    packet["cases"][0]["human_approval_summary"]["verifier_id"] = None

    report = _report_for_mutated_packet(packet)

    assert report["status"] == "fail"
    assert "reviewer_packet_verifier_id_missing" in report["failure_reasons"]


def test_approval_required_packet_fails_when_verifier_policy_id_missing() -> None:
    packet = _valid_case_packet()
    packet["cases"][0]["human_approval_summary"]["verifier_policy_id"] = None

    report = _report_for_mutated_packet(packet)

    assert report["status"] == "fail"
    assert "reviewer_packet_verifier_policy_id_missing" in report["failure_reasons"]


def test_approval_required_packet_fails_when_verifier_policy_hash_missing() -> None:
    packet = _valid_case_packet()
    packet["cases"][0]["human_approval_summary"]["verifier_policy_hash"] = None

    report = _report_for_mutated_packet(packet)

    assert report["status"] == "fail"
    assert "reviewer_packet_verifier_policy_hash_missing" in report["failure_reasons"]


def test_approval_required_packet_fails_when_verifier_policy_hashes_differ() -> None:
    packet = _valid_case_packet()
    packet["cases"][0]["outcome_receipt_summary"]["metadata"][
        "human_approval_verifier_policy_hash"
    ] = "f" * 64

    report = _report_for_mutated_packet(packet)

    assert report["status"] == "fail"
    assert "reviewer_packet_verifier_policy_hash_mismatch" in report["failure_reasons"]
