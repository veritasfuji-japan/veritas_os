# veritas_os/core/pipeline_contract.py
# -*- coding: utf-8 -*-
"""
VERITAS Pipeline — Contract enforcement helpers.

Ensures invariants like:
  - extras.fast_mode always exists
  - extras.metrics.{mem_hits, memory_evidence_count, ...} always exist
  - extras.memory_meta.context.fast always exists
  - backward compat keys preserved
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .pipeline_helpers import _to_bool, _as_str


# =========================================================
# Metric setters (type-safe)
# =========================================================

def _set_int_metric(
    extras: Dict[str, Any],
    key: str,
    value: Any,
    default: int = 0,
) -> None:
    extras.setdefault("metrics", {})
    if not isinstance(extras["metrics"], dict):
        extras["metrics"] = {}
    try:
        extras["metrics"][key] = int(value)
    except Exception:
        extras["metrics"][key] = int(default)


def _set_bool_metric(
    extras: Dict[str, Any],
    key: str,
    value: Any,
    default: bool = False,
) -> None:
    extras.setdefault("metrics", {})
    if not isinstance(extras["metrics"], dict):
        extras["metrics"] = {}
    try:
        extras["metrics"][key] = _to_bool(value)
    except Exception:
        extras["metrics"][key] = bool(default)


# =========================================================
# Full contract enforcement
# =========================================================

def _ensure_full_contract(
    extras: Dict[str, Any],
    *,
    fast_mode_default: bool,
    context_obj: Dict[str, Any],
    query_str: str = "",
) -> None:
    """
    Strong contract (safe, no free vars):
    - extras.fast_mode always exists (bool)
    - extras.metrics.{mem_hits, memory_evidence_count, web_hits, web_evidence_count, fast_mode} always exist
    - backward compat: metrics.mem_evidence_count
    - extras.env_tools always dict
    - extras.memory_meta always dict
    - extras.memory_meta.context always dict and has context.fast(bool)
    - extras.memory_meta.query filled if possible (query_str)
    """
    if not isinstance(extras, dict):
        return

    extras.setdefault("metrics", {})
    if not isinstance(extras["metrics"], dict):
        extras["metrics"] = {}

    extras.setdefault("env_tools", {})
    if not isinstance(extras["env_tools"], dict):
        extras["env_tools"] = {}

    extras.setdefault("memory_meta", {})
    if not isinstance(extras["memory_meta"], dict):
        extras["memory_meta"] = {}

    # fast_mode
    extras["fast_mode"] = _to_bool(extras.get("fast_mode", fast_mode_default))
    _set_bool_metric(
        extras,
        "fast_mode",
        (extras.get("metrics", {}) or {}).get("fast_mode", extras["fast_mode"]),
        default=extras["fast_mode"],
    )

    # ints
    _set_int_metric(extras, "mem_hits", extras["metrics"].get("mem_hits", 0), default=0)
    _set_int_metric(
        extras,
        "memory_evidence_count",
        extras["metrics"].get("memory_evidence_count", 0),
        default=0,
    )
    _set_int_metric(extras, "web_hits", extras["metrics"].get("web_hits", 0), default=0)
    _set_int_metric(
        extras,
        "web_evidence_count",
        extras["metrics"].get("web_evidence_count", 0),
        default=0,
    )

    # backward compat
    try:
        extras["metrics"].setdefault(
            "mem_evidence_count",
            int(extras["metrics"].get("mem_evidence_count", 0) or 0),
        )
    except Exception:
        extras["metrics"]["mem_evidence_count"] = 0

    # memory_meta.context merge
    mm = extras["memory_meta"]
    try:
        base_ctx = dict(context_obj) if isinstance(context_obj, dict) else {}
    except Exception:
        base_ctx = {}

    mm_ctx = mm.get("context")
    if not isinstance(mm_ctx, dict):
        mm_ctx = dict(base_ctx)
        mm["context"] = mm_ctx
    else:
        for k, v in base_ctx.items():
            mm_ctx.setdefault(k, v)

    # invariant: context.fast
    mm_ctx["fast"] = _to_bool(mm_ctx.get("fast", extras["fast_mode"]))

    # invariant: memory_meta.query
    try:
        existing_q = mm.get("query")
        if not (isinstance(existing_q, str) and existing_q.strip()):
            if isinstance(query_str, str) and query_str.strip():
                mm["query"] = query_str
    except Exception:
        pass


# =========================================================
# Extras deep-merge (contract preserving)
# =========================================================

def _deep_merge_dict(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    """Safe deep merge: dict-only. Never raises."""
    try:
        if not isinstance(dst, dict) or not isinstance(src, dict):
            return dst
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                _deep_merge_dict(dst[k], v)  # type: ignore[index]
            else:
                dst[k] = v
        return dst
    except Exception:
        return dst


def _merge_extras_preserving_contract(
    base_extras: Dict[str, Any],
    incoming_extras: Dict[str, Any],
    *,
    fast_mode_default: bool,
    context_obj: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Merge extras without losing contract keys.
    - metrics merged deeply (never replaced by non-dict)
    - memory_meta.context preserved and fast injected
    - never raises
    """
    try:
        if not isinstance(base_extras, dict):
            base_extras = {}
        if not isinstance(incoming_extras, dict):
            _ensure_full_contract(
                base_extras, fast_mode_default=fast_mode_default, context_obj=context_obj
            )
            return base_extras

        prev_metrics = base_extras.get("metrics")
        prev_mm = base_extras.get("memory_meta")
        prev_fast = base_extras.get("fast_mode", fast_mode_default)

        _deep_merge_dict(base_extras, incoming_extras)

        if not isinstance(base_extras.get("metrics"), dict):
            base_extras["metrics"] = prev_metrics if isinstance(prev_metrics, dict) else {}
        if not isinstance(base_extras.get("memory_meta"), dict):
            try:
                base_extras["memory_meta"] = (
                    prev_mm if isinstance(prev_mm, dict) else {"context": dict(context_obj)}
                )
            except Exception:
                base_extras["memory_meta"] = {"context": {}}

        base_extras["fast_mode"] = _to_bool(base_extras.get("fast_mode", prev_fast))

        _ensure_full_contract(
            base_extras, fast_mode_default=fast_mode_default, context_obj=context_obj
        )
        return base_extras
    except Exception:
        try:
            if isinstance(base_extras, dict):
                _ensure_full_contract(
                    base_extras, fast_mode_default=fast_mode_default, context_obj=context_obj
                )
                return base_extras
        except Exception:
            pass
        return base_extras if isinstance(base_extras, dict) else {}


# =========================================================
# Healing loop helpers
# =========================================================

def _extract_rejection(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    fuji_payload = payload.get("fuji") if isinstance(payload, dict) else None
    if not isinstance(fuji_payload, dict):
        return None
    rejection = fuji_payload.get("rejection")
    if not isinstance(rejection, dict):
        return None
    if rejection.get("status") != "REJECTED":
        return None
    return rejection


def _summarize_last_output(
    payload: Dict[str, Any],
    plan_payload: Dict[str, Any],
) -> Dict[str, Any]:
    chosen = payload.get("chosen") if isinstance(payload, dict) else None
    planner_obj = payload.get("planner") if isinstance(payload, dict) else None
    return {
        "chosen": chosen if isinstance(chosen, dict) else {},
        "plan": plan_payload if isinstance(plan_payload, dict) else {},
        "planner": planner_obj if isinstance(planner_obj, dict) else {},
    }
