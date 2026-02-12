# -*- coding: utf-8 -*-
"""Tests to boost coverage for veritas_os/core/self_healing.py."""
from __future__ import annotations

import os
import time
from unittest import mock

from veritas_os.core import self_healing
from veritas_os.core.fuji_codes import FujiAction
from veritas_os.core.self_healing import (
    HealingBudget,
    HealingState,
    advance_state,
    budget_remaining,
    build_healing_input,
    check_guardrails,
    decide_healing_action,
    diff_summary,
    is_healing_enabled,
)


# ── is_healing_enabled env-var branches ───────────────────────────────

def test_is_healing_enabled_context_disabled() -> None:
    assert is_healing_enabled({"self_healing_enabled": False}) is False


def test_is_healing_enabled_env_false() -> None:
    with mock.patch.dict(os.environ, {"VERITAS_SELF_HEALING_ENABLED": "false"}):
        assert is_healing_enabled({}) is False


def test_is_healing_enabled_env_zero() -> None:
    with mock.patch.dict(os.environ, {"VERITAS_SELF_HEALING_ENABLED": "0"}):
        assert is_healing_enabled({}) is False


def test_is_healing_enabled_env_off() -> None:
    with mock.patch.dict(os.environ, {"VERITAS_SELF_HEALING_ENABLED": "off"}):
        assert is_healing_enabled({}) is False


def test_is_healing_enabled_env_no() -> None:
    with mock.patch.dict(os.environ, {"VERITAS_SELF_HEALING_ENABLED": "no"}):
        assert is_healing_enabled({}) is False


def test_is_healing_enabled_default_true() -> None:
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("VERITAS_SELF_HEALING_ENABLED", None)
        assert is_healing_enabled({}) is True


# ── diff_summary ──────────────────────────────────────────────────────

def test_diff_summary_no_change() -> None:
    inp = {
        "original_task": "t",
        "last_output": {"a": 1},
        "rejection": {},
        "policy_decision": "ok",
    }
    assert diff_summary(inp, dict(inp)) == "no_meaningful_change"


# ── check_guardrails budget branches ─────────────────────────────────

def test_check_guardrails_budget_steps_exceeded() -> None:
    state = HealingState(attempt=0, steps_used=6)
    budget = HealingBudget(max_attempts=10, max_steps=6, max_seconds=60)
    result = check_guardrails(
        state=state, budget=budget,
        error_code="F-1002", input_signature="sig",
    )
    assert result == "budget_steps_exceeded"


def test_check_guardrails_budget_time_exceeded() -> None:
    state = HealingState(
        attempt=0, steps_used=0,
        start_time=time.monotonic() - 100,
    )
    budget = HealingBudget(max_attempts=10, max_steps=10, max_seconds=5)
    result = check_guardrails(
        state=state, budget=budget,
        error_code="F-1002", input_signature="sig",
    )
    assert result == "budget_time_exceeded"


# ── build_healing_input with non-dict rejection ──────────────────────

def test_build_healing_input_non_dict_rejection() -> None:
    result = build_healing_input(
        original_task="task",
        last_output={},
        rejection="not a dict",  # type: ignore[arg-type]
        attempt=1,
        policy_decision="retry",
    )
    assert result["rejection"]["status"] is None
    assert result["rejection"]["gate"] is None


# ── decide_healing_action branches ────────────────────────────────────

def test_decide_healing_action_f3008() -> None:
    d = decide_healing_action("F-3008")
    assert d.allow is False
    assert d.action == FujiAction.HUMAN_REVIEW
    assert d.stop_reason == "ethical_boundary"


def test_decide_healing_action_f3001() -> None:
    d = decide_healing_action("F-3001")
    assert d.allow is False
    assert d.stop_reason == "value_core_mismatch"


def test_decide_healing_action_unknown_code() -> None:
    d = decide_healing_action("F-9999")
    assert d.allow is False
    assert d.stop_reason == "unknown_code"


def test_decide_healing_action_feedback_human_review() -> None:
    d = decide_healing_action("F-9999", feedback_action="HUMAN_REVIEW")
    assert d.allow is False
    assert d.stop_reason == "feedback_human_review"


# ── budget_remaining ──────────────────────────────────────────────────

def test_budget_remaining_snapshot() -> None:
    state = HealingState(attempt=1, steps_used=2, start_time=time.monotonic() - 5)
    budget = HealingBudget(max_attempts=3, max_steps=6, max_seconds=20)
    snap = budget_remaining(state, budget)
    assert snap["attempts_remaining"] == 2
    assert snap["steps_remaining"] == 4
    assert snap["seconds_remaining"] > 0


# ── advance_state ─────────────────────────────────────────────────────

def test_advance_state_different_error_resets_count() -> None:
    state = HealingState(
        attempt=1, steps_used=1,
        last_error_code="F-1002", same_error_count=1,
    )
    advance_state(state=state, error_code="F-2101", input_signature="sig-2")
    assert state.attempt == 2
    assert state.same_error_count == 1
    assert state.last_error_code == "F-2101"


# ── _safe_int / _safe_float env parsing with invalid values ───────────

def test_safe_int_invalid_value() -> None:
    with mock.patch.dict(os.environ, {"VERITAS_TEST_INT": "notanint"}):
        result = self_healing._safe_int("VERITAS_TEST_INT", 42)
        assert result == 42


def test_safe_float_invalid_value() -> None:
    with mock.patch.dict(os.environ, {"VERITAS_TEST_FLOAT": "notafloat"}):
        result = self_healing._safe_float("VERITAS_TEST_FLOAT", 3.14)
        assert result == 3.14
