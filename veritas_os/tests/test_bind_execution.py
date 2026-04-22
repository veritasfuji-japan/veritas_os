"""Deterministic tests for native bind-boundary execution orchestration."""

from __future__ import annotations

import pytest

from veritas_os.logging.encryption import generate_key
from veritas_os.policy.bind_artifacts import find_bind_receipts
from veritas_os.policy.bind_artifacts import ExecutionIntent, FinalOutcome
from veritas_os.policy.bind_execution import ReferenceBindAdapter, execute_bind_boundary


def _intent(
    expected_fingerprint: str = "",
    *,
    ttl_seconds: int | None = None,
    approval_context: dict[str, object] | None = None,
    policy_lineage: dict[str, object] | None = None,
) -> ExecutionIntent:
    return ExecutionIntent(
        execution_intent_id="ei-001",
        decision_id="dec-001",
        request_id="req-001",
        policy_snapshot_id="policy-v1",
        actor_identity="operator",
        target_system="reference",
        target_resource="state",
        intended_action="mutate",
        decision_hash="a" * 64,
        decision_ts="2026-04-20T12:00:00Z",
        ttl_seconds=ttl_seconds,
        expected_state_fingerprint=expected_fingerprint,
        approval_context=approval_context,
        policy_lineage=policy_lineage,
    )


@pytest.fixture()
def trustlog_env(tmp_path, monkeypatch):
    """Redirect TrustLog writes to a temporary log path."""
    from veritas_os.logging import trust_log

    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
    monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(trust_log, "LOG_JSON", tmp_path / "trust_log.json", raising=False)
    monkeypatch.setattr(trust_log, "LOG_JSONL", tmp_path / "trust_log.jsonl", raising=False)
    monkeypatch.setattr(trust_log, "_append_stats", {"success": 0, "failure": 0}, raising=False)

    def _open_for_append():
        trust_log.LOG_JSONL.parent.mkdir(parents=True, exist_ok=True)
        return open(trust_log.LOG_JSONL, "a", encoding="utf-8")

    monkeypatch.setattr(trust_log, "open_trust_log_for_append", _open_for_append)
    return tmp_path


def test_bind_execution_success_committed() -> None:
    adapter = ReferenceBindAdapter(state={"version": 1}, pending_changes={"version": 2})
    intent = _intent(expected_fingerprint=adapter.fingerprint_state({"version": 1}))

    receipt = execute_bind_boundary(
        execution_intent=intent,
        adapter=adapter,
        bind_ts="2026-04-20T12:00:10Z",
        bind_receipt_id="br-success",
    )

    assert receipt.final_outcome is FinalOutcome.COMMITTED
    assert receipt.live_state_fingerprint_before
    assert receipt.live_state_fingerprint_after
    assert adapter.state["version"] == 2


def test_bind_execution_authority_failure_is_blocked() -> None:
    adapter = ReferenceBindAdapter(
        state={"version": 1},
        pending_changes={"version": 2},
        authority_signal=False,
    )
    intent = _intent(expected_fingerprint=adapter.fingerprint_state({"version": 1}))

    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter)

    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert adapter.state["version"] == 1


def test_bind_execution_constraint_failure_is_blocked() -> None:
    adapter = ReferenceBindAdapter(
        state={"version": 1},
        pending_changes={"version": 2},
        constraint_signals={"critical_constraint": False},
    )
    intent = _intent(expected_fingerprint=adapter.fingerprint_state({"version": 1}))

    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter)

    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert "BIND_CONSTRAINTS_VIOLATED" in receipt.admissibility_result["reason_codes"]


def test_bind_execution_runtime_risk_failure_is_blocked() -> None:
    adapter = ReferenceBindAdapter(
        state={"version": 1},
        pending_changes={"version": 2},
        runtime_risk_signal=False,
    )
    intent = _intent(expected_fingerprint=adapter.fingerprint_state({"version": 1}))

    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter)

    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert "BIND_RUNTIME_RISK_UNACCEPTABLE" in receipt.admissibility_result["reason_codes"]


def test_bind_execution_drift_failure_is_blocked() -> None:
    adapter = ReferenceBindAdapter(state={"version": 1}, pending_changes={"version": 2})
    intent = _intent(expected_fingerprint=adapter.fingerprint_state({"version": 0}))

    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter)

    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert "BIND_DRIFT_DETECTED" in receipt.admissibility_result["reason_codes"]


def test_bind_execution_snapshot_failure_is_snapshot_failed() -> None:
    adapter = ReferenceBindAdapter(
        state={"version": 1},
        pending_changes={"version": 2},
        snapshot_success=False,
    )

    receipt = execute_bind_boundary(execution_intent=_intent(expected_fingerprint="x"), adapter=adapter)

    assert receipt.final_outcome is FinalOutcome.SNAPSHOT_FAILED


