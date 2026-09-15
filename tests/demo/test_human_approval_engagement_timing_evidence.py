from __future__ import annotations

from scripts.demo.export_human_approval_engagement_timing_evidence import (
    build_human_approval_engagement_timing_evidence,
)
from veritas_os.security.hash import sha256_of_canonical_json


def test_engagement_timing_packet_is_deterministic_and_bounded() -> None:
    first = build_human_approval_engagement_timing_evidence()
    second = build_human_approval_engagement_timing_evidence()

    assert first == second
    assert first["case_id"] == "valid_authority_and_approval"
    assert first["runtime_case_outcome"] == "commit"
    assert first["runtime_case_passed"] is True
    assert first["boundary_note"] == (
        "local/offline fixture only; no live SaaS/IAM/IdP integration"
    )

    timing = first["engagement_timing"]
    assert timing["approval_basis_opened_at"] == {
        "manager_approval:MA-2002": "2026-04-24T23:57:00+00:00",
        "ticket:AR-1001": "2026-04-24T23:55:00+00:00",
    }
    assert timing["all_approval_basis_refs_have_open_signal"] is True
    assert timing["seconds_from_latest_basis_open_to_approval"] == 180
    assert timing["timing_validation_valid"] is True
    assert timing["timing_validation_failure_reasons"] == []


def test_engagement_timing_is_bound_into_receipt_hash() -> None:
    packet = build_human_approval_engagement_timing_evidence()
    receipt = packet["human_approval_receipt"]

    assert receipt["approval_basis_opened_at"] == {
        "manager_approval:MA-2002": "2026-04-24T23:57:00+00:00",
        "ticket:AR-1001": "2026-04-24T23:55:00+00:00",
    }
    assert receipt["receipt_hash"]


def test_packet_hash_covers_reviewer_evidence() -> None:
    packet = build_human_approval_engagement_timing_evidence()
    packet_hash = packet["packet_hash"]
    payload = dict(packet)
    payload.pop("packet_hash")

    assert packet_hash == sha256_of_canonical_json(payload)


def test_packet_does_not_claim_meaningful_review() -> None:
    packet = build_human_approval_engagement_timing_evidence()
    limit = packet["evidentiary_limit"]

    assert "does not prove" in limit
    assert "read" in limit
    assert "understood" in limit
    assert "independently evaluated" in limit
