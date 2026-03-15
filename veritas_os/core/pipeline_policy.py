# veritas_os/core/pipeline_policy.py
# -*- coding: utf-8 -*-
"""
Pipeline policy / gate application stage.

Handles:
- FUJI pre‑check
- ValueCore evaluation
- Gate decision (allow / modify / rejected)
- Value EMA learning
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

from .pipeline_types import (
    PipelineContext,
    HIGH_RISK_THRESHOLD,
    BASE_TELOS_THRESHOLD,
    TELOS_THRESHOLD_MIN,
    TELOS_THRESHOLD_MAX,
)
from .pipeline_helpers import _lazy_import, _apply_value_boost, _warn
from .pipeline_evidence import _norm_evidence_item

logger = logging.getLogger(__name__)


def _build_fail_closed_fuji_precheck(reason: str) -> dict[str, Any]:
    """Return a fail-closed FUJI payload used when safety evaluation fails."""
    return {
        "status": "rejected",
        "reasons": [reason],
        "violations": ["fuji_precheck_unavailable"],
        "risk": 1.0,
        "modifications": [],
    }


def stage_fuji_precheck(ctx: PipelineContext) -> None:
    """Run FUJI policy pre‑check and merge with existing fuji_dict."""
    fuji_core = (
        _lazy_import("veritas_os.core.fuji", None)
        or _lazy_import("veritas_os.core", "fuji")
    )

    fuji_pre = _build_fail_closed_fuji_precheck("fuji_precheck_missing")
    try:
        if fuji_core is not None and hasattr(fuji_core, "validate_action"):
            fuji_pre = fuji_core.validate_action(ctx.query, ctx.context)  # type: ignore
        elif fuji_core is not None and hasattr(fuji_core, "validate"):
            fuji_pre = fuji_core.validate(ctx.query, ctx.context)  # type: ignore
    except (RuntimeError, ValueError, TypeError, AttributeError) as e:
        _warn(f"[fuji] error (fail-closed): {e}")
        fuji_pre = _build_fail_closed_fuji_precheck("fuji_precheck_error")

    status_map = {
        "ok": "allow",
        "allow": "allow",
        "pass": "allow",
        "modify": "modify",
        "block": "rejected",
        "deny": "rejected",
        "rejected": "rejected",
    }
    try:
        if isinstance(fuji_pre, dict):
            fuji_pre["status"] = status_map.get(
                str(fuji_pre.get("status", "rejected")).lower(), "rejected"
            )
    except (KeyError, TypeError, AttributeError):
        if isinstance(fuji_pre, dict):
            fuji_pre["status"] = "rejected"

    ctx.fuji_dict = {
        **(ctx.fuji_dict if isinstance(ctx.fuji_dict, dict) else {}),
        **(fuji_pre if isinstance(fuji_pre, dict) else {}),
    }

    fuji_status = ctx.fuji_dict.get("status", "allow")
    try:
        import math as _math
        risk_val = float(ctx.fuji_dict.get("risk", 0.0))
        if not _math.isfinite(risk_val):
            risk_val = 1.0  # fail-closed: NaN/Inf は最大リスクとして扱う
        risk_val = max(0.0, min(1.0, risk_val))
    except (ValueError, TypeError):
        risk_val = 0.0
    reasons_list = ctx.fuji_dict.get("reasons", []) or []
    viols = ctx.fuji_dict.get("violations", []) or []

    ev_fuji = _norm_evidence_item(
        {
            "source": "internal:fuji",
            "uri": None,
            "snippet": (
                f"[FUJI pre] status={fuji_status}, risk={risk_val}, "
                f"reasons={'; '.join(reasons_list) if reasons_list else '-'}, "
                f"violations={', '.join(viols) if viols else '-'}"
            ),
            "confidence": 0.9 if fuji_status in ("modify", "rejected") else 0.8,
        }
    )
    if ev_fuji:
        ctx.evidence.append(ev_fuji)


def stage_value_core(
    ctx: PipelineContext,
    *,
    _load_valstats: Any,
    _clip01: Any,
) -> None:
    """Evaluate ValueCore and apply EMA‑based boosts."""
    value_core = (
        _lazy_import("veritas_os.core.value_core", None)
        or _lazy_import("veritas_os.core", "value_core")
    )

    try:
        if value_core is not None and hasattr(value_core, "evaluate"):
            vc = value_core.evaluate(ctx.query, ctx.context or {})  # type: ignore
            ctx.values_payload = {
                "scores": getattr(vc, "scores", {}) if vc is not None else {},
                "total": getattr(vc, "total", 0.0) if vc is not None else 0.0,
                "top_factors": getattr(vc, "top_factors", []) if vc is not None else [],
                "rationale": getattr(vc, "rationale", "") if vc is not None else "",
            }
        else:
            ctx.values_payload = {
                "scores": {},
                "total": 0.0,
                "top_factors": [],
                "rationale": "value_core missing",
            }
    except (RuntimeError, ValueError, TypeError, AttributeError) as e:
        _warn(f"[value_core] evaluation error: {e}")
        ctx.values_payload = {
            "scores": {},
            "total": 0.0,
            "top_factors": [],
            "rationale": "evaluation failed",
        }

    # EMA
    try:
        vs = _load_valstats()
        ctx.value_ema = float(vs.get("ema", 0.5))
    except (ValueError, TypeError):
        ctx.value_ema = 0.5

    BOOST_MAX = float(os.getenv("VERITAS_VALUE_BOOST_MAX", "0.05"))
    boost = (ctx.value_ema - 0.5) * 2.0
    boost = max(-1.0, min(1.0, boost)) * BOOST_MAX

    ctx.input_alts = _apply_value_boost(ctx.input_alts, boost)
    ctx.alternatives = _apply_value_boost(ctx.alternatives, boost)

    RISK_EMA_WEIGHT = float(os.getenv("VERITAS_RISK_EMA_WEIGHT", "0.15"))
    try:
        ctx.effective_risk = float(ctx.fuji_dict.get("risk", 0.0)) * (
            1.0 - RISK_EMA_WEIGHT * ctx.value_ema
        )
    except (ValueError, TypeError):
        ctx.effective_risk = 0.0
    ctx.effective_risk = max(0.0, min(1.0, ctx.effective_risk))

    TELOS_EMA_DELTA = float(os.getenv("VERITAS_TELOS_EMA_DELTA", "0.10"))
    ctx.telos_threshold = BASE_TELOS_THRESHOLD - TELOS_EMA_DELTA * (ctx.value_ema - 0.5) * 2.0
    ctx.telos_threshold = max(TELOS_THRESHOLD_MIN, min(TELOS_THRESHOLD_MAX, ctx.telos_threshold))

    # world.utility synthesis
    try:
        v_total = _clip01(ctx.values_payload.get("total", 0.5))
        t_val = _clip01(ctx.telos)
        r_val = _clip01(ctx.effective_risk)

        for d in ctx.alternatives:
            if not isinstance(d, dict):
                continue
            base = _clip01(d.get("score", 0.0))
            util = base
            util *= 0.5 + 0.5 * v_total
            util *= 1.0 - r_val
            util *= 0.5 + 0.5 * t_val
            util = _clip01(util)
            d.setdefault("world", {})
            if isinstance(d["world"], dict):
                d["world"]["utility"] = util

        avg_u = (
            (sum(float((d.get("world") or {}).get("utility", 0.0)) for d in ctx.alternatives) / len(ctx.alternatives))
            if ctx.alternatives
            else 0.0
        )
        ctx.response_extras.setdefault("metrics", {})
        if not isinstance(ctx.response_extras["metrics"], dict):
            ctx.response_extras["metrics"] = {}
        ctx.response_extras["metrics"]["avg_world_utility"] = round(float(avg_u), 4)
    except (ValueError, TypeError) as e:
        _warn(f"[world.utility] skipped: {e}")


def stage_gate_decision(ctx: PipelineContext) -> None:
    """Apply gate decision based on FUJI status and risk/telos thresholds."""
    gate_stage_started_at = time.time()
    ctx.decision_status, ctx.rejection_reason = "allow", None
    ctx.modifications = ctx.fuji_dict.get("modifications") or []

    RISK_EMA_WEIGHT = float(os.getenv("VERITAS_RISK_EMA_WEIGHT", "0.15"))

    # merge Debate risk_delta
    try:
        if isinstance(ctx.debate, list) and ctx.debate:
            delta = float((ctx.debate[0] or {}).get("risk_delta", 0.0))
            if delta:
                new_risk = max(0.0, min(1.0, float(ctx.fuji_dict.get("risk", 0.0)) + delta))
                ctx.fuji_dict["risk"] = new_risk
                ctx.effective_risk = max(
                    0.0, min(1.0, new_risk * (1.0 - RISK_EMA_WEIGHT * ctx.value_ema))
                )
    except (ValueError, TypeError) as e:
        _warn(f"[Debate→FUJI] merge failed: {e}")

    if ctx.fuji_dict.get("status") == "modify":
        ctx.modifications = ctx.fuji_dict.get("modifications") or []
    elif ctx.fuji_dict.get("status") == "rejected":
        ctx.decision_status = "rejected"
        ctx.rejection_reason = (
            "FUJI gate: "
            + ", ".join(ctx.fuji_dict.get("reasons", []) or ["policy_violation"])
        )
        ctx.chosen, ctx.alternatives = {}, []
    elif ctx.effective_risk >= HIGH_RISK_THRESHOLD and float(ctx.telos) < float(ctx.telos_threshold):
        ctx.decision_status = "rejected"
        ctx.rejection_reason = (
            f"FUJI gate: high risk ({ctx.effective_risk:.2f}) "
            f"& low telos (<{ctx.telos_threshold:.2f})"
        )
        ctx.chosen, ctx.alternatives = {}, []

    ctx.response_extras["metrics"]["stage_latency"]["gate"] = max(
        0,
        int((time.time() - gate_stage_started_at) * 1000),
    )
