"""Deterministic tests for native bind-boundary execution orchestration."""

from __future__ import annotations

from veritas_os.policy.bind_artifacts import ExecutionIntent, FinalOutcome
from veritas_os.policy.bind_execution import ReferenceBindAdapter, execute_bind_boundary


def _intent(expected_fingerprint: str = "") -> ExecutionIntent:
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
        expected_state_fingerprint=expected_fingerprint,
    )


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
    )
    receipt_b = execute_bind_boundary(
        execution_intent=intent,
        adapter=adapter_b,
        bind_ts="2026-04-20T12:00:10Z",
        bind_receipt_id="br-deterministic",
    )

    assert receipt_a.to_dict() == receipt_b.to_dict()
