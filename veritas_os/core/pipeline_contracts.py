# veritas_os/core/pipeline_contracts.py
# -*- coding: utf-8 -*-
"""
Pipeline コントラクト強制モジュール。

extras / metrics / memory_meta に関する不変条件（invariant）を維持する
ヘルパー群。run_decide_pipeline 内のネスト定義をモジュールレベルに昇格した。

保証する不変条件:
- extras.fast_mode (bool) は常に存在
- extras.metrics.{mem_hits, memory_evidence_count, web_hits, web_evidence_count, fast_mode} は常に存在
- extras.metrics.mem_evidence_count は後方互換のため常に存在
- extras.env_tools は常に dict
- extras.memory_meta は常に dict
- extras.memory_meta.context は常に dict かつ context.fast (bool) を持つ
"""
from __future__ import annotations

from typing import Any, Dict

from .pipeline_helpers import _set_bool_metric, _set_int_metric, _to_bool_local


# =========================================================
# フルコントラクト強制
# =========================================================

def _ensure_full_contract(
    extras: Dict[str, Any],
    *,
    fast_mode_default: bool,
    context_obj: Dict[str, Any],
    query_str: str = "",
) -> None:
    """
    extras の全不変条件を満たす（例外を出さない、副作用で extras を更新）。

    - extras.fast_mode always exists (bool)
    - extras.metrics.{mem_hits, memory_evidence_count, web_hits, web_evidence_count, fast_mode}
    - extras.metrics.stage_latency.{retrieval, web, llm, gate, persist} always exist (int)
    - backward compat: metrics.mem_evidence_count
    - extras.env_tools always dict
    - extras.memory_meta always dict
    - extras.memory_meta.context always dict and has context.fast (bool)
    - extras.memory_meta.query filled if possible
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
    extras["fast_mode"] = _to_bool_local(extras.get("fast_mode", fast_mode_default))
    _set_bool_metric(
        extras,
        "fast_mode",
        (extras.get("metrics", {}) or {}).get("fast_mode", extras["fast_mode"]),
        default=extras["fast_mode"],
    )

    # int metrics
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

    # stage_latency
    stage_latency = extras["metrics"].get("stage_latency")
    if not isinstance(stage_latency, dict):
        stage_latency = {}
    for stage_name in ("retrieval", "web", "llm", "gate", "persist"):
        try:
            stage_latency[stage_name] = max(0, int(stage_latency.get(stage_name, 0) or 0))
        except Exception:
            stage_latency[stage_name] = 0
    extras["metrics"]["stage_latency"] = stage_latency

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
    mm_ctx["fast"] = _to_bool_local(mm_ctx.get("fast", extras["fast_mode"]))

    # invariant: memory_meta.query
    try:
        existing_q = mm.get("query")
        if not (isinstance(existing_q, str) and existing_q.strip()):
            if isinstance(query_str, str) and query_str.strip():
                mm["query"] = query_str
    except Exception:
        pass


# =========================================================
# metrics コントラクト（最小版）
# =========================================================

def _ensure_metrics_contract(extras: Dict[str, Any]) -> None:
    """extras.metrics の最小不変条件を満たす（常に 5 キーを持つ）。"""
    extras.setdefault("metrics", {})
    m = extras["metrics"]
    m.setdefault("mem_hits", 0)
    m.setdefault("memory_evidence_count", 0)
    m.setdefault("web_hits", 0)
    m.setdefault("web_evidence_count", 0)
    m.setdefault("fast_mode", False)
    extras.setdefault("fast_mode", False)


# =========================================================
# extras の深いマージ
# =========================================================

def _deep_merge_dict(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    """dict を再帰的に安全マージする（例外を出さない）。"""
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
    extras を深いマージしつつコントラクトキーを失わない。

    - metrics はネストマージ（非 dict で置換されない）
    - memory_meta.context は保持され context.fast が注入される
    - 例外を出さない
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

        base_extras["fast_mode"] = _to_bool_local(base_extras.get("fast_mode", prev_fast))

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


__all__ = [
    "_ensure_full_contract",
    "_ensure_metrics_contract",
    "_deep_merge_dict",
    "_merge_extras_preserving_contract",
]
