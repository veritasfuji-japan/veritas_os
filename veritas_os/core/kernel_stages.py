# veritas_os/core/kernel_stages.py
# -*- coding: utf-8 -*-
"""
kernel.decide() から責務を分離したステージモジュール

各ステージは独立してテスト可能で、設定値はconfig.pyから取得します。
"""
from __future__ import annotations

import uuid
import time
import math
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging

from .config import scoring_cfg, pipeline_cfg
from .types import OptionDict, EvidenceDict
from .utils import _safe_float

log = logging.getLogger(__name__)


# =============================================================================
# Stage 1: Context Preparation
# =============================================================================

def prepare_context(
    context: Dict[str, Any],
    query: str,
) -> Dict[str, Any]:
    """
    コンテキストを準備・正規化する

    Args:
        context: 入力コンテキスト
        query: クエリ文字列

    Returns:
        正規化されたコンテキスト
    """
    ctx = dict(context or {})
    ctx.setdefault("user_id", "cli")
    ctx.setdefault("request_id", uuid.uuid4().hex)
    ctx.setdefault("query", query)
    ctx.setdefault("stakes", 0.5)
    ctx.setdefault("mode", "")

    # Telos weights
    tw = ctx.get("telos_weights") or {}
    w_trans = _safe_float(tw.get("W_Transcendence", 0.6), 0.6)
    w_strug = _safe_float(tw.get("W_Struggle", 0.4), 0.4)
    ctx["_computed_telos_score"] = round(0.5 * w_trans + 0.5 * w_strug, 3)

    return ctx


# =============================================================================
# Stage 2: Memory & Evidence Collection
# =============================================================================

def collect_memory_evidence(
    user_id: str,
    query: str,
    context: Dict[str, Any],
    fast_mode: bool = False,
) -> Dict[str, Any]:
    """
    MemoryOS からエビデンスを収集する

    Args:
        user_id: ユーザーID
        query: 検索クエリ
        context: コンテキスト
        fast_mode: 高速モードフラグ

    Returns:
        {
            "evidence": List[Dict],
            "memory_summary": str,
            "evidence_count": int,
            "source": str,
        }
    """
    result: Dict[str, Any] = {
        "evidence": [],
        "memory_summary": "",
        "evidence_count": 0,
        "source": "none",
    }

    # Pipeline から提供されていればそれを使用
    pipeline_evidence = context.get("_pipeline_evidence")
    if pipeline_evidence and isinstance(pipeline_evidence, list):
        result["evidence"] = pipeline_evidence
        result["evidence_count"] = len(pipeline_evidence)
        result["source"] = "pipeline_provided"
        return result

    if fast_mode:
        result["source"] = "skipped_fast_mode"
        return result

    try:
        from . import memory as mem_core
        memory_summary = mem_core.summarize_for_planner(
            user_id=user_id,
            query=query,
            limit=pipeline_cfg.memory_search_limit,
        )
        result["memory_summary"] = memory_summary
        result["source"] = "MemoryOS.summarize_for_planner"
    except Exception as e:
        log.warning("Memory summarize failed: %s", e)
        result["source"] = f"error: {repr(e)[:80]}"

    return result


# =============================================================================
# Stage 3: World Model
# =============================================================================

def run_world_simulation(
    user_id: str,
    query: str,
    context: Dict[str, Any],
    fast_mode: bool = False,
) -> Dict[str, Any]:
    """
    WorldModel シミュレーションを実行

    Args:
        user_id: ユーザーID
        query: クエリ
        context: コンテキスト
        fast_mode: 高速モードフラグ

    Returns:
        {
            "simulation": Dict | None,
            "source": str,
        }
    """
    result: Dict[str, Any] = {
        "simulation": None,
        "source": "none",
    }

    if context.get("_world_sim_done"):
        result["simulation"] = context.get("_world_sim_result")
        result["source"] = "pipeline_provided"
        return result

    if fast_mode:
        result["source"] = "skipped_fast_mode"
        return result

    try:
        from . import world as world_model
        world_sim = world_model.simulate(
            user_id=user_id,
            query=query,
            chosen=None,
        )
        result["simulation"] = world_sim
        result["source"] = "world.simulate()"
    except Exception as e:
        log.warning("World simulation failed: %s", e)
        result["source"] = f"error: {repr(e)[:80]}"

    return result


# =============================================================================
# Stage 4: Environment Tools
# =============================================================================

