# veritas_os/core/self_healing.py
# -*- coding: utf-8 -*-
"""
Self-Healing loop utilities for VERITAS OS.

This module defines the policy, guardrails, and helper utilities for
re-running a rejected task using FUJI feedback in a safe, auditable way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import time
from typing import Any, Dict, Optional

from .fuji_codes import FujiAction

def _safe_int(env_key: str, default: int) -> int:
    val = os.getenv(env_key)
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _safe_float(env_key: str, default: float) -> float:
    val = os.getenv(env_key)
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


MAX_HEALING_ATTEMPTS = _safe_int("VERITAS_MAX_HEALING_ATTEMPTS", 3)
MAX_HEALING_STEPS = _safe_int("VERITAS_HEALING_MAX_STEPS", 6)
MAX_HEALING_SECONDS = _safe_float("VERITAS_HEALING_MAX_SECONDS", 20.0)
MAX_CONSECUTIVE_SAME_ERROR = _safe_int("VERITAS_HEALING_MAX_SAME_ERROR", 2)


@dataclass(frozen=True)
class HealingBudget:
    """Budget guardrails for self-healing attempts."""

    max_attempts: int = MAX_HEALING_ATTEMPTS
    max_steps: int = MAX_HEALING_STEPS
    max_seconds: float = MAX_HEALING_SECONDS


@dataclass
class HealingState:
    """Mutable state for self-healing attempts."""

    attempt: int = 0
    steps_used: int = 0
    start_time: float = field(default_factory=time.monotonic)
    last_error_code: Optional[str] = None
    same_error_count: int = 0
    last_input_signature: Optional[str] = None


@dataclass(frozen=True)
class HealingDecision:
    """Policy decision for self-healing action."""

    action: FujiAction
    allow: bool
    reason: str
    stop_reason: Optional[str] = None


def is_healing_enabled(context: Dict[str, Any]) -> bool:
    """Return whether self-healing is enabled for the current context."""
    if context.get("self_healing_enabled") is False:
        return False
    env_flag = os.getenv("VERITAS_SELF_HEALING_ENABLED", "1")
    return env_flag.strip().lower() not in ("0", "false", "no", "off")


def is_safety_code(error_code: str) -> bool:
    """Return True if the FUJI error code is safety/security related."""
    return str(error_code).startswith("F-4")


def _coerce_action(action_value: Any) -> Optional[FujiAction]:
    try:
        return FujiAction(str(action_value))
    except Exception:
        return None


def decide_healing_action(
    error_code: str,
    feedback_action: Optional[str] = None,
) -> HealingDecision:
    """
    Decide the healing action for a FUJI error code.

    Safety errors (F-4xxx) are not self-healed by default.
    """
    code = str(error_code or "")

    if is_safety_code(code) or code in {"F-4001", "F-4003"}:
        return HealingDecision(
            action=FujiAction.HUMAN_REVIEW,
            allow=False,
            reason="safety_or_security_code_requires_human_review",
            stop_reason="safety_code_blocked",
        )

    if code == "F-3008":
        return HealingDecision(
            action=FujiAction.HUMAN_REVIEW,
            allow=False,
            reason="ethical_boundary_requires_human_review",
            stop_reason="ethical_boundary",
        )

    if code == "F-3001":
        return HealingDecision(
            action=FujiAction.HUMAN_REVIEW,
            allow=False,
            reason="value_core_mismatch_requires_human_review",
            stop_reason="value_core_mismatch",
        )

    mapping = {
        "F-1002": FujiAction.REQUEST_EVIDENCE,
        "F-1005": FujiAction.RE_CRITIQUE,
        "F-2101": FujiAction.RE_DEBATE,
        "F-2203": FujiAction.RE_DEBATE,
    }
    action = mapping.get(code) or _coerce_action(feedback_action)
    if action is None:
        action = FujiAction.HUMAN_REVIEW
        return HealingDecision(
            action=action,
            allow=False,
            reason="unknown_code_requires_human_review",
            stop_reason="unknown_code",
        )

    if action == FujiAction.HUMAN_REVIEW:
        return HealingDecision(
            action=action,
            allow=False,
            reason="feedback_requires_human_review",
            stop_reason="feedback_human_review",
        )

    return HealingDecision(
        action=action,
        allow=True,
        reason=f"policy_map:{code}->{action.value}",
    )


def build_healing_input(
    *,
    original_task: str,
    last_output: Dict[str, Any],
    rejection: Dict[str, Any],
    attempt: int,
    policy_decision: str,
) -> Dict[str, Any]:
    """Build the standardized self-healing input payload."""
    feedback = rejection.get("feedback") if isinstance(rejection, dict) else {}
    error = rejection.get("error") if isinstance(rejection, dict) else {}
    return {
        "original_task": original_task,
        "last_output": last_output,
        "rejection": {
            "status": rejection.get("status"),
            "gate": rejection.get("gate"),
            "error": error,
            "feedback": feedback,
            "trust_log_id": rejection.get("trust_log_id"),
        },
        "attempt": int(attempt),
        "policy_decision": policy_decision,
    }


def healing_input_signature(healing_input: Dict[str, Any]) -> str:
    """
    Build a deterministic signature for diff detection.

    The attempt number is ignored to detect no-op retries.
    """
    payload = dict(healing_input)
    payload.pop("attempt", None)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def diff_summary(
    prev_input: Optional[Dict[str, Any]],
    next_input: Dict[str, Any],
) -> str:
    """Summarize changes between two healing inputs."""
    if not prev_input:
        return "initial_healing_input"

    changed_fields = []
    for key in ("original_task", "last_output", "rejection", "policy_decision"):
        if prev_input.get(key) != next_input.get(key):
            changed_fields.append(key)

    if not changed_fields:
        return "no_meaningful_change"

    return "changed_fields:" + ",".join(changed_fields)


def budget_remaining(state: HealingState, budget: HealingBudget) -> Dict[str, Any]:
    """Return remaining budget snapshot for logging."""
    elapsed = time.monotonic() - state.start_time
    return {
        "attempts_remaining": max(0, budget.max_attempts - state.attempt),
        "steps_remaining": max(0, budget.max_steps - state.steps_used),
        "seconds_remaining": max(0.0, budget.max_seconds - elapsed),
    }


def check_guardrails(
    *,
    state: HealingState,
    budget: HealingBudget,
    error_code: str,
    input_signature: str,
) -> Optional[str]:
    """Return a stop reason if any guardrail is violated."""
    attempt_no = state.attempt + 1
    elapsed = time.monotonic() - state.start_time

    if attempt_no > budget.max_attempts:
        return "max_attempts_exceeded"
    if state.steps_used >= budget.max_steps:
        return "budget_steps_exceeded"
    if elapsed >= budget.max_seconds:
        return "budget_time_exceeded"

    next_same_error = state.same_error_count
    if error_code and error_code == state.last_error_code:
        next_same_error += 1
    else:
        next_same_error = 1
    if next_same_error >= MAX_CONSECUTIVE_SAME_ERROR:
        return "same_error_consecutive_limit"

    if state.last_input_signature and input_signature == state.last_input_signature:
        return "no_meaningful_change"

    return None


def advance_state(
    *,
    state: HealingState,
    error_code: str,
    input_signature: str,
) -> None:
    """Update healing state after scheduling an attempt."""
    state.attempt += 1
    state.steps_used += 1
    if error_code and error_code == state.last_error_code:
        state.same_error_count += 1
    else:
        state.same_error_count = 1
    state.last_error_code = error_code
    state.last_input_signature = input_signature


def build_healing_trust_log_entry(
    *,
    request_id: str,
    healing_enabled: bool,
    attempt: int,
    prev_error_code: Optional[str],
    chosen_action: str,
    budget_snapshot: Dict[str, Any],
    diff_summary_text: str,
    linked_trust_log_id: Optional[str],
    stop_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a TrustLog entry for healing attempts."""
    entry: Dict[str, Any] = {
        "request_id": request_id,
        "kind": "self_healing",
        "healing_enabled": healing_enabled,
        "healing_attempt": int(attempt),
        "prev_error_code": prev_error_code,
        "chosen_action": chosen_action,
        "budget_remaining": budget_snapshot,
        "diff_summary": diff_summary_text,
        "linked_trust_log_id": linked_trust_log_id,
    }
    if stop_reason:
        entry["stop_reason"] = stop_reason
    return entry

