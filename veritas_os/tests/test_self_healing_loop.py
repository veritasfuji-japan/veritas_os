# -*- coding: utf-8 -*-
from __future__ import annotations

from veritas_os.core import self_healing
from veritas_os.core.fuji_codes import FujiAction


def test_f2101_selects_redebate_and_attempt_increments() -> None:
    decision = self_healing.decide_healing_action("F-2101")
    assert decision.allow is True
    assert decision.action == FujiAction.RE_DEBATE

    state = self_healing.HealingState()
    signature = self_healing.healing_input_signature(
        {
            "original_task": "task",
            "last_output": {},
            "rejection": {},
            "attempt": 1,
            "policy_decision": decision.reason,
        }
    )
    self_healing.advance_state(
        state=state,
        error_code="F-2101",
        input_signature=signature,
    )
    assert state.attempt == 1


def test_same_error_consecutive_stops() -> None:
    state = self_healing.HealingState(
        attempt=1,
        steps_used=1,
        last_error_code="F-1002",
        same_error_count=1,
        last_input_signature="sig-1",
    )
    budget = self_healing.HealingBudget(max_attempts=5, max_steps=5, max_seconds=60)
    stop_reason = self_healing.check_guardrails(
        state=state,
        budget=budget,
        error_code="F-1002",
        input_signature="sig-2",
    )
    assert stop_reason == "same_error_consecutive_limit"


def test_max_attempts_exceeded_stops() -> None:
    state = self_healing.HealingState(attempt=2, steps_used=2)
    budget = self_healing.HealingBudget(max_attempts=2, max_steps=5, max_seconds=60)
    stop_reason = self_healing.check_guardrails(
        state=state,
        budget=budget,
        error_code="F-1002",
        input_signature="sig-1",
    )
    assert stop_reason == "max_attempts_exceeded"


def test_f4003_immediate_human_review() -> None:
    decision = self_healing.decide_healing_action("F-4003")
    assert decision.allow is False
    assert decision.action == FujiAction.HUMAN_REVIEW


def test_no_meaningful_change_stop() -> None:
    state = self_healing.HealingState(
        attempt=1,
        steps_used=1,
        last_input_signature="sig-1",
        last_error_code="F-1002",
        same_error_count=1,
    )
    budget = self_healing.HealingBudget(max_attempts=5, max_steps=5, max_seconds=60)
    stop_reason = self_healing.check_guardrails(
        state=state,
        budget=budget,
        error_code="F-1005",
        input_signature="sig-1",
    )
    assert stop_reason == "no_meaningful_change"


def test_trust_log_entry_contains_healing_metadata() -> None:
    entry = self_healing.build_healing_trust_log_entry(
        request_id="req-123",
        healing_enabled=True,
        attempt=1,
        prev_error_code="F-2101",
        chosen_action="RE-DEBATE",
        budget_snapshot={"attempts_remaining": 2},
        diff_summary_text="initial_healing_input",
        linked_trust_log_id="TL-1",
        stop_reason=None,
    )
    assert entry["healing_attempt"] == 1
    assert entry["prev_error_code"] == "F-2101"
    assert entry["chosen_action"] == "RE-DEBATE"