def run_environment_tools(
    query: str,
    context: Dict[str, Any],
    fast_mode: bool = False,
) -> Dict[str, Any]:
    """
    環境ツール（Web検索、GitHub検索など）を実行

    Args:
        query: 検索クエリ
        context: コンテキスト
        fast_mode: 高速モードフラグ

    Returns:
        ツール実行結果の辞書
    """
    result: Dict[str, Any] = {}

    # Pipeline から提供されていればそれを使用
    pipeline_env = context.get("_pipeline_env_tools")
    if pipeline_env and isinstance(pipeline_env, dict):
        return pipeline_env

    if fast_mode:
        return {"skipped": {"reason": "fast_mode"}}

    try:
        from veritas_os.tools import call_tool
        ql = query.lower()

        if context.get("use_env_tools"):
            result["web_search"] = _run_tool_safe(
                call_tool, "web_search", query=query, max_results=3
            )
            result["github_search"] = _run_tool_safe(
                call_tool, "github_search", query=query, max_results=3
            )
        else:
            if "github" in ql:
                result["github_search"] = _run_tool_safe(
                    call_tool, "github_search", query=query, max_results=3
                )
            if any(k in ql for k in ["agi", "論文", "paper", "research"]):
                result["web_search"] = _run_tool_safe(
                    call_tool, "web_search", query=query, max_results=3
                )
    except Exception as e:
        result["error"] = f"run_env_tool failed: {repr(e)[:200]}"

    return result


def _run_tool_safe(call_tool_fn, kind: str, **kwargs) -> Dict[str, Any]:
    """ツールを安全に実行"""
    try:
        result = call_tool_fn(kind, **kwargs)
        if not isinstance(result, dict):
            result = {"raw": result}
        result.setdefault("ok", True)
        result.setdefault("results", [])
        return result
    except Exception as e:
        return {
            "ok": False,
            "results": [],
            "error": f"env_tool error: {repr(e)[:200]}",
        }


# =============================================================================
# Stage 5: Alternatives Scoring
# =============================================================================

def score_alternatives(
    intent: str,
    query: str,
    alternatives: List[Dict[str, Any]],
    telos_score: float,
    stakes: float,
    persona_bias: Dict[str, float] | None,
    context: Dict[str, Any] | None = None,
) -> None:
    """
    alternatives に対してスコアリングを行う

    設定値はすべて scoring_cfg から取得。

    Args:
        intent: 検出されたintent
        query: クエリ文字列
        alternatives: オプションリスト
        telos_score: Telosスコア
        stakes: ステークス値
        persona_bias: ペルソナバイアス辞書
        context: コンテキスト
    """
    ql = (query or "").lower()
    bias = persona_bias or {}
    _ctx = context or {}  # noqa: F841

    # value_core が利用可能かチェック
    try:
        from . import value_core
        vc_compute = getattr(value_core, "compute_value_score", None)
        OptionScore = getattr(value_core, "OptionScore", None)
        has_value_core = callable(vc_compute) and OptionScore is not None
    except Exception:
        has_value_core = False
        vc_compute = None
        OptionScore = None

    # adapt モジュール
    try:
        from . import adapt
    except Exception:
        adapt = None

    def _kw_hit(title: str, kws: List[str]) -> bool:
        t = (title or "").lower()
        return any(k in t for k in kws)

    if not alternatives:
        return

    for a in alternatives:
        base = _safe_float(a.get("score"), 1.0)
        title = a.get("title", "") or ""
        desc = a.get("description", "") or ""

        # ---- intent ヒューリスティック（設定値使用） ----
        if intent == "weather" and _kw_hit(title, ["予報", "降水", "傘", "天気"]):
            base += scoring_cfg.intent_weather_bonus
        elif intent == "health" and _kw_hit(title, ["休息", "回復", "散歩", "サウナ", "睡眠"]):
            base += scoring_cfg.intent_health_bonus
        elif intent == "learn" and _kw_hit(title, ["一次情報", "要約", "行動"]):
            base += scoring_cfg.intent_learn_bonus
        elif intent == "plan" and _kw_hit(title, ["最小", "情報収集", "休息", "リファクタ", "テスト"]):
            base += scoring_cfg.intent_plan_bonus

        # クエリ内容と候補タイトルの組み合わせによる微調整
        if any(k in ql for k in ["雨", "降水", "umbrella", "forecast"]) and "傘" in title:
            base += scoring_cfg.query_match_bonus

        # stakes が高い場合は「休息・情報収集寄り」をやや優遇
        if stakes >= scoring_cfg.high_stakes_threshold and _kw_hit(title, ["休息", "回復", "情報"]):
            base += scoring_cfg.high_stakes_bonus

        # ---- persona bias ----
        by_title = bias.get(title.lower(), 0.0)
        by_fuzzy = 0.0
        if adapt is not None and hasattr(adapt, "fuzzy_bias_lookup"):
            by_fuzzy = adapt.fuzzy_bias_lookup(bias, title)
        by_id = bias.get(f"@id:{a.get('id')}", 0.0)
        bias_boost = max(by_title, by_fuzzy, by_id)
        base *= (1.0 + scoring_cfg.persona_bias_multiplier * bias_boost)

        # ---- Telos スコアによる全体スケール ----
        base *= (scoring_cfg.telos_scale_base + scoring_cfg.telos_scale_factor * max(0.0, min(1.0, telos_score)))

        # ---- value_core があれば ValueScore を乗算 ----
        if has_value_core and vc_compute is not None and OptionScore is not None:
            try:
                persona_weight = float(bias_boost)
            except Exception:
                persona_weight = 0.0

            try:
                opt_score = OptionScore(
                    id=str(a.get("id") or ""),
                    title=title,
                    description=desc,
                    base_score=base,
                    telos_score=float(telos_score),
                    stakes=float(stakes),
                    persona_bias=persona_weight,
                    world_projection=a.get("world"),
                )
                vscore = float(vc_compute(opt_score))
                if math.isfinite(vscore):
                    base *= vscore
            except Exception:
                pass

        a["score_raw"] = _safe_float(a.get("score"), 1.0)
        a["score"] = round(base, 4)


