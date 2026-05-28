"""Tests for deterministic local/offline Outcome Receipt v1 helpers."""

from __future__ import annotations

from veritas_os.governance.outcome_receipt import (
    OutcomeReceipt,
    build_outcome_receipt,
    validate_outcome_receipt,
    with_outcome_hash,
)


def _base_receipt() -> OutcomeReceipt:
    return OutcomeReceipt(
        outcome_receipt_id="outcome-op-001",
        decision_id="decision-001",
        execution_intent_id="intent-001",
        bind_receipt_id="bind-001",
        operation_id="op-001",
        action_class="permission_change",
        target_system="mock_saas_directory",
        target_resource="contractor:external.user@example.test",
        intended_action="grant_admin_permission",
        requested_scope=["saas:grant_admin"],
        final_outcome="commit",
        committed=True,
        blocked=False,
        escalated=False,
        rolled_back=False,
        pre_state_fingerprint="pre-hash",
        post_state_fingerprint="post-hash",
        postcondition_status="passed",
        observed_effects=[{"effect_type": "permission_grant", "fixture_only": True}],
        failure_reasons=[],
        rollback_status=None,
        evaluated_at="2026-04-26T00:00:00+00:00",
        outcome_hash="",
        metadata={"fixture_only": True},
    )


def test_valid_committed_outcome_receipt_has_deterministic_non_empty_outcome_hash() -> None:
    receipt = with_outcome_hash(_base_receipt())
    assert receipt.outcome_hash


def test_same_content_produces_same_hash() -> None:
    first = with_outcome_hash(_base_receipt())
    second = with_outcome_hash(_base_receipt())
    assert first.outcome_hash == second.outcome_hash


def test_changing_meaningful_field_changes_hash() -> None:
    first = with_outcome_hash(_base_receipt())
    changed = _base_receipt()
    changed = OutcomeReceipt(**{**changed.to_dict(), "final_outcome": "block", "committed": False, "blocked": True})
    second = with_outcome_hash(changed)
    assert first.outcome_hash != second.outcome_hash


def test_outcome_hash_does_not_recursively_affect_its_own_hash() -> None:
    first = with_outcome_hash(_base_receipt())
    second = with_outcome_hash(OutcomeReceipt(**{**first.to_dict(), "outcome_hash": "different"}))
    assert first.outcome_hash == second.outcome_hash


def test_missing_receipt_fails_validation() -> None:
    result = validate_outcome_receipt(None)
    assert result.is_valid is False
    assert "outcome_receipt_missing" in result.failure_reasons


def test_committed_and_blocked_conflict_fails_validation() -> None:
    receipt = with_outcome_hash(OutcomeReceipt(**{**_base_receipt().to_dict(), "blocked": True}))
    result = validate_outcome_receipt(receipt)
    assert "outcome_receipt_committed_and_blocked_conflict" in result.failure_reasons


def test_invalid_postcondition_status_fails_validation() -> None:
    receipt = with_outcome_hash(OutcomeReceipt(**{**_base_receipt().to_dict(), "postcondition_status": "unknown"}))
    result = validate_outcome_receipt(receipt)
    assert "outcome_receipt_invalid_postcondition_status" in result.failure_reasons


def test_committed_true_with_blocked_final_outcome_fails_validation() -> None:
    receipt = with_outcome_hash(OutcomeReceipt(**{**_base_receipt().to_dict(), "final_outcome": "block", "committed": True}))
    result = validate_outcome_receipt(receipt)
    assert "outcome_receipt_committed_outcome_mismatch" in result.failure_reasons


def test_rollback_without_failure_reason_fails_validation() -> None:
    receipt = with_outcome_hash(OutcomeReceipt(**{**_base_receipt().to_dict(), "committed": False, "rolled_back": True}))
    result = validate_outcome_receipt(receipt)
    assert "outcome_receipt_rollback_without_failure_reason" in result.failure_reasons


def test_unparseable_evaluated_at_fails_validation() -> None:
    receipt = with_outcome_hash(OutcomeReceipt(**{**_base_receipt().to_dict(), "evaluated_at": "not-a-date"}))
    result = validate_outcome_receipt(receipt)
    assert "outcome_receipt_evaluated_at_unparseable" in result.failure_reasons


def test_build_outcome_receipt_returns_hash_populated_receipt() -> None:
    receipt = build_outcome_receipt(
        decision_id="decision-001",
        execution_intent_id="intent-001",
        bind_receipt_id="bind-001",
        operation_id="op-001",
        action_class="permission_change",
        target_system="mock_saas_directory",
        target_resource="contractor:external.user@example.test",
        intended_action="grant_admin_permission",
        requested_scope=["saas:grant_admin"],
        final_outcome="commit",
        evaluated_at="2026-04-26T00:00:00+00:00",
    )
    assert receipt.outcome_hash
