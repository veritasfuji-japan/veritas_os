# veritas_os/core/kernel_post_choice.py
# -*- coding: utf-8 -*-
"""Post-choice enrichment: affect reflection, reason generation, self-refine.

Extracted from ``kernel.py`` to reduce the responsibility footprint of
``decide()``.  All functions are pure-ish helpers that populate the
``extras["affect"]`` sub-dict without side-effects beyond logging.

Backward compatibility:
- This module is an *internal* helper consumed only by ``kernel.decide()``.
- No public contract is exposed; callers should continue using ``decide()``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def enrich_affect(
    *,
    query: str,
    chosen: Dict[str, Any],
    fuji_result: Dict[str, Any],
    telos_score: float,
    affect_core: Any,
    extras: Dict[str, Any],
) -> None:
    """Run AffectOS / ReasonOS reflection and populate ``extras["affect"]``.

    Args:
        query: User query text.
        chosen: The selected alternative dict.
        fuji_result: FUJI gate evaluation result.
        telos_score: Computed telos score.
        affect_core: The ``affect`` module (injected to avoid import cycles).
        extras: Mutable dict that will receive ``affect.meta`` / errors.
    """
    try:
        affect_meta = affect_core.reflect({
            "query": query,
            "chosen": chosen,
            "gate": fuji_result,
            "values": {
                "total": float(telos_score),
                "ema": float(telos_score),
            },
        })
        extras.setdefault("affect", {})
        extras["affect"]["meta"] = affect_meta
    except (TypeError, ValueError, RuntimeError, AttributeError) as e:
        extras.setdefault("affect", {})
        extras["affect"]["meta_error"] = repr(e)


async def enrich_reason(
    *,
    query: str,
    telos_score: float,
    fuji_result: Dict[str, Any],
    reason_core: Any,
    user_id: str,
    mode: str,
    intent: str,
    planner: Optional[Dict[str, Any]],
    extras: Dict[str, Any],
) -> None:
    """Generate a natural-language reason and populate ``extras["affect"]``.

    Args:
        query: User query text.
        telos_score: Computed telos score.
        fuji_result: FUJI gate evaluation result.
        reason_core: The ``reason`` module (injected; may be ``None``).
        user_id: Current user id.
        mode: Decision mode string.
        intent: Detected intent.
        planner: Planner output dict (optional).
        extras: Mutable dict that will receive ``affect.natural`` / errors.
    """
    try:
        if reason_core is not None and hasattr(reason_core, "generate_reason"):
            gen_reason_fn = reason_core.generate_reason
            reason_args = {
                "query": query,
                "planner": planner,
                "values": {"total": float(telos_score)},
                "gate": fuji_result,
                "context": {
                    "user_id": user_id,
                    "mode": mode,
                    "intent": intent,
                },
            }
            if asyncio.iscoroutinefunction(gen_reason_fn):
                reason_natural = await gen_reason_fn(**reason_args)
            else:
                reason_natural = gen_reason_fn(**reason_args)

            extras.setdefault("affect", {})
            extras["affect"]["natural"] = reason_natural
        else:
            extras.setdefault("affect", {})
            extras["affect"]["natural_error"] = (
                "reason_core.generate_reason not available"
            )
    except (TypeError, ValueError, RuntimeError, AttributeError) as e:
        extras.setdefault("affect", {})
        extras["affect"]["natural_error"] = repr(e)


async def enrich_reflection(
    *,
    query: str,
    chosen: Dict[str, Any],
    fuji_result: Dict[str, Any],
    telos_score: float,
    reason_core: Any,
    planner: Optional[Dict[str, Any]],
    stakes: float,
    fast_mode: bool,
    extras: Dict[str, Any],
) -> None:
    """Generate a self-refine reflection template for high-risk decisions.

    Only runs when ``fast_mode`` is False and stakes >= 0.7 or risk >= 0.5.

    Args:
        query: User query text.
        chosen: The selected alternative dict.
        fuji_result: FUJI gate evaluation result.
        telos_score: Computed telos score.
        reason_core: The ``reason`` module (injected; may be ``None``).
        planner: Planner output dict (optional).
        stakes: Decision stakes value.
        fast_mode: Whether fast mode is active.
        extras: Mutable dict that will receive ``affect.reflection_template``.
    """
    try:
        risk_val = float(fuji_result.get("risk", 0.0))
        if fast_mode or (stakes < 0.7 and risk_val < 0.5):
            return

        if reason_core is not None and hasattr(
            reason_core, "generate_reflection_template"
        ):
            gen_refl_fn = reason_core.generate_reflection_template
            refl_args = {
                "query": query,
                "chosen": chosen,
                "gate": fuji_result,
                "values": {"total": float(telos_score)},
                "planner": planner or {},
            }
            if asyncio.iscoroutinefunction(gen_refl_fn):
                refl_tmpl = await gen_refl_fn(**refl_args)
            else:
                refl_tmpl = gen_refl_fn(**refl_args)

            if refl_tmpl:
                extras.setdefault("affect", {})
                extras["affect"]["reflection_template"] = refl_tmpl
    except (TypeError, ValueError, RuntimeError, AttributeError) as e:
        extras.setdefault("affect", {})
        extras["affect"]["reflection_template_error"] = repr(e)


__all__ = [
    "enrich_affect",
    "enrich_reason",
    "enrich_reflection",
]