# =============================================================================
# Stage 6: Debate
# =============================================================================

def run_debate_stage(
    query: str,
    alternatives: List[Dict[str, Any]],
    context: Dict[str, Any],
    fast_mode: bool = False,
) -> Dict[str, Any]:
    """
    DebateOS ステージを実行

    Args:
        query: クエリ文字列
        alternatives: オプションリスト
        context: コンテキスト
        fast_mode: 高速モードフラグ

    Returns:
        {
            "chosen": Dict | None,
            "debate_logs": List[Dict],
            "enriched_alternatives": List[Dict],
            "source": str,
        }
    """
    result: Dict[str, Any] = {
        "chosen": None,
        "debate_logs": [],
        "enriched_alternatives": alternatives,
        "source": "none",
    }

    if fast_mode:
        # 高速モード: 最高スコアを選択
        if alternatives:
            result["chosen"] = max(alternatives, key=lambda d: _safe_float(d.get("score"), 1.0))
        else:
            result["chosen"] = _mk_option("デフォルト選択")
        result["debate_logs"].append({
            "summary": "fast_mode のため DebateOS をスキップ",
            "risk_delta": 0.0,
            "suggested_choice_id": result["chosen"].get("id") if result["chosen"] else None,
            "source": "fast_mode_local",
        })
        result["source"] = "fast_mode"
        return result

    try:
        from . import debate as debate_core

        user_id = context.get("user_id", "cli")
        stakes = _safe_float(context.get("stakes", 0.5), 0.5)
        tw = context.get("telos_weights") or {}
        mode = context.get("mode", "")

        debate_result = debate_core.run_debate(
            query=query,
            options=alternatives,
            context={
                "user_id": user_id,
                "stakes": stakes,
                "telos_weights": tw,
                "mode": mode,
            },
        )

        result["chosen"] = debate_result.get("chosen")
        result["enriched_alternatives"] = debate_result.get("options") or alternatives
        result["source"] = debate_result.get("source", "openai_llm")

        result["debate_logs"].append({
            "summary": "Multi-Agent DebateOS により候補が評価されました。",
            "risk_delta": 0.0,
            "suggested_choice_id": result["chosen"].get("id") if isinstance(result["chosen"], dict) else None,
            "source": result["source"],
        })

    except Exception as e:
        log.warning("DebateOS failed: %s", e)
        if alternatives:
            result["chosen"] = max(alternatives, key=lambda d: _safe_float(d.get("score"), 1.0))
        else:
            result["chosen"] = _mk_option("フォールバック選択")
        result["debate_logs"].append({
            "summary": f"DebateOS フォールバック (例外: {repr(e)[:80]})",
            "risk_delta": 0.0,
            "suggested_choice_id": result["chosen"].get("id") if result["chosen"] else None,
            "source": "fallback",
        })
        result["source"] = "fallback"

    return result


# =============================================================================
# Stage 7: FUJI Gate
# =============================================================================

