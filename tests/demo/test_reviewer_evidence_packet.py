"""Tests for the local/offline Reviewer Evidence Packet export."""

from __future__ import annotations

from scripts.demo.export_reviewer_evidence_packet import (
    build_reviewer_evidence_packet,
    compute_reviewer_packet_hash,
    with_packet_hash,
)


def _case_by_id(packet: dict[str, object], case_id: str) -> dict[str, object]:
    cases = packet["cases"]
    assert isinstance(cases, list)
    return next(case for case in cases if case["case_id"] == case_id)


def test_build_reviewer_evidence_packet_returns_dict() -> None:
    packet = build_reviewer_evidence_packet()
    assert isinstance(packet, dict)


def test_packet_identity_fields_are_stable() -> None:
    packet = build_reviewer_evidence_packet()
    assert packet["packet_id"] == "reviewer-evidence-packet-saas-permission-change-v1"
    assert packet["packet_version"] == "v1"
    assert packet["local_offline_only"] is True


def test_packet_includes_cases_aggregate_summary_and_reviewer_notes() -> None:
    packet = build_reviewer_evidence_packet()
    assert packet["cases"]
    assert isinstance(packet["aggregate_summary"], dict)
    assert packet["reviewer_notes"]


def test_every_case_includes_required_nested_summaries() -> None:
    packet = build_reviewer_evidence_packet()
    for case in packet["cases"]:
        assert case["outcome_receipt_summary"]
        assert case["evidence_chain_manifest_summary"]
        assert case["evidence_chain_verification_summary"]


def test_valid_authority_and_approval_case_commits_or_is_commit_eligible() -> None:
    packet = build_reviewer_evidence_packet()
    case = _case_by_id(packet, "valid_authority_and_approval")
    assert case["actual_outcome"] in {"commit", "commit_eligible"}


def test_valid_authority_and_approval_chain_verification_is_verified() -> None:
    packet = build_reviewer_evidence_packet()
    case = _case_by_id(packet, "valid_authority_and_approval")
    summary = case["evidence_chain_verification_summary"]
    assert summary["verification_status"] == "verified"


def test_blocked_cases_are_blocked() -> None:
    packet = build_reviewer_evidence_packet()
    for case_id in [
        "missing_authority",
        "missing_human_approval",
        "expired_human_approval",
        "scope_mismatch",
    ]:
        case = _case_by_id(packet, case_id)
        assert case["actual_outcome"] == "block"
        assert case["outcome_receipt_summary"]["blocked"] is True


def test_human_approval_summary_is_compact_and_deterministic() -> None:
    packet = build_reviewer_evidence_packet()
    case = _case_by_id(packet, "missing_human_approval")
    summary = case["human_approval_summary"]
    assert summary == {
        "approved": False,
        "approval_receipt_id": None,
        "approver_identity": None,
        "approver_role": None,
        "approved_scope": [],
        "receipt_hash_present": False,
        "failure_reasons": ["human_approval_missing"],
    }


def test_aggregate_summary_counts_match_cases() -> None:
    packet = build_reviewer_evidence_packet()
    cases = packet["cases"]
    aggregate_summary = packet["aggregate_summary"]
    assert aggregate_summary["total_cases"] == len(cases)
    assert aggregate_summary["blocked_cases"] == sum(
        1 for case in cases if case["outcome_receipt_summary"]["blocked"] is True
    )
    assert aggregate_summary["committed_cases"] == sum(
        1 for case in cases if case["outcome_receipt_summary"]["committed"] is True
    )
    assert aggregate_summary["verified_chains"] == sum(
        1
        for case in cases
        if case["evidence_chain_verification_summary"]["verification_status"] == "verified"
    )


def test_packet_hash_is_non_empty_sha256_hex() -> None:
    packet = build_reviewer_evidence_packet()
    assert packet["packet_hash"]
    assert len(packet["packet_hash"]) == 64


def test_same_packet_content_produces_same_packet_hash() -> None:
    first = build_reviewer_evidence_packet()
    second = build_reviewer_evidence_packet()
    assert first["packet_hash"] == second["packet_hash"]
    assert compute_reviewer_packet_hash(first) == compute_reviewer_packet_hash(second)


def test_changing_meaningful_field_changes_packet_hash() -> None:
    packet = build_reviewer_evidence_packet()
    changed = {**packet, "title": "Changed reviewer title"}
    assert compute_reviewer_packet_hash(changed) != packet["packet_hash"]


def test_packet_hash_does_not_recursively_affect_itself() -> None:
    packet = build_reviewer_evidence_packet()
    changed = {**packet, "packet_hash": "0" * 64}
    assert compute_reviewer_packet_hash(packet) == compute_reviewer_packet_hash(changed)
    assert with_packet_hash(changed)["packet_hash"] == packet["packet_hash"]


def test_no_network_or_environment_dependency_required(monkeypatch) -> None:
    monkeypatch.delenv("VERITAS_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    packet = build_reviewer_evidence_packet()
    assert packet["local_offline_only"] is True
