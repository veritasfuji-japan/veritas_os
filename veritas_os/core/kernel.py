
# veritas_os/core/kernel.py (v2-compatible)
# -*- coding: utf-8 -*-
"""Core decision logic for VERITAS Kernel.

Public contract:
- ``decide()`` remains the backward-compatible kernel entry-point consumed by
  pipeline orchestration and tests.
- The module is responsible for decision computation only: alternative
  scoring, debate, FUJI gating, and rationale generation.

Preferred extension points:
- ``kernel_stages.py`` for staged kernel flow changes
- ``kernel_qa.py`` for QA / validation-specific helpers
- ``kernel_post_choice.py`` for post-choice affect/reason/reflection enrichment
- ``kernel_episode.py`` for episode logging side-effects
- ``kernel_doctor.py`` for auto-doctor security utilities
- ``pipeline_contracts.py`` for cross-module payload normalization contracts

Compatibility guidance:
- Backward-compatible wrappers live here so older call sites continue to work,
  but new branching, fallback shaping, and adapter logic should be added to
  helper modules first. Pipeline orchestration, side effects, and persistence
  stay in ``core/pipeline.py``.
"""
from __future__ import annotations

import logging
import re
import subprocess as _subprocess
import time
import uuid
from typing import Any, Dict, List, Optional, Protocol, Union

logger = logging.getLogger(__name__)
subprocess = _subprocess


