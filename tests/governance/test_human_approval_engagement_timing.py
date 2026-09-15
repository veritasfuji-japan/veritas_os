from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from veritas_os.governance.human_approval_receipt import (
    HumanApprovalReceipt,
    summarize_human_approval_engagement_timing,
    validate_human_approval_engagement_timing,
    validate_human_approval_receipt,
    with_receipt_hash,
)
from veritas_os.security.hash import sha256_of_canonical_json


def _receipt(**overrides: object) -> HumanApprovalReceipt:
    payload: dict[str, object] = {
        "approval_receipt_id": "har-engagement-001",
        "decision_id": "decision-saas-001",
        "execution_intent_id": "intent-saas-001",
        "approver_identity": "human:manager.alex",
        "approver_role": "engineering_manager",
        "approved_action_class": "permission_change",
        "approved_scope": ["saas:grant_admin"],
        "approval_basis_refs": ["ticket:AR-1001", "manager_approval:MA-2002"],
        "approved_at": "2026-04-25T00:00:00+00:00",
        "expires_at": "2026-04-30T00:00:00+00:00",
        "policy_snapshot_id": "policy-snapshot-saas-001",
        "authority_evidence_id": "aev-saas-001",
        "approval_result": "approved",
        "signature_verified": True,
        "receipt_hash": "",
        "metadata": {"fixture": True},
    }
    payload.update(overrides)
    return HumanApprovalReceipt(**payload)  # type: ignore[arg-type]


def _valid_timing() -> dict[str, str]:
    return {
        "ticket:AR-1001": "2026-04-24T23:55:00+00:00",
        "manager_approval:MA-2002": "2026-04-24T23:57:00+00:00",
    }


def test_absent_timing_preserves_legacy_serialization_and_digest() -> None:
    receipt = _receipt()
    serialized = receipt.to_dict()

    assert "approval_basis_opened_at" not in serialized

    legacy_payload = dict(serialized)
    legacy_payload.pop("receipt_hash")
    assert receipt.deterministic_digest() == sha256_of_canonical_json(legacy_payload)


def test_present_timing_is_hashed_and_dictionary_order_is_canonical() -> None:
    first = _receipt(approval_basis_opened_at=_valid_timing())
    second = _receipt(
        approval_basis_opened_at={
            "manager_approval:MA-2002": "2026-04-24T23:57:00+00:00",
            "ticket:AR-1001": "2026-04-24T23:55:00+00:00",
        }
    )
    without_timing = _receipt()

    assert first.deterministic_digest() == second.deterministic_digest()
    assert first.deterministic_digest() != without_timing.deterministic_digest()
    assert list(first.to_dict()["approval_basis_opened_at"]) == [
        "manager_approval:MA-2002",
        "ticket:AR-1001",
    ]


def test_valid_timing_before_approval_is_accepted() -> None:
    result = validate_human_approval_engagement_timing(
        _receipt(approval_basis_opened_at=_valid_timing())
    )

    assert result.is_valid is True
    assert result.failure_reasons == []


def test_timing_after_approval_is_rejected_by_evidence_validator() -> None:
    result = validate_human_approval_engagement_timing(
        _receipt(
            approval_basis_opened_at={
                "ticket:AR-1001": "2026-04-25T00:00:01+00:00"
            }
        )
    )

    assert result.is_valid is False
    assert result.failure_reasons == ["human_approval_engagement_after_approval"]


def test_unknown_basis_reference_is_rejected_by_evidence_validator() -> None:
    result = validate_human_approval_engagement_timing(
        _receipt(
            approval_basis_opened_at={
                "ticket:UNKNOWN": "2026-04-24T23:55:00+00:00"
            }
        )
    )

    assert result.is_valid is False
    assert result.failure_reasons == ["human_approval_engagement_unknown_basis_ref"]


def test_timezone_naive_signal_is_rejected() -> None:
    result = validate_human_approval_engagement_timing(
        _receipt(
            approval_basis_opened_at={
                "ticket:AR-1001": "2026-04-24T23:55:00"
            }
        )
    )

    assert result.is_valid is False
    assert result.failure_reasons == ["human_approval_engagement_timestamp_invalid"]


def test_partial_timing_mapping_is_valid_but_marked_incomplete() -> None:
    receipt = _receipt(
        approval_basis_opened_at={
            "ticket:AR-1001": "2026-04-24T23:55:00+00:00"
        }
    )

    validation = validate_human_approval_engagement_timing(receipt)
    summary = summarize_human_approval_engagement_timing(receipt)

    assert validation.is_valid is True
    assert summary["all_approval_basis_refs_have_open_signal"] is False
    assert summary["seconds_from_latest_basis_open_to_approval"] == 300


def test_valid_fixture_summary_reports_three_minute_latest_open_interval() -> None:
    summary = summarize_human_approval_engagement_timing(
        _receipt(approval_basis_opened_at=_valid_timing())
    )

    assert summary == {
        "approval_basis_opened_at": {
            "manager_approval:MA-2002": "2026-04-24T23:57:00+00:00",
            "ticket:AR-1001": "2026-04-24T23:55:00+00:00",
        },
        "all_approval_basis_refs_have_open_signal": True,
        "seconds_from_latest_basis_open_to_approval": 180,
        "timing_validation_valid": True,
        "timing_validation_failure_reasons": [],
    }


def test_timing_signal_does_not_change_runtime_approval_validity() -> None:
    invalid_evidence_signal = _receipt(
        approval_basis_opened_at={
            "ticket:AR-1001": "2026-04-25T00:00:01+00:00"
        }
    )

    timing_validation = validate_human_approval_engagement_timing(
        invalid_evidence_signal
    )
    runtime_validation = validate_human_approval_receipt(
        invalid_evidence_signal,
        requested_scope=["saas:grant_admin"],
        action_class="permission_change",
        policy_snapshot_id="policy-snapshot-saas-001",
        now=datetime(2026, 4, 26, tzinfo=UTC),
    )

    assert timing_validation.is_valid is False
    assert runtime_validation.is_valid is True
    assert runtime_validation.failure_reasons == []


def test_with_receipt_hash_preserves_timing_evidence() -> None:
    receipt = _receipt(approval_basis_opened_at=_valid_timing())
    finalized = with_receipt_hash(receipt)

    assert finalized.receipt_hash == receipt.deterministic_digest()
    assert finalized.approval_basis_opened_at == _valid_timing()
    assert finalized.to_dict()["approval_basis_opened_at"] == {
        "manager_approval:MA-2002": "2026-04-24T23:57:00+00:00",
        "ticket:AR-1001": "2026-04-24T23:55:00+00:00",
    }


def test_round_trip_without_timing_remains_backward_compatible() -> None:
    original = _receipt()
    finalized = with_receipt_hash(original)
    round_tripped = HumanApprovalReceipt(**finalized.to_dict())

    assert round_tripped == finalized
    assert round_tripped.approval_basis_opened_at is None


def test_round_trip_with_timing_preserves_hash_bound_signal() -> None:
    original = _receipt(approval_basis_opened_at=_valid_timing())
    finalized = with_receipt_hash(original)
    round_tripped = HumanApprovalReceipt(**finalized.to_dict())

    assert round_tripped == finalized
    assert round_tripped.deterministic_digest() == original.deterministic_digest()