def run_fuji_gate(
    query: str,
    context: Dict[str, Any],
    evidence: List[Dict[str, Any]],
    alternatives: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    FUJI Gate 評価を実行

    Args:
        query: クエリ文字列
        context: コンテキスト
        evidence: エビデンスリスト
        alternatives: オプションリスト

    Returns:
        FUJI Gate の評価結果
    """
    try:
        from . import fuji as fuji_core

        user_id = context.get("user_id", "cli")
        stakes = _safe_float(context.get("stakes", 0.5), 0.5)
        mode = context.get("mode", "")
        telos_score = context.get("_computed_telos_score", 0.5)

        fuji_result = fuji_core.evaluate(
            query,
            context={
                "user_id": user_id,
                "stakes": stakes,
                "mode": mode,
                "telos_score": telos_score,
                "fuji_safe_applied": context.get("fuji_safe_applied", False),
            },
            evidence=evidence,
            alternatives=alternatives,
        )
        return fuji_result

    except Exception as e:
        log.error("FUJI Gate failed: %s", e)
        return {
            "status": "allow",
            "decision_status": "allow",
            "rejection_reason": None,
            "reasons": [f"fuji_error:{repr(e)[:80]}"],
            "violations": [],
            "risk": 0.05,
            "checks": [],
            "guidance": None,
            "modifications": [],
            "redactions": [],
            "safe_instructions": [],
        }


# =============================================================================
# Stage 8: Post-processing & Learning
# =============================================================================

def update_persona_and_goals(
    chosen: Dict[str, Any],
    context: Dict[str, Any],
    fuji_result: Dict[str, Any],
    telos_score: float,
    fast_mode: bool = False,
) -> Dict[str, Any]:
    """
    ペルソナとAGIゴールを更新

    Args:
        chosen: 選択されたオプション
        context: コンテキスト
        fuji_result: FUJI Gate の結果
        telos_score: Telosスコア
        fast_mode: 高速モードフラグ

    Returns:
        更新結果の辞書
    """
    result: Dict[str, Any] = {
        "updated": False,
        "error": None,
    }

    if fast_mode or context.get("_agi_goals_adjusted_by_pipeline"):
        result["skipped"] = True
        return result

    try:
        from . import adapt
        from . import agi_goals
        from . import world as world_model

        with adapt.PERSONA_UPDATE_LOCK:
            persona2 = adapt.update_persona_bias_from_history(window=pipeline_cfg.persona_update_window)

            b = dict(persona2.get("bias_weights") or {})
            key = (chosen.get("title") or "").strip().lower() or f"@id:{chosen.get('id')}"
            if key:
                b[key] = b.get(key, 0.0) + pipeline_cfg.persona_bias_increment

            s = sum(b.values()) or 1.0
            b = {kk: vv / s for kk, vv in b.items()}
            b = adapt.clean_bias_weights(b)

            world_snap: Dict[str, Any] = {}
            world_sim = context.get("_world_sim_result")
            if isinstance(world_sim, dict):
                world_snap = dict(world_sim)

            value_ema = float(telos_score)
            fuji_risk = float(fuji_result.get("risk", 0.05))

            new_bias = agi_goals.auto_adjust_goals(
                bias_weights=b,
                world_snap=world_snap,
                value_ema=value_ema,
                fuji_risk=fuji_risk,
            )

            persona2["bias_weights"] = new_bias
            adapt.save_persona(persona2)

        result["updated"] = True
        result["last_auto_adjust"] = {
            "value_ema": value_ema,
            "fuji_risk": fuji_risk,
        }

    except Exception as e:
        log.warning("Persona/AGI goals update failed: %s", e)
        result["error"] = repr(e)

    return result


def save_episode_to_memory(
    query: str,
    chosen: Dict[str, Any],
    context: Dict[str, Any],
    intent: str,
    mode: str,
    telos_score: float,
) -> bool:
    """
    エピソードをMemoryOSに保存

    Args:
        query: クエリ文字列
        chosen: 選択されたオプション
        context: コンテキスト
        intent: 検出されたintent
        mode: モード
        telos_score: Telosスコア

    Returns:
        保存成功したかどうか
    """
    if context.get("_episode_saved_by_pipeline"):
        return True

    try:
        from . import memory as mem_core

        user_id = context.get("user_id", "cli")
        req_id = context.get("request_id", uuid.uuid4().hex)

        episode_text = (
            f"[query] {query}\n"
            f"[chosen] {chosen.get('title')}\n"
            f"[mode] {mode}\n"
            f"[intent] {intent}\n"
            f"[telos_score] {telos_score}"
        )

        episode_record = {
            "text": episode_text,
            "tags": ["episode", "decide", "veritas"],
            "meta": {
                "user_id": user_id,
                "request_id": req_id,
                "mode": mode,
                "intent": intent,
            },
        }

        try:
            mem_core.MEM.put("episodic", episode_record)
        except TypeError:
            mem_core.MEM.put(
                user_id,
                f"decision:{req_id}",
                episode_record,
            )

        return True

    except Exception as e:
        log.warning("Episode save failed: %s", e)
        return False


# =============================================================================
# Utility functions
# =============================================================================

def _mk_option(title: str, description: str = "", _id: Optional[str] = None) -> Dict[str, Any]:
    """オプション辞書を生成する"""
    return {
        "id": _id or uuid.uuid4().hex,
        "title": title,
        "description": description,
        "score": 1.0,
    }


__all__ = [
    "prepare_context",
    "collect_memory_evidence",
    "run_world_simulation",
    "run_environment_tools",
    "score_alternatives",
    "run_debate_stage",
    "run_fuji_gate",
    "update_persona_and_goals",
    "save_episode_to_memory",
]
