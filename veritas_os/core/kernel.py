
# veritas_os/core/kernel.py (v2-compatible)
# -*- coding: utf-8 -*-
"""
VERITAS kernel.py v2-compatible - 後方互換性を維持した二重実行解消版

★ 重要: 既存の decide() シグネチャは変更しない
★ context 内のフラグで二重実行をスキップ判定
"""
from __future__ import annotations

import logging
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# ★ C-1 修正: doctor 自動起動のレート制限
# 高頻度リクエストでプロセスが溜まるのを防止（最低 60 秒間隔）
# ★ C-1b 修正: アクティブプロセス追跡で並行起動を防止
import threading as _threading
_DOCTOR_MIN_INTERVAL_SEC = 60.0
_doctor_last_run: float = 0.0
_doctor_active_proc: "subprocess.Popen | None" = None
_doctor_lock = _threading.Lock()


def _is_safe_python_executable(executable_path: str | None) -> bool:
    """Validate that a Python executable path is safe to launch.

    Args:
        executable_path: Path candidate, usually ``sys.executable``.

    Returns:
        ``True`` when the path points to an executable Python interpreter.

    Security:
        Auto-doctor launches a subprocess. Rejecting missing, non-absolute,
        non-executable, or unexpected binary names reduces command hijacking
        risk when runtime environment variables are tampered with.
    """
    import os

    if not executable_path:
        return False
    if not os.path.isabs(executable_path):
        return False
    if not os.path.isfile(executable_path):
        return False
    if not os.access(executable_path, os.X_OK):
        return False

    executable_name = os.path.basename(executable_path).lower().replace(".exe", "")
    return bool(re.match(r"^(python|pypy)[0-9.]*$", executable_name))


def _open_doctor_log_fd(log_path: str) -> int:
    """Open a doctor log file descriptor with secure defaults.

    The descriptor is opened with restrictive file permissions and validated
    as a regular file. When available, ``O_NOFOLLOW`` is enabled to reduce
    symlink-based redirection risks.

    Args:
        log_path: Absolute file path of the doctor log.

    Returns:
        File descriptor opened in append mode.

    Raises:
        OSError: If the file cannot be opened.
        ValueError: If the opened path is not a regular file.
    """
    import os
    import stat

    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    nofollow_flag = getattr(os, "O_NOFOLLOW", 0)
    if nofollow_flag:
        flags |= nofollow_flag

    fd = os.open(log_path, flags, 0o600)
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode):
        os.close(fd)
        raise ValueError("Doctor log path must point to a regular file")
    return fd

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
import inspect

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

# ★ セキュリティ修正: reason_core のインポート（存在しない場合は None）
try:
    from . import reason as reason_core
except (ImportError, ModuleNotFoundError):  # pragma: no cover
    reason_core = None  # type: ignore

# ★ QA処理を分離モジュールからインポート
from .kernel_qa import (
    detect_simple_qa as _detect_simple_qa,
    handle_simple_qa as _handle_simple_qa,
    detect_knowledge_qa as _detect_knowledge_qa,
    handle_knowledge_qa as _handle_knowledge_qa,
    SIMPLE_QA_PATTERNS,
    AGI_BLOCK_KEYWORDS,
)

try:  # 任意: 戦略レイヤー（なければ無視）
    from . import strategy as strategy_core  # type: ignore
except (ImportError, ModuleNotFoundError):  # pragma: no cover
    strategy_core = None  # type: ignore

try:
    from veritas_os.core.sanitize import mask_pii as _mask_pii  # type: ignore
    _HAS_SANITIZE = True