def test_bind_execution_apply_failure_is_apply_failed() -> None:
    adapter = ReferenceBindAdapter(
        state={"version": 1},
        pending_changes={"version": 2},
        apply_success=False,
    )
    intent = _intent(expected_fingerprint=adapter.fingerprint_state({"version": 1}))

    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter)

    assert receipt.final_outcome is FinalOutcome.APPLY_FAILED
    assert adapter.state["version"] == 1


def test_bind_execution_apply_failure_can_rollback_via_policy() -> None:
    adapter = ReferenceBindAdapter(
        state={"version": 1},
        pending_changes={"version": 2},
        apply_success=False,
        revert_success=True,
    )
    intent = _intent(
        expected_fingerprint=adapter.fingerprint_state({"version": 1}),
        policy_lineage={"bind_adjudication": {"rollback_on_apply_failure": True}},
    )

    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter)

    assert receipt.final_outcome is FinalOutcome.ROLLED_BACK
    assert receipt.rollback_reason.startswith("BIND_APPLY_FAILED:")
    assert adapter.state["version"] == 1


def test_bind_execution_postcondition_failure_rolls_back() -> None:
    adapter = ReferenceBindAdapter(
        state={"version": 1},
        pending_changes={"version": 2},
        postcondition_success=False,
        revert_success=True,
    )
    intent = _intent(expected_fingerprint=adapter.fingerprint_state({"version": 1}))

    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter)

    assert receipt.final_outcome is FinalOutcome.ROLLED_BACK
    assert receipt.rollback_reason == "BIND_POSTCONDITION_FAILED"
    assert adapter.state["version"] == 1


def test_bind_execution_revert_failure_escalates_explicitly() -> None:
    adapter = ReferenceBindAdapter(
        state={"version": 1},
        pending_changes={"version": 2},
        postcondition_success=False,
        revert_success=False,
    )
    intent = _intent(expected_fingerprint=adapter.fingerprint_state({"version": 1}))

    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter)

    assert receipt.final_outcome is FinalOutcome.ESCALATED
    assert receipt.escalation_reason


def test_bind_execution_is_deterministic_for_same_inputs() -> None:
    adapter_a = ReferenceBindAdapter(state={"version": 1}, pending_changes={"version": 2})
    adapter_b = ReferenceBindAdapter(state={"version": 1}, pending_changes={"version": 2})
    intent = _intent(expected_fingerprint=adapter_a.fingerprint_state({"version": 1}))

    receipt_a = execute_bind_boundary(
        execution_intent=intent,
        adapter=adapter_a,
        bind_ts="2026-04-20T12:00:10Z",
        bind_receipt_id="br-deterministic",
        append_trustlog=False,
    )
    receipt_b = execute_bind_boundary(
        execution_intent=intent,
        adapter=adapter_b,
        bind_ts="2026-04-20T12:00:10Z",
        bind_receipt_id="br-deterministic",
        append_trustlog=False,
    )

    assert receipt_a.to_dict() == receipt_b.to_dict()


def test_bind_execution_success_auto_appends_trustlog_receipt(trustlog_env) -> None:
    """Committed outcome should be returned as TrustLog-linked bind receipt."""
    adapter = ReferenceBindAdapter(state={"version": 1}, pending_changes={"version": 2})
    intent = _intent(expected_fingerprint=adapter.fingerprint_state({"version": 1}))

    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter)

    assert receipt.final_outcome is FinalOutcome.COMMITTED
    assert receipt.trustlog_hash
    matched = find_bind_receipts(bind_receipt_id=receipt.bind_receipt_id)
    assert len(matched) == 1
    assert matched[0].final_outcome is FinalOutcome.COMMITTED


def test_bind_execution_blocked_auto_appends_trustlog_receipt(trustlog_env) -> None:
    """Blocked outcome should also be persisted to TrustLog lineage."""
    adapter = ReferenceBindAdapter(
        state={"version": 1},
        pending_changes={"version": 2},
        authority_signal=False,
    )
    intent = _intent(expected_fingerprint=adapter.fingerprint_state({"version": 1}))

    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter)

    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert receipt.trustlog_hash
    matched = find_bind_receipts(bind_receipt_id=receipt.bind_receipt_id)
    assert len(matched) == 1
    assert matched[0].final_outcome is FinalOutcome.BLOCKED


def test_bind_execution_rolled_back_auto_appends_trustlog_receipt(trustlog_env) -> None:
    """Rolled-back outcome should be persisted to TrustLog lineage."""
    adapter = ReferenceBindAdapter(
        state={"version": 1},
        pending_changes={"version": 2},
        postcondition_success=False,
        revert_success=True,
    )
    intent = _intent(expected_fingerprint=adapter.fingerprint_state({"version": 1}))

    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter)

    assert receipt.final_outcome is FinalOutcome.ROLLED_BACK
    assert receipt.trustlog_hash
    matched = find_bind_receipts(bind_receipt_id=receipt.bind_receipt_id)
    assert len(matched) == 1
    assert matched[0].final_outcome is FinalOutcome.ROLLED_BACK


