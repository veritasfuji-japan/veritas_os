# veritas_os/core/pipeline_decide_stages.py
# -*- coding: utf-8 -*-
"""
Pipeline inline stages extracted from run_decide_pipeline.

Stages:
- Stage 3:   Options normalization
- Stage 4b:  Absorb raw core results
- Stage 4c:  Fallback alternatives
- Stage 4d:  WorldModel + MemoryModel boost
- Stage 5:   DebateOS
- Stage 5b:  Critique
- Stage 6b:  Value learning EMA update
- Stage 6c:  Metrics aggregation
- Stage 6d:  Low-evidence hardening
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from .pipeline_types import PipelineContext, DEFAULT_CONFIDENCE
from .pipeline_evidence import _norm_evidence_item, _dedupe_evidence

logger = logging.getLogger(__name__)


# =========================================================
# Stage 3: Options normalization
# =========================================================

def stage_normalize_options(
    ctx: PipelineContext,
    *,
    _norm_alt: Callable[[Any], Dict[str, Any]],
) -> None:
    """Stage 3: body から alternatives を正規化し ctx に設定する。"""
    explicit_raw = ctx.body.get("options") or ctx.body.get("alternatives") or []
    if not isinstance(explicit_raw, list):
        explicit_raw = []

    explicit_options: List[Dict[str, Any]] = [
        _norm_alt(a) for a in explicit_raw if isinstance(a, dict)
    ]
    explicit_options = [a for a in explicit_options if isinstance(a, dict)]

    input_alts: List[Dict[str, Any]] = list(explicit_options)

    if not input_alts and ctx.is_veritas_query:
        plan = ctx.plan
        step_alts: List[Dict[str, Any]] = []
        for i, st in enumerate((plan.get("steps") if isinstance(plan, dict) else []) or [], 1):
            if not isinstance(st, dict):
                continue
            title = st.get("title") or st.get("name") or f"Step {i}"
            detail = st.get("detail") or st.get("description") or st.get("why") or ""
            step_alts.append(
                _norm_alt(
                    {
                        "id": st.get("id") or f"plan_step_{i}",
                        "title": title,
                        "description": detail,
                        "score": 1.0,
                        "meta": {"source": "planner", "step_index": i},
                    }
                )
            )

        input_alts = step_alts or [
            _norm_alt({"id": "veritas_mvp_demo", "title": "MVPデモを最短で見せられる形にする", "description": "Swagger/CLIで /v1/decide の30〜60秒デモを作る。"}),
            _norm_alt({"id": "veritas_report", "title": "技術監査レポートを仕上げる", "description": "第三者が読めるレベルにブラッシュアップする。"}),
            _norm_alt({"id": "veritas_spec_sheet", "title": "MVP仕様書を1枚にまとめる", "description": "CLI/API・FUJI・Debate・Memoryの流れを1枚に整理する。"}),
            _norm_alt({"id": "veritas_demo_script", "title": "第三者向けデモ台本を作る", "description": "画面順・説明順・想定QAを台本化する。"}),
        ]

    ctx.explicit_options = explicit_options
    ctx.input_alts = input_alts
    ctx.alternatives = list(input_alts)

    if not isinstance(ctx.web_evidence, list):
        ctx.web_evidence = []


# =========================================================
# Stage 4b: Absorb raw core results
# =========================================================

def stage_absorb_raw_results(
    ctx: PipelineContext,
    *,
    _norm_alt: Callable[[Any], Dict[str, Any]],
    _normalize_critique_payload: Callable[..., Dict[str, Any]],
    _merge_extras_preserving_contract: Callable[..., Dict[str, Any]],
) -> None:
    """Stage 4b: kernel.decide の raw 結果を ctx に吸収する。"""
    raw = ctx.raw
    critique: Dict[str, Any] = {}
    debate: List[Any] = []
    telos: float = 0.0
    fuji_dict: Dict[str, Any] = {}

    if raw:
        if isinstance(raw.get("evidence"), list):
            for ev0 in raw["evidence"]:
                ev = _norm_evidence_item(ev0)
                if ev:
                    ctx.evidence.append(ev)

        if "critique" in raw:
            critique = _normalize_critique_payload(raw.get("critique"))

        debate = raw.get("debate") or debate

        try:
            telos = float(raw.get("telos_score") or telos)
        except (ValueError, TypeError):
            pass

        fuji_dict = raw.get("fuji") or fuji_dict

        alts_from_core = raw.get("alternatives") or raw.get("options") or []
        if (not ctx.explicit_options) and isinstance(alts_from_core, list) and alts_from_core:
            ctx.alternatives = [_norm_alt(a) for a in alts_from_core]

        if isinstance(raw.get("extras"), dict):
            ctx.response_extras = _merge_extras_preserving_contract(
                ctx.response_extras,
                raw["extras"],
                fast_mode_default=ctx.fast_mode,
                context_obj=ctx.context,
            )

    ctx.critique = critique
    ctx.debate = debate
    ctx.telos = telos
    ctx.fuji_dict = fuji_dict


# =========================================================
# Stage 4c: Fallback alternatives
# =========================================================

def stage_fallback_alternatives(
    ctx: PipelineContext,
    *,
    _norm_alt: Callable[[Any], Dict[str, Any]],
    _dedupe_alts: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]],
) -> None:
    """Stage 4c: alternatives が空の場合にフォールバックを提供し重複排除する。"""
    alts = ctx.alternatives or [
        _norm_alt({"title": "最小ステップで前進する"}),
        _norm_alt({"title": "情報収集を優先する"}),
        _norm_alt({"title": "今日は休息に充てる"}),
    ]
    ctx.alternatives = _dedupe_alts(alts)


# =========================================================
# Stage 4d: WorldModel + MemoryModel boost
# =========================================================

def stage_model_boost(
    ctx: PipelineContext,
    *,
    world_model: Any,
    MEM_VEC: Any,
    MEM_CLF: Any,
    _allow_prob: Callable[[str], float],
    _mem_model_path: Callable[[], str],
    _warn: Callable[[str], None],
) -> None:
    """Stage 4d: WorldModel シミュレーション + MemoryModel によるスコアブースト。"""
    alts = ctx.alternatives

    # WorldModel boost
    try:
        if world_model is not None and hasattr(world_model, "simulate"):
            boosted: List[Dict[str, Any]] = []
            uid_for_world = (ctx.context or {}).get("user_id") or ctx.user_id or "anon"
            uid_for_world = str(uid_for_world) if uid_for_world is not None else "anon"

            for d in alts:
                sim = world_model.simulate(user_id=uid_for_world, query=ctx.query, chosen=d)
                if isinstance(sim, dict):
                    d["world"] = sim
                    micro = max(
                        0.0,
                        min(
                            0.03,
                            0.02 * float(sim.get("utility", 0.0))
                            + 0.01 * float(sim.get("confidence", 0.5)),
                        ),
                    )
                    d["score"] = float(d.get("score", 1.0)) * (1.0 + micro)
                boosted.append(d)
            alts = boosted
    except Exception as e:  # subsystem resilience
        _warn(f"[WorldModelOS] skip: {e}")

    # MemoryModel boost
    try:
        ctx.response_extras.setdefault("metrics", {})
        if not isinstance(ctx.response_extras["metrics"], dict):
            ctx.response_extras["metrics"] = {}

        if MEM_VEC is not None and MEM_CLF is not None:
            ctx.response_extras["metrics"]["mem_model"] = {
                "applied": True,
                "reason": "loaded",
                "path": _mem_model_path(),
                "classes": (
                    getattr(MEM_CLF, "classes_", []).tolist()
                    if hasattr(MEM_CLF, "classes_")
                    else None
                ),
            }
            for d in alts:
                text = (d.get("title") or "") + " " + (d.get("description") or "")
                p_allow = _allow_prob(text)
                base = float(d.get("score", 1.0))
                d["score_raw"] = float(d.get("score_raw", base))
                d["score"] = base * (1.0 + 0.10 * p_allow)
        else:
            ctx.response_extras["metrics"]["mem_model"] = {
                "applied": False,
                "reason": "model_not_loaded",
                "path": _mem_model_path(),
            }
    except (ValueError, TypeError, AttributeError) as e:
        ctx.response_extras.setdefault("metrics", {})
        if not isinstance(ctx.response_extras["metrics"], dict):
            ctx.response_extras["metrics"] = {}
        ctx.response_extras["metrics"]["mem_model"] = {
            "applied": False,
            "error": str(e),
            "path": _mem_model_path(),
        }

    ctx.alternatives = alts

    # chosen (pre-debate)
    raw = ctx.raw
    chosen = raw.get("chosen") if isinstance(raw, dict) else {}
    if not isinstance(chosen, dict) or not chosen:
        try:
            chosen = max(
                alts,
                key=lambda d: float(
                    (d.get("world") or {}).get("utility", d.get("score", 1.0))
                ),
            )
        except (ValueError, TypeError):
            chosen = alts[0] if alts else {}
    ctx.chosen = chosen


# =========================================================
# Stage 5: DebateOS
# =========================================================

def stage_debate(
    ctx: PipelineContext,
    *,
    debate_core: Any,
    _warn: Callable[[str], None],
) -> None:
    """Stage 5: DebateOS を実行し結果を ctx に反映する。"""
    debate_result: Dict[str, Any] = {}
    try:
        if debate_core is not None and hasattr(debate_core, "run_debate") and not ctx.fast_mode:
            debate_result = debate_core.run_debate(
                query=ctx.query,
                options=ctx.alternatives,
                context={
                    "user_id": ctx.user_id,
                    "stakes": (ctx.context or {}).get("stakes"),
                    "telos_weights": (ctx.context or {}).get("telos_weights"),
                },
            ) or {}
    except (KeyError, TypeError, AttributeError) as e:
        _warn(f"[DebateOS] skipped: {e}")
        debate_result = {}

    if isinstance(debate_result, dict) and debate_result:
        deb_opts = debate_result.get("options") or []
        if isinstance(deb_opts, list) and deb_opts:
            ctx.alternatives = deb_opts
            ctx.debate = deb_opts
        deb_chosen = debate_result.get("chosen")
        if isinstance(deb_chosen, dict) and deb_chosen:
            ctx.chosen = deb_chosen
        ctx.response_extras.setdefault("debate", {})
        if isinstance(ctx.response_extras["debate"], dict):
            try:
                ctx.response_extras["debate"].update(
                    {"source": debate_result.get("source"), "raw": debate_result.get("raw")}
                )
            except (KeyError, TypeError, AttributeError):
                pass
        try:
            rejected_cnt = 0
            for o in deb_opts:
                if not isinstance(o, dict):
                    continue
                v = str(o.get("verdict") or "").strip()
                if v in ("却下", "reject", "Rejected", "NG"):
                    rejected_cnt += 1
            if rejected_cnt > 0 and deb_opts and isinstance(deb_opts[0], dict):
                deb_opts[0]["risk_delta"] = min(0.20, 0.05 * rejected_cnt)
        except (KeyError, TypeError, AttributeError) as e:
            _warn(f"[DebateOS] risk_delta heuristic skipped: {e}")


# =========================================================
# Stage 5b: Critique
# =========================================================

async def stage_critique_async(
    ctx: PipelineContext,
    *,
    _normalize_critique_payload: Callable[..., Dict[str, Any]],
    _run_critique_best_effort: Callable[..., Any],
    _ensure_critique_required: Callable[..., Dict[str, Any]],
    _critique_fallback: Callable[..., Dict[str, Any]],
) -> None:
    """Stage 5b: Critique を実行・正規化して ctx に反映する。"""
    try:
        critique = _normalize_critique_payload(ctx.critique)
        if not critique:
            critique = await _run_critique_best_effort(
                query=ctx.query,
                chosen=ctx.chosen,
                evidence=ctx.evidence if isinstance(ctx.evidence, list) else [],
                debate=ctx.debate,
                context=ctx.context,
                user_id=ctx.user_id,
            )
        critique = _ensure_critique_required(
            response_extras=ctx.response_extras,
            query=ctx.query,
            chosen=ctx.chosen,
            critique_obj=critique,
        )
    except Exception:  # subsystem resilience: intentionally broad
        critique = _critique_fallback(reason="critique_guard_exception", query=ctx.query, chosen=ctx.chosen)
        ctx.response_extras.setdefault("env_tools", {})
        if isinstance(ctx.response_extras["env_tools"], dict):
            ctx.response_extras["env_tools"]["critique_degraded"] = True

    try:
        if isinstance(critique, dict) and critique.get("ok") is False:
            ctx.response_extras.setdefault("env_tools", {})
            if isinstance(ctx.response_extras["env_tools"], dict):
                ctx.response_extras["env_tools"]["review_required"] = True
                ctx.response_extras["env_tools"]["review_reason"] = "critique_missing_or_failed"
    except (KeyError, TypeError, AttributeError):
        pass

    ctx.critique = critique


# =========================================================
# Stage 6b: Value learning EMA update
# =========================================================

def stage_value_learning_ema(
    ctx: PipelineContext,
    *,
    _load_valstats: Callable[[], Dict[str, Any]],
    _save_valstats: Callable[[Dict[str, Any]], None],
    _warn: Callable[[str], None],
    utc_now_iso_z: Callable[[], str],
) -> None:
    """Stage 6b: Value EMA を更新して永続化する。"""
    try:
        valstats = _load_valstats()
        alpha = float(valstats.get("alpha", 0.2))
        ema_prev = float(valstats.get("ema", 0.5))
        n_prev = int(valstats.get("n", 0))
        v_val = float(ctx.values_payload.get("total", 0.5))
        ema_new = (1.0 - alpha) * ema_prev + alpha * v_val
        hist = valstats.get("history", [])
        if not isinstance(hist, list):
            hist = []
        hist.append({"ts": utc_now_iso_z(), "ema": ema_new, "value": v_val})
        hist = hist[-1000:]
        valstats.update({"ema": ema_new, "n": n_prev + 1, "last": v_val, "history": hist})
        _save_valstats(valstats)
        ctx.values_payload["ema"] = round(ema_new, 4)
        ctx.value_ema = float(ema_new)
    except (ValueError, TypeError) as e:
        _warn(f"[value-learning] skip: {e}")


# =========================================================
# Stage 6c: Metrics aggregation
# =========================================================

def stage_compute_metrics(
    ctx: PipelineContext,
    *,
    _ensure_full_contract: Callable[..., None],
) -> None:
    """Stage 6c: 最終メトリクスを集約する。"""
    duration_ms = max(1, int((time.time() - ctx.started_at) * 1000))
    mem_evi_cnt = 0
    for ev in ctx.evidence:
        if isinstance(ev, dict) and str(ev.get("source", "")).startswith("memory"):
            mem_evi_cnt += 1

    ctx.response_extras.setdefault("metrics", {})
    if not isinstance(ctx.response_extras["metrics"], dict):
        ctx.response_extras["metrics"] = {}
    ctx.response_extras["metrics"].update(
        {
            "latency_ms": duration_ms,
            "mem_evidence_count": int(mem_evi_cnt),
            "memory_evidence_count": int(
                ctx.response_extras["metrics"].get("memory_evidence_count", 0) or 0
            ),
            "alts_count": int(len(ctx.alternatives)),
            "has_evidence": bool(ctx.evidence),
            "value_ema": round(float(ctx.value_ema), 4),
            "effective_risk": round(float(ctx.effective_risk), 4),
            "telos_threshold": round(float(ctx.telos_threshold), 3),
        }
    )
    _ensure_full_contract(
        ctx.response_extras,
        fast_mode_default=ctx.fast_mode,
        context_obj=ctx.context,
        query_str=ctx.query,
    )


# =========================================================
# Stage 6d: Low-evidence hardening
# =========================================================

def stage_evidence_hardening(
    ctx: PipelineContext,
    *,
    evidence_core: Any,
    _query_is_step1_hint: Callable[[str], bool],
    _has_step1_minimum_evidence: Callable[[List[Dict[str, Any]]], bool],
) -> None:
    """Stage 6d: 証拠不足のクエリに対してフォールバック証拠を追加し、最終正規化する。"""
    EVIDENCE_MAX = int(os.getenv("VERITAS_EVIDENCE_MAX", "50"))

    try:
        if not isinstance(ctx.evidence, list):
            ctx.evidence = list(ctx.evidence or [])
        step1_intent = False
        if not ctx.fast_mode:
            step1_intent = _query_is_step1_hint(ctx.query)
        if (
            step1_intent
            and (not _has_step1_minimum_evidence(ctx.evidence))
            and (evidence_core is not None)
        ):
            fn = getattr(evidence_core, "step1_minimum_evidence", None)
            if callable(fn):
                for ev0 in fn(ctx.context):
                    evn = _norm_evidence_item(ev0)
                    if evn:
                        ctx.evidence.append(evn)
    except (ValueError, TypeError):
        pass

    ctx.evidence = [
        ev for ev in (_norm_evidence_item(x) for x in ctx.evidence) if ev
    ]
    ctx.evidence = _dedupe_evidence(ctx.evidence)
    if len(ctx.evidence) > EVIDENCE_MAX:
        ctx.evidence = ctx.evidence[:EVIDENCE_MAX]


__all__ = [
    "stage_normalize_options",
    "stage_absorb_raw_results",
    "stage_fallback_alternatives",
    "stage_model_boost",
    "stage_debate",
    "stage_critique_async",
    "stage_value_learning_ema",
    "stage_compute_metrics",
    "stage_evidence_hardening",
]