except (ImportError, ModuleNotFoundError):  # pragma: no cover
    _mask_pii = None  # type: ignore
    _HAS_SANITIZE = False

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
    except Exception as e:
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
    except Exception:
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
) -> None:
    """
    alternatives に対してスコアリングを行う。

    ★ リファクタリング: kernel_stages.score_alternatives() に委譲。
    設定値は config.scoring_cfg から取得されるため、マジックナンバーが排除されています。
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
                intent=intent,
                query=q,
                options=alts,
                telos_score=telos_score,
                stakes=stakes,
                persona_bias=bias,
                context=ctx or {},
            )
            if isinstance(scored, list) and scored:
                score_map = {}
                for o in scored:
                    oid = o.get("id")
                    if not oid:
                        continue
                    score_map[oid] = _safe_float(o.get("score"), 0.0)

                for a in alts:
                    oid = a.get("id")
                    if not oid:
                        continue
                    if oid in score_map:
                        a["score"] = round(score_map[oid], 4)
        except Exception:
            logger.warning("[Kernel] _score_alternatives strategy scoring failed", exc_info=True)


def _score_alternatives_with_value_core_and_persona(
    intent: str,
    q: str,
    alts: List[Dict[str, Any]],
    telos_score: float,
    stakes: float,
    persona_bias: Dict[str, float] | None,
    ctx: Dict[str, Any] | None = None,
) -> None:
    """
    ★ 後方互換ラッパ
    旧バージョンから呼ばれている名前を維持するための薄い wrapper。
    実装は _score_alternatives() に委譲する。
    """
    return _score_alternatives(
        intent=intent,
        q=q,
        alts=alts,
        telos_score=telos_score,
        stakes=stakes,
        persona_bias=persona_bias,
        ctx=ctx,
    )

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
    """
    VERITAS kernel.decide v2-compatible:
    
    ★ シグネチャは元のまま維持（後方互換性）
    ★ context 内のフラグで二重実行をスキップ判定
    """
    start_ts = time.time()

    # ---- context を安全に固める ----
    ctx_raw: Dict[str, Any] = dict(context or {})
    user_id = ctx_raw.get("user_id") or "cli"

    # スキップ理由を記録
    skip_reasons: Dict[str, str] = {}

    # ★ WorldModel 注入: pipeline が既に実行済みならスキップ
    if ctx_raw.get("_world_state_injected"):
        ctx = ctx_raw
        skip_reasons["world_model_inject"] = "already_injected_by_pipeline"
    else:
        try:
            ctx = world_model.inject_state_into_context(
                context=ctx_raw,
                user_id=user_id,
            )
            ctx["_world_state_injected"] = True
        except Exception as e:
            ctx = ctx_raw
            logger.warning("world_model.inject_state_into_context failed: %s", e)

    fast_mode = bool(ctx.get("fast") or ctx.get("mode") == "fast")

    req_id = ctx.get("request_id") or uuid.uuid4().hex
    q_text = _to_text(query or ctx.get("query") or "")

    evidence: List[Dict[str, Any]] = []
    critique: List[Dict[str, Any]] = []
    debate_logs: List[Dict[str, Any]] = []
    extras: Dict[str, Any] = {}
    memory_evidence_count: int = 0

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
    except Exception:
        logger.warning("[Kernel] knowledge_qa detection/handling failed", exc_info=True)

    # ★ Pipeline から渡された evidence があればそれを使用
    pipeline_evidence = ctx.get("_pipeline_evidence")
    if pipeline_evidence and isinstance(pipeline_evidence, list):
        evidence.extend(pipeline_evidence)
        memory_evidence_count = len(pipeline_evidence)
        extras["memory"] = {
            "source": "pipeline_provided",
            "evidence_count": memory_evidence_count,
        }
        skip_reasons["memory_search"] = "provided_by_pipeline"
    else:
        # MemoryOS 要約を取得
        try:
            memory_summary = mem_core.summarize_for_planner(
                user_id=user_id,
                query=q_text,
                limit=8,
            )
            ctx["memory_summary"] = memory_summary
            extras["memory"] = {
                "summary": memory_summary,
                "source": "MemoryOS.summarize_for_planner",
            }
        except Exception as e:
            extras["memory"] = {
                "error": f"memory summarize failed: {repr(e)[:80]}",
            }

    # Persona
    try:
        persona = adapt.load_persona()
        persona_bias: Dict[str, float] = adapt.clean_bias_weights(
            dict(persona.get("bias_weights") or {})
        )
    except Exception as e:
        persona = {}
        persona_bias = {}
        logger.warning("[kernel] adapt.load_persona failed: %s", e)

    # WorldModel simulate
    world_sim = None
    if ctx.get("_world_sim_done"):
        world_sim = ctx.get("_world_sim_result")
        skip_reasons["world_simulate"] = "already_done_by_pipeline"
    elif fast_mode:
        skip_reasons["world_simulate"] = "fast_mode"
    else:
        try:
            world_sim = world_model.simulate(
                user_id=user_id,
                query=q_text,
                chosen=None,
            )
            extras["world"] = {
                "prediction": world_sim,
                "source": "world.simulate()",
            }
        except Exception as e:
            extras["world"] = {
                "error": f"world.simulate failed: {repr(e)[:80]}",
            }

    # ★ env tools: pipeline から渡されていればスキップ
    env_logs: Dict[str, Any] = {}
    pipeline_env = ctx.get("_pipeline_env_tools")
    if pipeline_env and isinstance(pipeline_env, dict):
        env_logs = pipeline_env
        skip_reasons["env_tools"] = "provided_by_pipeline"
    elif fast_mode:
        env_logs["skipped"] = {"reason": "fast_mode"}
        skip_reasons["env_tools"] = "fast_mode"
    else:
        try:
            ql = q_text.lower()

            if ctx.get("use_env_tools"):
                env_logs["web_search"] = run_env_tool(
                    "web_search",
                    query=q_text,
                    max_results=3,
                )
                env_logs["github_search"] = run_env_tool(
                    "github_search",
                    query=q_text,
                    max_results=3,
                )
            else:
                if "github" in ql:
                    env_logs["github_search"] = run_env_tool(
                        "github_search",
                        query=q_text,
                        max_results=3,
                    )
                if any(k in ql for k in ["agi", "論文", "paper", "research"]):
                    env_logs["web_search"] = run_env_tool(
                        "web_search",
                        query=q_text,
                        max_results=3,
                    )
        except Exception as e:
            env_logs["error"] = f"run_env_tool failed: {repr(e)[:200]}"

    if env_logs:
        extras["env_tools"] = env_logs

    # intent
    intent = _detect_intent(q_text)

    # =======================================================
    # ★ Planner: pipeline から渡されていればスキップ
    # =======================================================

    alts: List[Dict[str, Any]] = list(alternatives or [])
    alts = _filter_alts_by_intent(intent, q_text, alts)

    planner_obj: Dict[str, Any] | None = None

    # ★ Pipeline から planner_result が渡されていれば使用
    pipeline_planner = ctx.get("_pipeline_planner")
    if pipeline_planner and isinstance(pipeline_planner, dict):
        planner_obj = pipeline_planner
        skip_reasons["planner"] = "provided_by_pipeline"
        
        steps = pipeline_planner.get("steps") or []
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

    # code_change_plan モード
    elif intent == "plan" and mode == "code_change_plan":
        bench_payload = ctx.get("bench_payload") or ctx.get("bench") or {}
        world_state_for_tasks = ctx.get("world_state")
        doctor_report = ctx.get("doctor_report")

        try:
            code_plan = planner_core.generate_code_tasks(
                bench=bench_payload,
                world_state=world_state_for_tasks,
                doctor_report=doctor_report,
            )
            extras["code_change_plan"] = code_plan
            planner_obj = {"mode": "code_change_plan", "plan": code_plan}

            tasks = code_plan.get("tasks") or []
            alts = []
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                tid = t.get("id") or uuid.uuid4().hex
                priority = (t.get("priority") or "medium").upper()
                title = t.get("title") or "コード変更タスク"
                kind = t.get("kind") or "code_change"
                module = t.get("module") or "unknown"
                path = t.get("path") or ""

                desc_parts = [f"kind={kind}", f"module={module}"]
                if path:
                    desc_parts.append(f"path={path}")
                if t.get("detail"):
                    desc_parts.append(f"detail={t['detail']}")

                alt = _mk_option(
                    title=f"[{priority}] {title}",
                    description=" / ".join(desc_parts),
                    _id=tid,
                )
                alt["meta"] = t
                alts.append(alt)

        except Exception as e:
            extras["code_change_plan_error"] = f"generate_code_tasks failed: {repr(e)[:120]}"

    # 通常モード → PlannerOS 呼び出し
    if not alts and planner_obj is None:
        try:
            planner_obj = planner_core.plan_for_veritas_agi(
                context=ctx,
                query=q_text,
            )
            steps = planner_obj.get("steps") or []

            alts = []
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

        except Exception as e:
            extras.setdefault("planner_error", {})
            extras["planner_error"]["detail"] = repr(e)
            if not alts:
                alts = _gen_options_by_intent(intent)

    if planner_obj is not None:
        extras["planner"] = planner_obj

    # alternatives 整形・スコアリング
    alts = _dedupe_alts(alts)
    _score_alternatives(intent, q_text, alts, telos_score, stakes, persona_bias, ctx)

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

    # MemoryOS から episodic evidence（pipeline 未提供時のみ）
    if not pipeline_evidence:
        try:
            decision_snapshot = {
                "request_id": req_id,
                "query": q_text,
                "context": ctx,
                "chosen": chosen,
                "alternatives": alts,
                "evidence": evidence,
                "extras": extras,
                "telos_score": telos_score,
            }

            mem_evs = mem_core.get_evidence_for_decision(
                decision_snapshot,
                user_id=user_id,
                top_k=max(min_evidence, 5),
            )
            if mem_evs:
                evidence.extend(mem_evs)
                memory_evidence_count = len(mem_evs)
                extras.setdefault("memory", {})
                extras["memory"]["evidence_count"] = memory_evidence_count
                extras["memory"]["citations"] = mem_evs
        except Exception as e:
            extras.setdefault("memory", {})
            extras["memory"]["evidence_error"] = f"get_evidence_for_decision failed: {repr(e)[:80]}"

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
    except Exception as e:
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
    # =======================================================
    try:
        affect_meta = affect_core.reflect({
            "query": q_text,
            "chosen": chosen,
            "gate": fuji_result,
            "values": {
                "total": float(telos_score),
                # 現時点では ema = total として扱う
                "ema": float(telos_score),
            },
        })
        extras.setdefault("affect", {})
        extras["affect"]["meta"] = affect_meta
    except Exception as e:
        extras.setdefault("affect", {})
        extras["affect"]["meta_error"] = repr(e)

    # 自然文 Reason（なぜこの決定が妥当か）
    # ★ セキュリティ修正: reason_core の存在チェックと安全な呼び出し
    try:
        if reason_core is not None and hasattr(reason_core, "generate_reason"):
            gen_reason_fn = reason_core.generate_reason
            reason_args = {
                "query": q_text,
                "planner": extras.get("planner"),
                "values": {"total": float(telos_score)},
                "gate": fuji_result,
                "context": {
                    "user_id": user_id,
                    "mode": mode,
                    "intent": intent,
                },
            }
            # ★ async/sync を安全に判定して呼び出し
            if asyncio.iscoroutinefunction(gen_reason_fn):
                reason_natural = await gen_reason_fn(**reason_args)
            else:
                reason_natural = gen_reason_fn(**reason_args)

            extras.setdefault("affect", {})
            extras["affect"]["natural"] = reason_natural
        else:
            extras.setdefault("affect", {})
            extras["affect"]["natural_error"] = "reason_core.generate_reason not available"
    except Exception as e:
        extras.setdefault("affect", {})
        extras["affect"]["natural_error"] = repr(e)

    # Self-Refine 用テンプレ（高リスク or 高 stakes のときだけ）
    # ★ セキュリティ修正: reason_core の存在チェックと安全な async 呼び出し
    try:
        risk_val = float(fuji_result.get("risk", 0.0))
        if (not fast_mode) and (stakes >= 0.7 or risk_val >= 0.5):
            if reason_core is not None and hasattr(reason_core, "generate_reflection_template"):
                gen_refl_fn = reason_core.generate_reflection_template
                refl_args = {
                    "query": q_text,
                    "chosen": chosen,
                    "gate": fuji_result,
                    "values": {"total": float(telos_score)},
                    "planner": extras.get("planner") or {},
                }
                # ★ async/sync を安全に判定して呼び出し
                if asyncio.iscoroutinefunction(gen_refl_fn):
                    refl_tmpl = await gen_refl_fn(**refl_args)
                else:
                    refl_tmpl = gen_refl_fn(**refl_args)

                if refl_tmpl:
                    extras.setdefault("affect", {})
                    extras["affect"]["reflection_template"] = refl_tmpl
    except Exception as e:
        extras.setdefault("affect", {})
        extras["affect"]["reflection_template_error"] = repr(e)

    # 学習＋AGIゴール自己調整
    if not fast_mode and not ctx.get("_agi_goals_adjusted_by_pipeline"):
        try:
            persona2 = adapt.update_persona_bias_from_history(window=50)

            b = dict(persona2.get("bias_weights") or {})
            key = (chosen.get("title") or "").strip().lower() or f"@id:{chosen.get('id')}"
            if key:
                b[key] = b.get(key, 0.0) + 0.05

            s = sum(b.values()) or 1.0
            b = {kk: vv / s for kk, vv in b.items()}
            b = adapt.clean_bias_weights(b)

            world_snap: Dict[str, Any] = {}
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

            extras.setdefault("agi_goals", {})
            extras["agi_goals"]["last_auto_adjust"] = {
                "value_ema": value_ema,
                "fuji_risk": fuji_risk,
            }

        except Exception as e:
            extras.setdefault("agi_goals", {})
            extras["agi_goals"]["error"] = repr(e)
    else:
        extras.setdefault("agi_goals", {})
        extras["agi_goals"]["skipped"] = {"reason": "fast_mode or pipeline"}

    # Decision ログを MemoryOS に保存（pipeline で保存済みならスキップ）
    if not ctx.get("_episode_saved_by_pipeline"):
        try:
            episode_text = (
                f"[query] {q_text}\n"
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
            redacted_episode_record = redact_payload(episode_record)
            if redacted_episode_record != episode_record:
                logger.warning(
                    "PII detected in kernel.decide episode log; masked before persistence."
                )
                extras.setdefault("memory_log", {})
                extras["memory_log"]["warning"] = (
                    "PII detected in episode log; masked before persistence."
                )

            try:
                mem_core.MEM.put("episodic", redacted_episode_record)
            except TypeError:
                mem_core.MEM.put(
                    user_id,
                    f"decision:{req_id}",
                    redacted_episode_record,
                )

        except Exception as e:
            extras.setdefault("memory_log", {})
            extras["memory_log"]["error"] = repr(e)
    else:
        skip_reasons["episode_save"] = "already_saved_by_pipeline"

    # =======================================================
    # metrics / world_state / doctor
    # =======================================================
    latency_ms: int | None = None
    try:
        latency_ms = int((time.time() - start_ts) * 1000)
        extras.setdefault("metrics", {})
        extras["metrics"]["latency_ms"] = latency_ms
    except Exception:
        pass

    # world_state.json 更新（Pipeline が行う場合はスキップ）
    if not ctx.get("_world_state_updated_by_pipeline"):
        try:
            world_model.update_from_decision(
                user_id=user_id,
                query=q_text,
                chosen=chosen,
                gate=fuji_result,
                values={"total": telos_score},
                planner=extras.get("code_change_plan") or extras.get("planner"),
                latency_ms=latency_ms,
            )
        except Exception as e:
            extras.setdefault("world_state_update", {})
            extras["world_state_update"]["error"] = repr(e)
    else:
        skip_reasons["world_state_update"] = "already_done_by_pipeline"

    # doctor 自動実行
    # ★ C-1 修正: レート制限付き（最低 _DOCTOR_MIN_INTERVAL_SEC 秒間隔）
    # ★ C-1b 修正: アクティブプロセス追跡で並行起動を防止
    auto_doctor = ctx.get("auto_doctor", True)
    if auto_doctor and not ctx.get("_doctor_triggered_by_pipeline"):
        global _doctor_last_run, _doctor_active_proc
        _should_run_doctor = False
        with _doctor_lock:
            # ★ C-1b: 既存プロセスがまだ実行中なら新規起動をスキップ
            if _doctor_active_proc is not None:
                if _doctor_active_proc.poll() is None:
                    extras.setdefault("doctor", {})
                    extras["doctor"]["skipped"] = "already_running"
                    _should_run_doctor = False
                else:
                    _doctor_active_proc = None
            if _doctor_active_proc is None:
                now = time.time()
                if now - _doctor_last_run >= _DOCTOR_MIN_INTERVAL_SEC:
                    _doctor_last_run = now
                    _should_run_doctor = True
                else:
                    extras.setdefault("doctor", {})
                    extras["doctor"]["skipped"] = "rate_limited"

        if _should_run_doctor:
            try:
                import os
                from pathlib import Path

                python_executable = sys.executable
                if not _is_safe_python_executable(python_executable):
                    raise ValueError("Invalid Python executable path")

                log_dir = Path(os.path.expanduser("~/.veritas/logs"))
                log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                doctor_log = log_dir / "doctor.log"
                # ★ セキュリティ修正: ログファイルを制限的なパーミッション (0o600) で開く
                fd = _open_doctor_log_fd(str(doctor_log))
                try:
                    os.write(fd, f"\n--- Doctor started at {datetime.now(timezone.utc).isoformat()} ---\n".encode("utf-8"))
                    doctor_timeout = 300  # 5 minutes max
                    proc = subprocess.Popen(
                        [python_executable, "-m", "veritas_os.scripts.doctor"],
                        stdout=fd,
                        stderr=subprocess.STDOUT,
                        shell=False,
                    )
                    # ★ C-1b: アクティブプロセスを追跡
                    with _doctor_lock:
                        _doctor_active_proc = proc
                    # Reap the subprocess in a background thread to prevent zombies;
                    # enforce a timeout to avoid indefinitely hanging processes.
                    def _make_doctor_reaper(p: subprocess.Popen, t: int):
                        """タイムアウト付きでdoctorプロセスを待機し、終了後にアクティブ追跡をクリアする。"""
                        def _run():
                            try:
                                p.wait(timeout=t)
                            except subprocess.TimeoutExpired:
                                p.kill()
                                p.wait()
                            finally:
                                with _doctor_lock:
                                    global _doctor_active_proc
                                    if _doctor_active_proc is p:
                                        _doctor_active_proc = None
                        return _run

                    _threading.Thread(
                        target=_make_doctor_reaper(proc, doctor_timeout),
                        daemon=True,
                    ).start()
                finally:
                    # Close our copy of the fd; the subprocess has its own copy.
                    os.close(fd)
            except Exception as e:
                extras.setdefault("doctor", {})
                extras["doctor"]["error"] = repr(e)

    # experiments / curriculum
    if not ctx.get("_daily_plans_generated_by_pipeline"):
        try:
            from . import experiments as experiment_core
            from . import curriculum as curriculum_core

            try:
                world_state_full = world_model.get_state()
            except Exception:
                world_state_full = None

            value_ema_for_day = float(telos_score)

            todays_exps = experiment_core.propose_experiments_for_today(
                user_id=user_id,
                world_state=world_state_full,
                value_ema=value_ema_for_day,
            )
            todays_tasks = curriculum_core.plan_today(
                user_id=user_id,
                world_state=world_state_full,
                value_ema=value_ema_for_day,
            )

            extras["experiments"] = [e.to_dict() for e in todays_exps]
            extras["curriculum"] = [t.to_dict() for t in todays_tasks]

        except Exception as e:
            extras.setdefault("daily_plans", {})
            extras["daily_plans"]["error"] = repr(e)
    else:
        skip_reasons["daily_plans"] = "already_generated_by_pipeline"

    # スキップ理由を extras に記録
    if skip_reasons:
        extras["_skip_reasons"] = skip_reasons

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