def test_bind_execution_trustlog_lineage_traversal_by_all_ids(trustlog_env) -> None:
    """Bind lineage must be traversable by decision/intent/receipt identifiers."""
    adapter = ReferenceBindAdapter(state={"version": 1}, pending_changes={"version": 2})
    intent = _intent(expected_fingerprint=adapter.fingerprint_state({"version": 1}))

    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter)

    by_decision_id = find_bind_receipts(decision_id=intent.decision_id)
    by_execution_intent_id = find_bind_receipts(execution_intent_id=intent.execution_intent_id)
    by_bind_receipt_id = find_bind_receipts(bind_receipt_id=receipt.bind_receipt_id)

    assert len(by_decision_id) == 1
    assert len(by_execution_intent_id) == 1
    assert len(by_bind_receipt_id) == 1
    assert by_decision_id[0].bind_receipt_id == receipt.bind_receipt_id
    assert by_execution_intent_id[0].bind_receipt_id == receipt.bind_receipt_id


def test_bind_execution_policy_requires_drift_missing_signal_blocks() -> None:
    adapter = ReferenceBindAdapter(state={"version": 1}, pending_changes={"version": 2})
    intent = _intent(
        expected_fingerprint="",
        policy_lineage={"bind_adjudication": {"drift_required": True}},
    )

    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter)

    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert "BIND_DRIFT_SIGNAL_MISSING" in receipt.admissibility_result["reason_codes"]


def test_bind_execution_policy_relaxes_drift_allows_commit_without_fingerprint() -> None:
    adapter = ReferenceBindAdapter(state={"version": 1}, pending_changes={"version": 2})
    intent = _intent(
        expected_fingerprint="",
        policy_lineage={"bind_adjudication": {"drift_required": False}},
    )

    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter)

    assert receipt.final_outcome is FinalOutcome.COMMITTED
    assert adapter.state["version"] == 2


def test_bind_execution_policy_requires_approval_freshness_stale_escalates() -> None:
    adapter = ReferenceBindAdapter(state={"version": 1}, pending_changes={"version": 2})
    intent = _intent(
        expected_fingerprint=adapter.fingerprint_state({"version": 1}),
        approval_context={"approval_expires_at": "2026-04-20T12:00:00Z"},
        policy_lineage={
            "bind_adjudication": {
                "approval_freshness_required": True,
                "missing_signal_default": "escalate",
            }
        },
    )

    receipt = execute_bind_boundary(
        execution_intent=intent,
        adapter=adapter,
        bind_ts="2026-04-20T12:05:00Z",
    )

    assert receipt.final_outcome is FinalOutcome.ESCALATED


def test_bind_execution_precondition_failed_when_intent_missing_target() -> None:
    adapter = ReferenceBindAdapter(state={"version": 1}, pending_changes={"version": 2})
    intent = _intent(expected_fingerprint=adapter.fingerprint_state({"version": 1}))
    intent = ExecutionIntent(**{**intent.to_dict(), "target_resource": ""})

    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter, append_trustlog=False)

    assert receipt.final_outcome is FinalOutcome.PRECONDITION_FAILED
    assert receipt.admissibility_result["reason_codes"] == ["BIND_PRECONDITION_INVALID"]


def test_bind_execution_policy_controls_missing_signal_default_block_vs_escalate() -> None:
    block_adapter = ReferenceBindAdapter(
        state={"version": 1},
        pending_changes={"version": 2},
        runtime_risk_signal=None,
    )
    escalate_adapter = ReferenceBindAdapter(
        state={"version": 1},
        pending_changes={"version": 2},
        runtime_risk_signal=None,
    )
    block_intent = _intent(
        expected_fingerprint=block_adapter.fingerprint_state({"version": 1}),
        policy_lineage={"bind_adjudication": {"missing_signal_default": "block"}},
    )
    escalate_intent = _intent(
        expected_fingerprint=escalate_adapter.fingerprint_state({"version": 1}),
        policy_lineage={"bind_adjudication": {"missing_signal_default": "escalate"}},
    )

    block_receipt = execute_bind_boundary(execution_intent=block_intent, adapter=block_adapter)
    escalate_receipt = execute_bind_boundary(
        execution_intent=escalate_intent,
        adapter=escalate_adapter,
    )

    assert block_receipt.final_outcome is FinalOutcome.BLOCKED
    assert escalate_receipt.final_outcome is FinalOutcome.ESCALATED
