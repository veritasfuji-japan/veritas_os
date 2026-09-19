"""Tests for optional Human Approval alternative-set reviewer evidence."""

from __future__ import annotations

from datetime import UTC, datetime

from veritas_os.governance.human_approval_receipt import (
    HumanApprovalReceipt,
    summarize_human_approval_alternatives_evidence,
    validate_human_approval_alternatives_evidence,
    validate_human_approval_receipt,
    with_receipt_hash,
)


def _alternatives() -> list[dict[str, object]]:
    return [
        {
            "alternative_id": "approve",
            "alternative_type": "approve",
            "available": True,
            "presented": True,
            "presented_at": "2026-04-24T23:58:00+00:00",
            "unavailable_reason": None,
        },
        {
            "alternative_id": "reject",
            "alternative_type": "reject",
            "available": True,
            "presented": True,
            "presented_at": "2026-04-24T23:58:00+00:00",
            "unavailable_reason": None,
        },
        {
            "alternative_id": "defer",
            "alternative_type": "defer",
            "available": True,
            "presented": False,
            "presented_at": None,
            "unavailable_reason": None,
        },
        {
            "alternative_id": "escalate",
            "alternative_type": "escalate",
            "available": False,
            "presented": True,
            "presented_at": "2026-04-24T23:58:00+00:00",
            "unavailable_reason": "secondary_reviewer_unavailable",
        },
    ]


def _receipt(**overrides: object) -> HumanApprovalReceipt:
    values: dict[str, object] = {
        "approval_receipt_id": "har-alt-001",
        "decision_id": "decision-alt-001",
        "execution_intent_id": "intent-alt-001",
        "approver_identity": "human:manager.alex",
        "approver_role": "engineering_manager",
        "approved_action_class": "permission_change",
        "approved_scope": ["saas:grant_admin"],
        "approval_basis_refs": ["ticket:AR-1001"],
        "approved_at": "2026-04-25T00:00:00+00:00",
        "expires_at": "2026-04-30T00:00:00+00:00",
        "policy_snapshot_id": "policy-snapshot-saas-001",
        "authority_evidence_id": "aev-saas-001",
        "approval_result": "approved",
        "signature_verified": True,
        "receipt_hash": "",
        "metadata": {"fixture": True},
    }
    values.update(overrides)
    return HumanApprovalReceipt(**values)  # type: ignore[arg-type]


def test_absent_alternatives_preserve_legacy_hash_behavior() -> None:
    implicit = _receipt()
    explicit = _receipt(
        review_alternatives=None,
        selected_alternative_id=None,
        selected_at=None,
    )

    assert implicit.to_dict() == explicit.to_dict()
    assert implicit.deterministic_digest() == explicit.deterministic_digest()
    assert "review_alternatives" not in implicit.to_dict_for_hash()
    assert "selected_alternative_id" not in implicit.to_dict_for_hash()
    assert "selected_at" not in implicit.to_dict_for_hash()


def test_alternative_order_does_not_change_receipt_hash() -> None:
    first = _receipt(
        review_alternatives=_alternatives(),
        selected_alternative_id="approve",
        selected_at="2026-04-25T00:00:00+00:00",
    )
    second = _receipt(
        review_alternatives=list(reversed(_alternatives())),
        selected_alternative_id="approve",
        selected_at="2026-04-25T00:00:00+00:00",
    )

    assert first.deterministic_digest() == second.deterministic_digest()


def test_available_and_presented_are_preserved_separately() -> None:
    receipt = with_receipt_hash(
        _receipt(
            review_alternatives=_alternatives(),
            selected_alternative_id="approve",
            selected_at="2026-04-25T00:00:00+00:00",
        )
    )

    validation = validate_human_approval_alternatives_evidence(receipt)
    summary = summarize_human_approval_alternatives_evidence(receipt)

    assert validation.is_valid is True
    assert summary["reject_alternative_available"] is True
    assert summary["reject_alternative_presented"] is True
    assert summary["available_but_not_presented_alternative_ids"] == ["defer"]
    assert summary["presented_but_unavailable_alternative_ids"] == ["escalate"]
    assert summary["selected_alternative_was_available"] is True
    assert summary["selected_alternative_was_presented"] is True


def test_selected_alternative_must_be_live_and_presented() -> None:
    receipt = _receipt(
        review_alternatives=_alternatives(),
        selected_alternative_id="escalate",
        selected_at="2026-04-25T00:00:00+00:00",
    )

    validation = validate_human_approval_alternatives_evidence(receipt)

    assert validation.is_valid is False
    assert "human_approval_selected_alternative_unavailable" in (
        validation.failure_reasons
    )


def test_presented_alternative_requires_timestamp() -> None:
    alternatives = _alternatives()
    alternatives[0] = {**alternatives[0], "presented_at": None}
    receipt = _receipt(
        review_alternatives=alternatives,
        selected_alternative_id="approve",
        selected_at="2026-04-25T00:00:00+00:00",
    )

    validation = validate_human_approval_alternatives_evidence(receipt)

    assert validation.is_valid is False
    assert "human_approval_alternative_presented_at_missing" in (
        validation.failure_reasons
    )


def test_selection_cannot_predate_presentation_or_follow_approval() -> None:
    receipt = _receipt(
        review_alternatives=_alternatives(),
        selected_alternative_id="approve",
        selected_at="2026-04-24T23:57:00+00:00",
    )
    early = validate_human_approval_alternatives_evidence(receipt)
    assert "human_approval_selected_before_presentation" in early.failure_reasons

    late = validate_human_approval_alternatives_evidence(
        _receipt(
            review_alternatives=_alternatives(),
            selected_alternative_id="approve",
            selected_at="2026-04-25T00:01:00+00:00",
        )
    )
    assert "human_approval_selected_after_approval" in late.failure_reasons


def test_alternatives_evidence_does_not_change_runtime_approval_validity() -> None:
    receipt = with_receipt_hash(
        _receipt(
            review_alternatives=_alternatives(),
            selected_alternative_id="escalate",
            selected_at="2026-04-25T00:00:00+00:00",
        )
    )

    evidence_validation = validate_human_approval_alternatives_evidence(receipt)
    runtime_validation = validate_human_approval_receipt(
        receipt,
        requested_scope=["saas:grant_admin"],
        action_class="permission_change",
        policy_snapshot_id="policy-snapshot-saas-001",
        now=datetime(2026, 4, 26, tzinfo=UTC),
    )

    assert evidence_validation.is_valid is False
    assert runtime_validation.is_valid is True


def test_alternatives_are_hash_bound_when_present() -> None:
    base = _receipt(
        review_alternatives=_alternatives(),
        selected_alternative_id="approve",
        selected_at="2026-04-25T00:00:00+00:00",
    )
    changed_alternatives = _alternatives()
    changed_alternatives[1] = {
        **changed_alternatives[1],
        "presented": False,
        "presented_at": None,
    }
    changed = _receipt(
        review_alternatives=changed_alternatives,
        selected_alternative_id="approve",
        selected_at="2026-04-25T00:00:00+00:00",
    )

    assert base.deterministic_digest() != changed.deterministic_digest()
