# veritas_os/core/pipeline_execute.py
# -*- coding: utf-8 -*-
"""
Pipeline core‑decision execution stage.

Handles:
- kernel.decide invocation via call_core_decide
- Self‑healing retry loop
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .pipeline_types import PipelineContext
from .pipeline_helpers import (
    _lazy_import,
    _extract_rejection,
    _summarize_last_output,
    _warn,
)

logger = logging.getLogger(__name__)


async def stage_core_execute(
    ctx: PipelineContext,
    *,
    call_core_decide_fn: Any,
    append_trust_log_fn: Any,
    veritas_core: Any = None,
) -> None:
    """Run kernel.decide and self‑healing loop, mutating *ctx* in place.

    Parameters
    ----------
    veritas_core:
        Pre-resolved kernel module. When ``None`` (default), the kernel
        is lazily imported here.  Passing the module explicitly allows the
        caller (pipeline.py) to provide a value that tests can
        monkeypatch on the *pipeline* module.
    """
    from . import self_healing

    if veritas_core is None:
        veritas_core = (
            _lazy_import("veritas_os.core.kernel", None)
            or _lazy_import("veritas_os.core", "kernel")
        )

    core_decide = None
    try:
        if veritas_core is not None and hasattr(veritas_core, "decide"):
            core_decide = veritas_core.decide  # type: ignore[attr-defined]
    except Exception:  # subsystem resilience: intentionally broad
        core_decide = None

    healing_enabled = self_healing.is_healing_enabled(ctx.context or {})
    healing_state = self_healing.HealingState()
    healing_budget = self_healing.HealingBudget()
    prev_healing_input: Optional[Dict[str, Any]] = None

    core_context: Dict[str, Any] = {}
    if core_decide is None:
        ctx.response_extras.setdefault("env_tools", {})
        if isinstance(ctx.response_extras["env_tools"], dict):
            ctx.response_extras["env_tools"]["kernel_missing"] = True
        _warn("[decide] kernel.decide missing -> skip core call")
    else:
        core_context = dict(ctx.context or {})
        core_context["_orchestrated_by_pipeline"] = True
        core_context["evidence"] = list(ctx.evidence)
        core_context["planner"] = dict(ctx.response_extras.get("planner") or {})
        core_context["env_tools"] = dict(ctx.response_extras.get("env_tools") or {})
        if isinstance(ctx.response_extras.get("world_simulation"), dict):
            core_context["world_simulation"] = dict(ctx.response_extras["world_simulation"])
        try:
            raw0 = await call_core_decide_fn(
                core_fn=core_decide,  # type: ignore[arg-type]
                context=core_context,
                query=ctx.query,
                alternatives=ctx.input_alts,
                min_evidence=ctx.min_ev,
            )
            ctx.raw = raw0 if isinstance(raw0, dict) else {}
        except Exception as e:  # subsystem resilience: intentionally broad
            _warn(f"[decide] core error: {e}")
            ctx.raw = {}

    # --- Self‑healing loop ---
    if ctx.raw and healing_enabled:
        original_task = ctx.query
        latest_healing_input: Optional[Dict[str, Any]] = None
        current_context = dict(ctx.context or {})

        while True:
            rejection = _extract_rejection(ctx.raw)
            if not rejection:
                break
            error_code = (rejection.get("error") or {}).get("code") or "unknown"
            feedback_action = (rejection.get("feedback") or {}).get("action")
            decision = self_healing.decide_healing_action(
                error_code=error_code,
                feedback_action=feedback_action,
            )

            attempt_no = healing_state.attempt + 1
            last_output = _summarize_last_output(ctx.raw, ctx.plan)
            healing_input = self_healing.build_healing_input(
                original_task=original_task,
                last_output=last_output,
                rejection=rejection,
                attempt=attempt_no,
                policy_decision=decision.reason,
            )
            input_signature = self_healing.healing_input_signature(healing_input)
            diff_text = self_healing.diff_summary(prev_healing_input, healing_input)

            stop_reason = self_healing.check_guardrails(
                state=healing_state,
                budget=healing_budget,
                error_code=str(error_code),
                input_signature=input_signature,
            )
            if not decision.allow:
                stop_reason = decision.stop_reason or "policy_blocked"

            budget_snapshot = self_healing.budget_remaining(
                healing_state,
                healing_budget,
            )
            trust_entry = self_healing.build_healing_trust_log_entry(
                request_id=ctx.request_id,
                healing_enabled=True,
                attempt=attempt_no,
                prev_error_code=str(error_code),
                chosen_action=decision.action.value,
                budget_snapshot=budget_snapshot,
                diff_summary_text=diff_text,
                linked_trust_log_id=rejection.get("trust_log_id"),
                stop_reason=stop_reason,
            )
            try:
                append_trust_log_fn(trust_entry)
            except (KeyError, TypeError, AttributeError) as e:
                _warn(f"[self_healing] trust_log skipped: {repr(e)}")

            ctx.healing_attempts.append(
                {
                    "attempt": attempt_no,
                    "action": decision.action.value,
                    "error_code": error_code,
                    "stop_reason": stop_reason,
                    "diff_summary": diff_text,
                }
            )
            prev_healing_input = healing_input
            latest_healing_input = healing_input

            if stop_reason:
                ctx.healing_stop_reason = stop_reason
                break

            self_healing.advance_state(
                state=healing_state,
                error_code=str(error_code),
                input_signature=input_signature,
            )

            current_context = dict(core_context)
            current_context["healing"] = {
                "attempt": attempt_no,
                "action": decision.action.value,
                "feedback": rejection.get("feedback"),
                "policy_decision": decision.reason,
                "input": healing_input,
            }
            try:
                raw0 = await call_core_decide_fn(
                    core_fn=core_decide,  # type: ignore[arg-type]
                    context=current_context,
                    query=ctx.query,
                    alternatives=ctx.input_alts,
                    min_evidence=ctx.min_ev,
                )
                ctx.raw = raw0 if isinstance(raw0, dict) else {}
            except Exception as e:  # subsystem resilience: intentionally broad
                _warn(f"[self_healing] retry failed: {repr(e)}")
                ctx.healing_stop_reason = "retry_execution_failed"
                break

        if ctx.healing_attempts:
            ctx.response_extras.setdefault("self_healing", {})
            if isinstance(ctx.response_extras["self_healing"], dict):
                ctx.response_extras["self_healing"].update(
                    {
                        "enabled": True,
                        "attempts": ctx.healing_attempts,
                        "stop_reason": ctx.healing_stop_reason,
                        "input": latest_healing_input,
                    }
                )
