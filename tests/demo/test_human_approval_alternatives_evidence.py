"""Tests for the third Human Approval oversight evidence data point."""

from __future__ import annotations

from scripts.demo.export_human_approval_alternatives_evidence import (
    build_human_approval_alternatives_evidence,
)


def test_alternatives_packet_is_deterministic_and_bounded() -> None:
    first = build_human_approval_alternatives_evidence()
    second = build_human_approval_alternatives_evidence()

    assert first == second
    assert first["packet_hash"] == second["packet_hash"]
    assert len(first["packet_hash"]) == 64
    assert first["case_id"] == "valid_authority_and_approval"
    assert first["runtime_case_outcome"] == "commit"
    assert first["runtime_case_passed"] is True


def test_prior_180_second_timing_evidence_is_preserved() -> None:
    packet = build_human_approval_alternatives_evidence()

    timing = packet["prior_timing_evidence"]
    assert timing["seconds_from_latest_basis_open_to_approval"] == 180
    assert timing["timing_validation_valid"] is True


def test_primary_case_records_live_reject_and_presented_available_split() -> None:
    packet = build_human_approval_alternatives_evidence()

    evidence = packet["approve_path"]["alternatives_evidence"]
    assert evidence["alternatives_validation_valid"] is True
    assert evidence["reject_alternative_available"] is True
    assert evidence["reject_alternative_presented"] is True
    assert evidence["available_but_not_presented_alternative_ids"] == [
        "defer_review"
    ]
    assert evidence["presented_but_unavailable_alternative_ids"] == [
        "escalate_for_secondary_review"
    ]
    assert evidence["selected_alternative_id"] == "approve_requested_scope"


def test_reject_path_is_representable_without_claiming_runtime_execution() -> None:
    packet = build_human_approval_alternatives_evidence()

    reject_path = packet["reject_path_evidence_only"]
    assert reject_path["runtime_executed"] is False
    assert reject_path["alternatives_validation"]["is_valid"] is True
    assert (
        reject_path["alternatives_evidence"]["selected_alternative_id"]
        == "reject_request"
    )
    assert (
        reject_path["human_approval_receipt"]["approval_result"]
        == "denied"
    )


def test_packet_keeps_evidentiary_boundary_explicit() -> None:
    packet = build_human_approval_alternatives_evidence()

    assert "available != presented" in packet["evidentiary_limit"]
    assert "presented != considered" in packet["evidentiary_limit"]
    assert "selected != understood" in packet["evidentiary_limit"]
    assert "does not create execution permission" in packet[
        "runtime_semantics_note"
    ]