class ReasonCapability(Protocol):
    """Kernel-facing contract for Reason capability."""

    def generate_reason(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def generate_reflection_template(self, *args: Any, **kwargs: Any) -> Any:
        ...


class StrategyCapability(Protocol):
    """Kernel-facing contract for Strategy capability."""

    def score_options(self, *args: Any, **kwargs: Any) -> Any:
        ...

# ============================================================
# Doctor / security utilities — implementation in kernel_doctor.py.
# Re-exported here so existing callers and test monkeypatches that
# target ``kernel.<name>`` keep working.
# ============================================================
from .kernel_doctor import (  # noqa: E402
    _is_safe_python_executable,
    _open_doctor_log_fd,
    _read_proc_self_status_seccomp,
    _read_apparmor_profile,
)


def _is_doctor_confinement_profile_active() -> bool:
    """Return whether process confinement is active for safe auto-doctor."""
    seccomp_mode = _read_proc_self_status_seccomp()
    if seccomp_mode is not None and seccomp_mode > 0:
        return True

    apparmor_profile = _read_apparmor_profile()
    if not apparmor_profile:
        return False

    normalized = apparmor_profile.lower()
    return normalized not in {"unconfined", "docker-default (enforce)"}

from .types import (
    ToolResult,
    OptionDict,
    EvidenceDict,
    FujiDecisionDict,
    DecideResult,
    ChosenDict,
    DebateViewpoint,
    CritiquePoint,
)
from .utils import _safe_float, _to_text, _redact_text, redact_payload

import asyncio

from . import adapt
from . import evidence as evos
from . import world as world_model
from . import planner as planner_core
from . import agi_goals
from . import memory as mem_core
from . import fuji as fuji_core
from . import debate as debate_core
from . import value_core
from . import affect as affect_core  # ★ NEW: ReasonOS / AffectOS
from . import reason as _reason_core
from . import strategy as _strategy_core
from .config import capability_cfg, emit_capability_manifest
from .sanitize import mask_pii as _mask_pii

# ★ QA処理を分離モジュールからインポート
from .kernel_qa import (
    detect_simple_qa as _detect_simple_qa,
    handle_simple_qa as _handle_simple_qa,
    detect_knowledge_qa as _detect_knowledge_qa,
    handle_knowledge_qa as _handle_knowledge_qa,
    SIMPLE_QA_PATTERNS,
    AGI_BLOCK_KEYWORDS,
)

reason_core: ReasonCapability | None = (
    _reason_core if capability_cfg.enable_kernel_reason else None
)
strategy_core: StrategyCapability | None = (
    _strategy_core if capability_cfg.enable_kernel_strategy else None
)
_HAS_SANITIZE = bool(capability_cfg.enable_kernel_sanitize)

if capability_cfg.emit_manifest_on_import:
    emit_capability_manifest(
        component="kernel",
        manifest={
            "reason": reason_core is not None,
            "strategy": strategy_core is not None,
            "sanitize": _HAS_SANITIZE,
        },
    )

from veritas_os.tools import call_tool


# ============================================================
# 環境ツールラッパ
# ============================================================

def run_env_tool(kind: str, **kwargs: Any) -> Dict[str, Any]:
    """環境ツールを実行し、結果を返す。

    Args:
        kind: ツールの種類 (例: "web_search", "memory_search")
        **kwargs: ツール固有のパラメータ

    Returns:
        Dict[str, Any]: ツール実行結果 (ToolResult互換)
            - ok: bool - 成功/失敗
            - results: List[Dict] - 結果リスト
            - error: Optional[str] - エラーメッセージ
            - その他ツール固有のフィールド
    """
    try:
        result = call_tool(kind, **kwargs)
        # 元の結果を保持しつつ、最低限のフィールドを保証
        if not isinstance(result, dict):
            result = {"raw": result}
        result.setdefault("ok", True)
        result.setdefault("results", [])
        return result
    except (TypeError, ValueError, RuntimeError, OSError) as e:
        error_message = f"env_tool error: {repr(e)[:200]}"
        return {
            "ok": False,
            "results": [],
            "error": error_message,
            "error_code": "ENV_TOOL_EXECUTION_ERROR",
            "tool_kind": str(kind),
        }


# ============================================================
# ユーティリティ
# ============================================================

def _tokens(s: str) -> List[str]:
    s = (s or "").replace("　", " ").lower()
    return [t for t in s.split() if t]


# _to_text は utils.py から統合インポート済み


def _mk_option(title: str, description: str = "", _id: Optional[str] = None) -> OptionDict:
    """オプション辞書を生成する。

    Args:
        title: オプションのタイトル
        description: オプションの説明
        _id: オプションID (省略時は自動生成)

    Returns:
        OptionDict: 生成されたオプション辞書
    """
    return OptionDict(
        id=_id or uuid.uuid4().hex,
        title=title,
        description=description,
        score=1.0,
    )


def _safe_load_persona() -> Dict[str, Any]:
    """
    persona.json 破損などで adapt.load_persona() が失敗しても
    kernel 全体を落とさないためのラッパ。
    """
    try:
        p = adapt.load_persona()
        if isinstance(p, dict):
            return p
        return {}
    except (AttributeError, TypeError, ValueError, RuntimeError):
        return {}


# _redact_text / redact_payload は utils.py に統合済み（import 済み）


# ============================================================
# Intent 検出（事前コンパイル済み正規表現）
# ============================================================

INTENT_PATTERNS = {
    "weather": re.compile(r"(天気|気温|降水|雨|晴れ|weather|forecast)", re.I),
    "health": re.compile(r"(疲れ|だる|体調|休む|回復|睡眠|寝|サウナ)", re.I),
    "learn": re.compile(r"(とは|仕組み|なぜ|how|why|教えて|違い|比較)", re.I),
    "plan": re.compile(r"(計画|進め|やるべき|todo|最小ステップ|スケジュール|plan)", re.I),
}

INTENT_OPTION_TEMPLATES = {
    "weather": [
        "天気アプリ/サイトで明日の予報を確認する",
        "降水確率が高い時間にリマインドを設定する",
        "傘・レインウェア・防水靴を準備する",
    ],
    "health": [
        "今日は休息し回復を最優先にする",
        "15分の軽い散歩で血流を上げる",
        "短時間サウナ＋十分な水分補給を行う",
    ],
    "learn": [
        "一次情報（公式/論文）を調べる",
        "要点を3行に要約する",
        "学んだことを1つだけ行動に落とす",
    ],
    "plan": [
        "最小ステップで前進する",
        "情報収集を優先する",
        "今日は休息し回復に充てる",
    ],
}


def _detect_intent(q: str) -> str:
    q = (q or "").strip().lower()
    for name, pattern in INTENT_PATTERNS.items():
        if pattern.search(q):
            return name
    return "plan"


def _gen_options_by_intent(intent: str) -> List[OptionDict]:
    templates = INTENT_OPTION_TEMPLATES.get(intent, INTENT_OPTION_TEMPLATES["plan"])
    return [_mk_option(title) for title in templates]


# ============================================================
# alternatives フィルタリング・重複排除・スコアリング
# ============================================================

def _filter_alts_by_intent(
    intent: str,
    q: str,
    alts: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not alts:
        return alts

    if intent == "weather":
        kws = ["天気", "気温", "降水", "雨", "晴れ", "予報", "weather", "forecast", "傘"]
        filtered: List[Dict[str, Any]] = []
        for a in alts:
            title = (a.get("title") or "")
            desc = (a.get("description") or "")
            text = f"{title} {desc}".lower()
            if any(k.lower() in text for k in kws):
                filtered.append(a)
        return filtered

    return alts


def _dedupe_alts(alts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    alternatives リストの重複排除と正規化。
    ★ セキュリティ修正: None/不正な型に対する防御的なハンドリング
    """
    if not alts:
        return []

    cleaned: List[Dict[str, Any]] = []
    for d in alts:
        if not isinstance(d, dict):
            continue

        # ★ 安全なstr取得: Noneや非文字列を空文字に変換
        raw_title = d.get("title")
        raw_desc = d.get("description")

        title = (str(raw_title) if raw_title is not None else "").strip()
        desc = (str(raw_desc) if raw_desc is not None else "").strip()

        # "none" 文字列は無効とみなす
        if title.lower() == "none":
            if desc:
                title = desc[:40]
            else:
                continue

        if not title and desc:
            title = desc[:40]
        elif not title:
            continue

        d["title"] = title
        d["description"] = desc
        cleaned.append(d)

    best: Dict[tuple, Dict[str, Any]] = {}
    for d in cleaned:
        # ★ 安全なキー生成: 必ず文字列であることを保証
        title_key = str(d.get("title") or "")
        desc_key = str(d.get("description") or "")
        key = (title_key, desc_key)

        # ★ 安全なスコア取得
        raw_score = d.get("score")
        try:
            score = float(raw_score) if raw_score is not None else 0.0
        except (TypeError, ValueError):
            score = 0.0

        prev = best.get(key)
        if prev is None:
            best[key] = d
        else:
            # ★ 安全な比較
            try:
                prev_score = float(prev.get("score", 0))
            except (TypeError, ValueError):
                prev_score = 0.0
            if score > prev_score:
                best[key] = d

    result = []
    seen: set = set()
    for d in cleaned:
        title_key = str(d.get("title") or "")
        desc_key = str(d.get("description") or "")
        key = (title_key, desc_key)
        if key in seen:
            continue
        if key in best:
            result.append(best[key])
        seen.add(key)

    return result


def _score_alternatives(
    intent: str,
    q: str,
    alts: List[Dict[str, Any]],
    telos_score: float,
    stakes: float,
    persona_bias: Dict[str, float] | None,
    ctx: Dict[str, Any] | None = None,
    telemetry: Dict[str, Any] | None = None,
) -> bool:
    """
    alternatives に対してスコアリングを行う。

    ★ リファクタリング: kernel_stages.score_alternatives() に委譲。
    設定値は config.scoring_cfg から取得されるため、マジックナンバーが排除されています。

    Args:
        intent: 推定意図。
        q: ユーザー入力テキスト。
        alts: スコアリング対象の候補。
        telos_score: 価値評価スコア。
        stakes: 意思決定の重要度。
        persona_bias: ペルソナ重み。
        ctx: 追加文脈。
        telemetry: 劣化運転情報を反映する辞書。

    Returns:
        bool: strategy_core による追加スコアリングが成功した場合 ``True``。
    """
    from .kernel_stages import score_alternatives as _score_alts_impl

    _score_alts_impl(
        intent=intent,
        query=q,
        alternatives=alts,
        telos_score=telos_score,
        stakes=stakes,
        persona_bias=persona_bias,
        context=ctx,
    )

    # ---- strategy_core 側でさらにランク付けしたい場合のフック ----
    if strategy_core is not None and hasattr(strategy_core, "score_options"):
        try:
            bias = persona_bias or {}
            scored = strategy_core.score_options(
                alts,
                ctx or {},
                intent=intent,
                query=q,
                telos_score=telos_score,
                stakes=stakes,
                persona_bias=bias,
            )
            if isinstance(scored, list) and scored:
                score_map = {}
                for o in scored:
                    # OptionScore dataclass or dict — extract id and score
                    if hasattr(o, "option_id"):
                        oid = o.option_id
                        sc = getattr(o, "fusion_score", 0.0)
                    elif isinstance(o, dict):
                        oid = o.get("id")
                        sc = o.get("score", o.get("fusion_score", 0.0))
                    else:
                        continue  # skip non-dict, non-dataclass items
                    if not oid:
                        continue
                    score_map[oid] = _safe_float(sc, 0.0)

                for a in alts:
                    oid = a.get("id")
                    if not oid:
                        continue
                    if oid in score_map:
                        a["score"] = round(score_map[oid], 4)
            return True
        except (TypeError, ValueError, RuntimeError):
            logger.warning("[Kernel] _score_alternatives strategy scoring failed", exc_info=True)
            if isinstance(telemetry, dict):
                telemetry.setdefault("degraded_subsystems", [])
                telemetry.setdefault("metrics", {})
                telemetry["degraded_subsystems"].append("strategy_scoring")
                telemetry["metrics"]["strategy_scoring_degraded"] = True
            return False
    return False


def _score_alternatives_with_value_core_and_persona(
    intent: str,
    q: str,
    alts: List[Dict[str, Any]],
    telos_score: float,
    stakes: float,
    persona_bias: Dict[str, float] | None,
    ctx: Dict[str, Any] | None = None,
    telemetry: Dict[str, Any] | None = None,
) -> bool:
    """Thin delegate to ``_score_alternatives()``.

    .. deprecated::
        Prefer ``_score_alternatives()`` directly. Scheduled for removal.
    """
    score_kwargs: Dict[str, Any] = {
        "intent": intent,
        "q": q,
        "alts": alts,
        "telos_score": telos_score,
        "stakes": stakes,
        "persona_bias": persona_bias,
        "ctx": ctx,
    }
    if telemetry is not None:
        score_kwargs["telemetry"] = telemetry
    return bool(_score_alternatives(**score_kwargs))

# ============================================================
# decide 本体 (v2-compatible)
# ★ QA処理は kernel_qa.py に分離
# ★ シグネチャは元のまま維持
# ============================================================

async def decide(
    context: Dict[str, Any],
    query: str,
    alternatives: List[Dict[str, Any]] | None,
    min_evidence: int = 1,
) -> Dict[str, Any]:
    """Return a decision payload from prepared inputs.

    Notes:
        - ``pipeline.py`` is the only orchestrator and must prepare context,
          evidence, planner output, and side-effectful operations.
        - This function stays focused on deterministic-ish decision logic.
    """
    start_ts = time.time()

    # ---- context を安全に固める ----
    ctx: Dict[str, Any] = dict(context or {})
    user_id = ctx.get("user_id") or "cli"

    fast_mode = bool(ctx.get("fast") or ctx.get("mode") == "fast")

    req_id = ctx.get("request_id") or uuid.uuid4().hex
    q_text = _to_text(query or ctx.get("query") or "")

    evidence: List[Dict[str, Any]] = []
    critique: List[Dict[str, Any]] = []
    debate_logs: List[Dict[str, Any]] = []
    extras: Dict[str, Any] = {}
    memory_evidence_count: int = 0
    degraded_subsystems: List[str] = []

    extras.setdefault("metrics", {})

    mode = ctx.get("mode") or ""
    tw = (ctx.get("telos_weights") or {})
    w_trans = _safe_float(tw.get("W_Transcendence", 0.6), 0.6)
    w_strug = _safe_float(tw.get("W_Struggle", 0.4), 0.4)
    telos_score = round(0.5 * w_trans + 0.5 * w_strug, 3)
    stakes = _safe_float(ctx.get("stakes", 0.5), 0.5)

    # --- Simple QA ---
    simple_kind = _detect_simple_qa(q_text)
    if simple_kind is not None:
        return _handle_simple_qa(
            kind=simple_kind,
            q=q_text,
            ctx=ctx,
            req_id=req_id,
            telos_score=telos_score,
        )

    # --- knowledge_qa ---
    try:
        if _detect_knowledge_qa(q_text):
            return _handle_knowledge_qa(
                q=q_text,
                ctx=ctx,
                req_id=req_id,
                telos_score=telos_score,
            )
    except (TypeError, ValueError, RuntimeError):
        logger.warning("[Kernel] knowledge_qa detection/handling failed", exc_info=True)

    prepared_evidence = ctx.get("evidence")
    if not isinstance(prepared_evidence, list):
        prepared_evidence = ctx.get("_pipeline_evidence")
    legacy_skip_reasons: Dict[str, str] = {}
    if isinstance(prepared_evidence, list):
        evidence.extend(prepared_evidence)
    memory_evidence_count = len(evidence)
    if isinstance(ctx.get("_pipeline_evidence"), list):
        legacy_skip_reasons["memory_search"] = "provided_by_pipeline"
    extras["memory"] = {
        "source": "pipeline_provided" if legacy_skip_reasons else "context_prepared",
        "evidence_count": memory_evidence_count,
    }

    # Persona
    try:
        persona = adapt.load_persona()
        persona_bias: Dict[str, float] = adapt.clean_bias_weights(
            dict(persona.get("bias_weights") or {})
        )
    except (TypeError, ValueError, RuntimeError, OSError) as e:
        persona = {}
        persona_bias = {}
        logger.warning("[kernel] adapt.load_persona failed: %s", e)

    world_sim = ctx.get("world_simulation")
    if world_sim is None and isinstance(ctx.get("_world_sim_result"), dict):
        world_sim = ctx.get("_world_sim_result")
    if isinstance(ctx.get("env_tools"), dict):
        extras["env_tools"] = dict(ctx.get("env_tools") or {})

    # intent
    intent = _detect_intent(q_text)

    # =======================================================
    # Planner output is accepted from context; kernel does not orchestrate it.
    # =======================================================

    alts: List[Dict[str, Any]] = list(alternatives or [])
    alts = _filter_alts_by_intent(intent, q_text, alts)

    planner_obj = ctx.get("planner") if isinstance(ctx.get("planner"), dict) else None
    if planner_obj is None and isinstance(ctx.get("_pipeline_planner"), dict):
        planner_obj = ctx.get("_pipeline_planner")
        legacy_skip_reasons["planner"] = "provided_by_pipeline"
    if planner_obj is not None:
        steps = planner_obj.get("steps") or []
        if steps and not alts:
            for idx, st in enumerate(steps, start=1):
                if not isinstance(st, dict):
                    continue
                sid = st.get("id") or f"step_{idx}"
                title = st.get("title") or f"step_{idx}"
                detail = st.get("detail") or st.get("description") or ""

                alt = _mk_option(
                    title=title,
                    description=detail,
                    _id=sid,
                )
                alt["meta"] = st
                alts.append(alt)

    if not alts and planner_obj is None:
        degraded_subsystems.append("planner_fallback")
        extras["metrics"]["planner_fallback_used"] = True
        try:
            planner_obj = planner_core.plan_for_veritas_agi(
                context=ctx,
                query=q_text,
            )
            steps = planner_obj.get("steps") or []
            for idx, st in enumerate(steps, start=1):
                if not isinstance(st, dict):
                    continue
                sid = st.get("id") or f"step_{idx}"
                title = st.get("title") or f"step_{idx}"
                detail = st.get("detail") or st.get("description") or ""
                alt = _mk_option(title=title, description=detail, _id=sid)
                alt["meta"] = st
                alts.append(alt)
        except Exception as e:  # pragma: no cover - planner calls LLM subsystem which may raise LLMError and other non-standard exceptions
            extras.setdefault("planner_error", {})
            extras["planner_error"]["detail"] = repr(e)

    if not alts:
        alts = _gen_options_by_intent(intent)

    if planner_obj is not None:
        extras["planner"] = planner_obj

    # alternatives 整形・スコアリング
    alts = _dedupe_alts(alts)
    strategy_scored = _score_alternatives(
        intent,
        q_text,
        alts,
        telos_score,
        stakes,
        persona_bias,
        ctx,
        {
            "degraded_subsystems": degraded_subsystems,
            "metrics": extras["metrics"],
        },
    )
    extras["metrics"]["strategy_scoring_applied"] = bool(strategy_scored)

    # =======================================================
    # DebateOS
    # =======================================================
    chosen: Dict[str, Any] | None = None

    if fast_mode:
        if alts:
            chosen = max(alts, key=lambda d: _safe_float(d.get("score"), 1.0))
        else:
            chosen = _mk_option("デフォルト選択")
        debate_logs.append({
            "summary": "fast_mode のため DebateOS をスキップ",
            "risk_delta": 0.0,
            "suggested_choice_id": chosen.get("id"),
            "source": "fast_mode_local",
        })
    else:
        try:
            debate_result = debate_core.run_debate(
                query=q_text,
                options=alts,
                context={
                    "user_id": user_id,
                    "stakes": stakes,
                    "telos_weights": tw,
                    "mode": mode,
                },
            )

            debate_chosen = debate_result.get("chosen")
            chosen = debate_chosen

            enriched_alts = debate_result.get("options") or alts

            extras["debate"] = {
                "raw": debate_result.get("raw"),
                "source": debate_result.get("source", "openai_llm"),
            }

            debate_logs.append({
                "summary": "Multi-Agent DebateOS により候補が評価されました。",
                "risk_delta": 0.0,
                "suggested_choice_id": chosen.get("id") if isinstance(chosen, dict) else None,
                "source": debate_result.get("source", "openai_llm"),
            })

            alts = _dedupe_alts(enriched_alts)

        except Exception as e:
            if alts:
                chosen = max(alts, key=lambda d: _safe_float(d.get("score"), 1.0))
            else:
                chosen = _mk_option("フォールバック選択")
            debate_logs.append({
                "summary": f"DebateOS フォールバック (例外: {repr(e)[:80]})",
                "risk_delta": 0.0,
                "suggested_choice_id": chosen.get("id"),
                "source": "fallback",
            })

    if chosen is None:
        chosen = {
            "id": f"debate_reject_all_{uuid.uuid4().hex[:8]}",
            "title": "全ての候補案がDebateOSにより却下されました",
            "description": "質問内容と無関係、または安全性の観点から不適切と判断されました。",
            "score": 0.0,
            "score_raw": 0.0,
            "verdict": "reject_all",
        }
        extras.setdefault("debate", {})
        extras["debate"]["reject_all"] = True

    if isinstance(world_sim, dict) and isinstance(chosen, dict):
        chosen["world"] = world_sim

    # Evidence
    evidence.append({
        "source": "internal:kernel",
        "uri": None,
        "snippet": f"query='{q_text}' evaluated with {len(alts)} alternatives (mode={mode})",
        "confidence": 0.8,
    })

    # FUJI Gate
    try:
        fuji_result = fuji_core.evaluate(
            q_text,
            context={
                "user_id": user_id,
                "stakes": stakes,
                "mode": mode,
                "telos_score": telos_score,
                "fuji_safe_applied": ctx.get("fuji_safe_applied", False),
            },
            evidence=evidence,
            alternatives=alts,
        )
    except (TypeError, ValueError, RuntimeError, OSError, TimeoutError) as e:
        logger.error("FUJI gate evaluation failed, defaulting to deny: %s", repr(e))
        fuji_result = {
            "status": "deny",
            "decision_status": "deny",
            "rejection_reason": "fuji_gate_error",
            "reasons": [f"fuji_error:{repr(e)[:80]}"],
            "violations": [],
            "risk": 1.0,
            "checks": [],
            "guidance": None,
            "modifications": [],
            "redactions": [],
            "safe_instructions": [],
        }
        extras.setdefault("fuji_error", {})
        extras["fuji_error"]["detail"] = repr(e)

    # =======================================================
    # AffectOS / ReasonOS: 自己評価 & 理由 & Self-Refine テンプレ
    # ★ 実装は kernel_post_choice.py に分離
    # =======================================================
    from . import kernel_post_choice as _post_choice

    await _post_choice.enrich_affect(
        query=q_text,
        chosen=chosen,
        fuji_result=fuji_result,
        telos_score=telos_score,
        affect_core=affect_core,
        extras=extras,
    )
    await _post_choice.enrich_reason(
        query=q_text,
        telos_score=telos_score,
        fuji_result=fuji_result,
        reason_core=reason_core,
        user_id=user_id,
        mode=mode,
        intent=intent,
        planner=extras.get("planner"),
        extras=extras,
    )
    await _post_choice.enrich_reflection(
        query=q_text,
        chosen=chosen,
        fuji_result=fuji_result,
        telos_score=telos_score,
        reason_core=reason_core,
        planner=extras.get("planner"),
        stakes=stakes,
        fast_mode=fast_mode,
        extras=extras,
    )

    extras.setdefault("agi_goals", {})
    if fast_mode:
        extras["agi_goals"]["skipped"] = {"reason": "fast_mode"}
    else:
        extras["agi_goals"]["status"] = "delegated_to_pipeline"

    # =======================================================
    # Episode logging side-effects
    # ★ 実装は kernel_episode.py に分離
    # =======================================================
    from . import kernel_episode as _episode

    _episode.save_episode(
        query=q_text,
        chosen=chosen,
        ctx=ctx,
        intent=intent,
        mode=mode,
        telos_score=telos_score,
        req_id=req_id,
        mem_core=mem_core,
        redact_payload_fn=redact_payload,
        extras=extras,
    )

    if ctx.get("auto_doctor", False):
        extras.setdefault("doctor", {})
        if not _is_doctor_confinement_profile_active():
            extras["doctor"]["skipped"] = "confinement_required"
            extras["doctor"]["security_warning"] = (
                "auto_doctor requires seccomp/AppArmor confinement"
            )
        else:
            extras["doctor"]["skipped"] = "delegated_to_pipeline"

    try:
        latency_ms = int((time.time() - start_ts) * 1000)
        extras["metrics"]["latency_ms"] = latency_ms
    except (TypeError, ValueError, OverflowError) as e:
        logger.debug("latency_ms calculation failed: %s", e)

    if degraded_subsystems:
        extras["degraded_subsystems"] = sorted(set(degraded_subsystems))

    legacy_flag_map = {
        "_world_state_injected": ("world_model_inject", "already_injected_by_pipeline"),
        "_episode_saved_by_pipeline": ("episode_save", "already_saved_by_pipeline"),
        "_world_state_updated_by_pipeline": ("world_state_update", "already_done_by_pipeline"),
        "_daily_plans_generated_by_pipeline": ("daily_plans", "already_generated_by_pipeline"),
    }
    for flag, reason_tuple in legacy_flag_map.items():
        if ctx.get(flag):
            key, value = reason_tuple
            legacy_skip_reasons[key] = value
    if isinstance(ctx.get("_pipeline_env_tools"), dict):
        legacy_skip_reasons["env_tools"] = "provided_by_pipeline"
    elif fast_mode:
        legacy_skip_reasons["env_tools"] = "fast_mode"

    if legacy_skip_reasons:
        extras["_skip_reasons"] = legacy_skip_reasons

    # =======================================================
    # レスポンス構築（旧 DecideResponse 互換 shape に寄せる）
    # =======================================================
    gate = {
        "risk": float(fuji_result.get("risk", 0.05)),
        "telos_score": float(telos_score),
        "decision_status": fuji_result.get("decision_status", fuji_result.get("status", "allow")),
        "reason": None,
        "modifications": fuji_result.get("modifications", []),
    }

    values = {
        "scores": {},
        "total": float(telos_score),
        "top_factors": [],
        "rationale": "kernel.decide v2-compatible",
    }

    decision_status = gate["decision_status"]
    rejection_reason = fuji_result.get("rejection_reason")

    return {
        "request_id": req_id,
        "chosen": chosen,
        "alternatives": alts,
        "evidence": evidence,
        "critique": critique,
        "debate": debate_logs,
        "telos_score": telos_score,
        "fuji": fuji_result,
        "rsi_note": None,
        "summary": "kernel.decide v2-compatible",
        "description": "二重実行解消版（後方互換性維持＋AffectOS連携）",
        "extras": extras,
        "memory_evidence_count": memory_evidence_count,
        "memory_citations": extras.get("memory", {}).get("citations", []),
        "memory_used_count": memory_evidence_count,
        "meta": {
            "memory_evidence_count": memory_evidence_count,
            "kernel_version": "v2-compatible",
        },
        # 旧 DecideResponse との互換フィールド
        "gate": gate,
        "values": values,
        "persona": persona,
        "version": "veritas-api 1.x",
        "decision_status": decision_status,
        "rejection_reason": rejection_reason,
    }
