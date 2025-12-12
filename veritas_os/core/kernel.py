
# veritas_os/core/kernel.py (v2-compatible)
# -*- coding: utf-8 -*-
"""
VERITAS kernel.py v2-compatible - 後方互換性を維持した二重実行解消版

★ 重要: 既存の decide() シグネチャは変更しない
★ context 内のフラグで二重実行をスキップ判定
"""
from __future__ import annotations

import re
import uuid
import time
import sys
import subprocess
from datetime import datetime
from typing import Any, Dict, List

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

try:  # 任意: 戦略レイヤー（なければ無視）
    from . import strategy as strategy_core  # type: ignore
except Exception:  # pragma: no cover
    strategy_core = None  # type: ignore

from veritas_os.tools import call_tool


# ============================================================
# 環境ツールラッパ
# ============================================================

def run_env_tool(kind: str, **kwargs) -> dict:
    try:
        return call_tool(kind, **kwargs)
    except Exception as e:
        return {
            "ok": False,
            "results": [],
            "error": f"env_tool error: {repr(e)[:200]}",
        }


# ============================================================
# ユーティリティ
# ============================================================

def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _tokens(s: str) -> List[str]:
    s = (s or "").replace("　", " ").lower()
    return [t for t in s.split() if t]


def _to_text(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        for k in ("title", "text", "description", "prompt"):
            if k in x and isinstance(x[k], str):
                return x[k]
    return str(x)


def _mk_option(title: str, description: str = "", _id: str | None = None) -> Dict[str, Any]:
    return {
        "id": _id or uuid.uuid4().hex,
        "title": title,
        "description": description,
        "score": 1.0,
    }


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


# ============================================================
# Intent 検出（事前コンパイル済み正規表現）
# ============================================================

INTENT_PATTERNS = {
    "weather": re.compile(r"(天気|気温|降水|雨|晴れ|weather|forecast)", re.I),
    "health": re.compile(r"(疲れ|だる|体調|休む|回復|睡眠|寝|サウナ)", re.I),
    "learn": re.compile(r"(とは|仕組み|なぜ|how|why|教えて|違い|比較)", re.I),
    "plan": re.compile(r"(計画|進め|やるべき|todo|最小ステップ|スケジュール|plan)", re.I),
}


def _detect_intent(q: str) -> str:
    q = (q or "").strip().lower()
    for name, pattern in INTENT_PATTERNS.items():
        if pattern.search(q):
            return name
    return "plan"


def _gen_options_by_intent(intent: str) -> List[Dict[str, Any]]:
    if intent == "weather":
        return [
            _mk_option("天気アプリ/サイトで明日の予報を確認する"),
            _mk_option("降水確率が高い時間にリマインドを設定する"),
            _mk_option("傘・レインウェア・防水靴を準備する"),
        ]
    if intent == "health":
        return [
            _mk_option("今日は休息し回復を最優先にする"),
            _mk_option("15分の軽い散歩で血流を上げる"),
            _mk_option("短時間サウナ＋十分な水分補給を行う"),
        ]
    if intent == "learn":
        return [
            _mk_option("一次情報（公式/論文）を調べる"),
            _mk_option("要点を3行に要約する"),
            _mk_option("学んだことを1つだけ行動に落とす"),
        ]
    return [
        _mk_option("最小ステップで前進する"),
        _mk_option("情報収集を優先する"),
        _mk_option("今日は休息し回復に充てる"),
    ]


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
    if not alts:
        return alts

    cleaned: List[Dict[str, Any]] = []
    for d in alts:
        if not isinstance(d, dict):
            continue

        title = (d.get("title") or "").strip()
        desc = (d.get("description") or "").strip()

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
        key = (d["title"], d["description"])
        score = float(d.get("score", 0))

        prev = best.get(key)
        if prev is None or score > float(prev.get("score", 0)):
            best[key] = d

    result = []
    seen = set()
    for d in cleaned:
        key = (d["title"], d["description"])
        if key in seen:
            continue
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
    alternatives に対して
    - intent 固有のヒューリスティック
    - persona_bias（ValueCore 用）
    - Telos スコア
    を掛け合わせて score / score_raw を更新する。

    value_core / strategy_core が定義されていればそれも利用し、
    未定義なら従来ロジックだけでスコアリングする。
    """
    ql = (q or "").lower()
    bias = persona_bias or {}
    ctx = ctx or {}

    # value_core / OptionScore が利用可能かどうかを事前チェック
    vc_compute = getattr(value_core, "compute_value_score", None)
    OptionScore = getattr(value_core, "OptionScore", None)
    has_value_core = callable(vc_compute) and OptionScore is not None

    def _kw_hit(title: str, kws: List[str]) -> bool:
        t = (title or "").lower()
        return any(k in t for k in kws)

    if not alts:
        return

    for a in alts:
        base = _safe_float(a.get("score"), 1.0)
        title = a.get("title", "") or ""
        desc = a.get("description", "") or ""

        # ---- intent ヒューリスティック ----
        if intent == "weather" and _kw_hit(title, ["予報", "降水", "傘", "天気"]):
            base += 0.4
        elif intent == "health" and _kw_hit(title, ["休息", "回復", "散歩", "サウナ", "睡眠"]):
            base += 0.4
        elif intent == "learn" and _kw_hit(title, ["一次情報", "要約", "行動"]):
            base += 0.35
        elif intent == "plan" and _kw_hit(title, ["最小", "情報収集", "休息", "リファクタ", "テスト"]):
            base += 0.3

        # クエリ内容と候補タイトルの組み合わせによる微調整
        if any(k in ql for k in ["雨", "降水", "umbrella", "forecast"]) and "傘" in title:
            base += 0.2

        # stakes が高い場合は「休息・情報収集寄り」をやや優遇
        if stakes >= 0.7 and _kw_hit(title, ["休息", "回復", "情報"]):
            base += 0.2

        # ---- persona bias ----
        by_title = bias.get(title.lower(), 0.0)
        by_fuzzy = adapt.fuzzy_bias_lookup(bias, title)
        by_id = bias.get(f"@id:{a.get('id')}", 0.0)
        bias_boost = max(by_title, by_fuzzy, by_id)
        base *= (1.0 + 0.3 * bias_boost)

        # ---- Telos スコアによる全体スケール ----
        base *= (0.9 + 0.2 * max(0.0, min(1.0, telos_score)))

        # ---- value_core があれば ValueScore を乗算 ----
        if has_value_core:
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
                base *= vscore
            except Exception:
                # value_core 内部でエラーが出ても全体は止めない
                pass

        a["score_raw"] = _safe_float(a.get("score"), 1.0)
        a["score"] = round(base, 4)

    # ---- strategy_core 側でさらにランク付けしたい場合のフック ----
    if strategy_core is not None and hasattr(strategy_core, "score_options"):
        try:
            scored = strategy_core.score_options(
                intent=intent,
                query=q,
                options=alts,
                telos_score=telos_score,
                stakes=stakes,
                persona_bias=bias,
                context=ctx,
            )
            if isinstance(scored, list) and scored:
                # 戻り値の各要素に score があれば kernel 側に反映
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
            # strategy_core が壊れていても decide 全体は止めない
            pass


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
# Simple QA モード（事前コンパイル済み正規表現）
# ============================================================

SIMPLE_QA_PATTERNS = {
    "time": re.compile(r"^(今|いま).*(何時|なんじ)[？?]?$"),
    "weekday": re.compile(r"^(今日|きょう).*(何曜日|なんようび)[？?]?$"),
    "date": re.compile(r"^(今日|きょう).*(何日|なんにち|日付)[？?]?$"),
    "time_en": re.compile(r"^what time is it[？?]?$", re.I),
    "weekday_en": re.compile(r"^what day is it[？?]?$", re.I),
}

AGI_BLOCK_KEYWORDS = [
    "agi", "ＡＧＩ", "veritas", "ヴェリタス", "ベリタス",
    "プロトagi", "proto-agi",
]


def _detect_simple_qa(q: str) -> str | None:
    q = (q or "").strip()
    ql = q.lower()

    if any(k in ql for k in AGI_BLOCK_KEYWORDS):
        return None

    if len(q) > 25:
        return None

    qj = q.replace("　", " ")

    if SIMPLE_QA_PATTERNS["time"].search(qj):
        return "time"
    if SIMPLE_QA_PATTERNS["weekday"].search(qj):
        return "weekday"
    if SIMPLE_QA_PATTERNS["date"].search(qj):
        return "date"
    if SIMPLE_QA_PATTERNS["time_en"].search(ql):
        return "time"
    if SIMPLE_QA_PATTERNS["weekday_en"].search(ql):
        return "weekday"
    if "today" in ql and "date" in ql and len(ql) < 40:
        return "date"

    return None


def _handle_simple_qa(
    kind: str,
    q: str,
    ctx: Dict[str, Any],
    req_id: str,
    telos_score: float,
) -> Dict[str, Any]:
    """
    Simple QA の戻り値を DecideResponse 完全互換に修正
    """
    now = datetime.now()
    answer_str = ""
    title = ""
    description = ""

    if kind == "time":
        answer_str = now.strftime("%H:%M")
        title = f"現在時刻は {answer_str} 頃です"
        description = "simple QA モード: システム時刻から現在時刻を直接回答しました。"
    elif kind == "weekday":
        weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        wd = weekdays[now.weekday()]
        answer_str = wd + "曜日"
        title = f"今日は{answer_str}です"
        description = "simple QA モード: システム日付から曜日を直接回答しました。"
    elif kind == "date":
        answer_str = now.strftime("%Y-%m-%d")
        title = f"今日は {answer_str} 頃の日付です"
        description = "simple QA モード: システム日付から今日の日付を直接回答しました。"
    else:
        answer_str = ""
        title = "simple QA モードで回答できませんでした"
        description = "想定外のsimple QA種別のため、通常のdecisionパイプラインを利用してください。"

    chosen = {
        "id": uuid.uuid4().hex,
        "title": title,
        "description": description,
        "score": 1.0,
        "score_raw": 1.0,
    }

    evidence = [
        {
            "source": "internal:simple_qa",
            "uri": None,
            "snippet": f"simple_qa kind={kind} for query='{q}'",
            "confidence": 0.9,
        }
    ]

    extras: Dict[str, Any] = {
        "simple_qa": {
            "kind": kind,
            "answer": answer_str,
            "mode": "bypass_debate",
        }
    }

    # DecideResponse 完全互換
    return {
        "request_id": req_id,
        "chosen": chosen,
        "alternatives": [chosen],
        "evidence": evidence,
        "critique": [],
        "debate": [],
        "telos_score": telos_score,
        "fuji": {
            "status": "allow",
            "decision_status": "allow",
            "reasons": [],
            "violations": [],
            "risk": 0.05,
            "checks": [],
            "guidance": None,
            "modifications": [],
            "redactions": [],
            "safe_instructions": [],
        },
        "rsi_note": None,
        "summary": "simple QA モードで直接回答しました。",
        "description": description,
        "extras": extras,
        "gate": {
            "risk": 0.05,
            "telos_score": telos_score,
            "decision_status": "allow",
            "reason": None,
            "modifications": [],
        },
        "values": {
            "scores": {},
            "total": telos_score,
            "top_factors": [],
            "rationale": "simple QA",
        },
        "persona": _safe_load_persona(),
        "version": "veritas-api 1.x",
        "decision_status": "allow",
        "rejection_reason": None,
        "memory_citations": [],
        "memory_used_count": 0,
        "memory_evidence_count": 0,
        "meta": {
            "kind": "simple_qa",
            "memory_evidence_count": 0,
        },
    }


# ============================================================
# knowledge_qa モード
# ============================================================

def _detect_knowledge_qa(q: str) -> bool:
    q = (q or "").strip()

    if len(q) < 4:
        return False

    if re.search(r"とは[？?]?$", q):
        return True
    if re.search(r"(どこ|どこにある)[？?]?$", q):
        return True
    if re.search(r"(誰|だれ)[？?]?$", q):
        return True
    if any(k in q for k in ["県庁所在地", "首都", "人口", "面積", "標高"]):
        return True

    ql = q.lower()
    if any(w in ql for w in ["what is", "who is", "where is"]):
        return True

    return False


def _handle_knowledge_qa(
    q: str,
    ctx: Dict[str, Any],
    req_id: str,
    telos_score: float,
) -> Dict[str, Any]:
    """
    Web検索ベースの軽量な知識QA。
    ★ 旧バージョンとの互換性を保ちつつ、FUJI Gate を通すように修正済み。
    """
    user_id = ctx.get("user_id") or "cli"
    stakes = _safe_float(ctx.get("stakes", 0.5), 0.5)
    mode = ctx.get("mode") or ""

    search_res = run_env_tool(
        "web_search",
        query=q,
        max_results=3,
    )

    answer_title = ""
    answer_desc = ""

    if search_res.get("ok") and search_res.get("results"):
        top = search_res["results"][0]
        title = top.get("title") or ""
        url = top.get("url") or ""
        snippet = top.get("snippet") or ""

        answer_title = f"知識QA: {q}"
        answer_desc_parts = []
        if snippet:
            answer_desc_parts.append(f"要約: {snippet}")
        if title:
            answer_desc_parts.append(f"参考タイトル: {title}")
        if url:
            answer_desc_parts.append(f"参考URL: {url}")
        answer_desc = " / ".join(answer_desc_parts)
    else:
        answer_title = f"知識QA: {q} に対する明確な回答を取得できませんでした"
        answer_desc = f"error={search_res.get('error')}"

    chosen = {
        "id": uuid.uuid4().hex,
        "title": answer_title,
        "description": answer_desc,
        "score": 1.0,
        "score_raw": 1.0,
    }

    evidence = [
        {
            "source": "internal:knowledge_qa",
            "uri": None,
            "snippet": f"knowledge_qa for query='{q}'",
            "confidence": 0.8,
        }
    ]

    extras: Dict[str, Any] = {
        "knowledge_qa": {
            "mode": "bypass_debate",
            "web_search": search_res,
        }
    }

    # ★ FUJI Gate を通す（高リスク用途での一貫性確保）
    try:
        fuji_result = fuji_core.evaluate(
            q,
            context={
                "user_id": user_id,
                "stakes": stakes,
                "mode": mode,
                "telos_score": telos_score,
                "fuji_safe_applied": ctx.get("fuji_safe_applied", False),
            },
            evidence=evidence,
            alternatives=[chosen],
        )
    except Exception as e:
        fuji_result = {
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
        "rationale": "knowledge QA",
    }

    # DecideResponse 完全互換
    return {
        "request_id": req_id,
        "chosen": chosen,
        "alternatives": [chosen],
        "evidence": evidence,
        "critique": [],
        "debate": [],
        "telos_score": telos_score,
        "fuji": fuji_result,
        "rsi_note": None,
        "summary": "knowledge_qa モードで直接回答しました。",
        "description": answer_desc,
        "extras": extras,
        "gate": gate,
        "values": values,
        "persona": _safe_load_persona(),
        "version": "veritas-api 1.x",
        "decision_status": gate["decision_status"],
        "rejection_reason": fuji_result.get("rejection_reason"),
        "memory_citations": [],
        "memory_used_count": 0,
        "memory_evidence_count": 0,
        "meta": {
            "kind": "knowledge_qa",
            "memory_evidence_count": 0,
        },
    }


# ============================================================
# decide 本体 (v2-compatible)
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
            print(f"[kernel] world_model.inject_state_into_context failed: {e}")

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
        pass

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
        print(f"[kernel] adapt.load_persona failed: {e}")

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
        fuji_result = {
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
    try:
        reason_natural = affect_core.generate_reason(
            query=q_text,
            planner=extras.get("planner"),
            values={"total": float(telos_score)},
            gate=fuji_result,
            context={
                "user_id": user_id,
                "mode": mode,
                "intent": intent,
            },
        )
        extras.setdefault("affect", {})
        extras["affect"]["natural"] = reason_natural
    except Exception as e:
        extras.setdefault("affect", {})
        extras["affect"]["natural_error"] = repr(e)

    # Self-Refine 用テンプレ（高リスク or 高 stakes のときだけ）
    try:
        risk_val = float(fuji_result.get("risk", 0.0))
        if (not fast_mode) and (stakes >= 0.7 or risk_val >= 0.5):
            refl_tmpl = await affect_core.generate_reflection_template(
                query=q_text,
                chosen=chosen,
                gate=fuji_result,
                values={"total": float(telos_score)},
                planner=extras.get("planner") or {},
            )
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

            try:
                mem_core.MEM.put("episodic", episode_record)
            except TypeError:
                mem_core.MEM.put(
                    user_id,
                    f"decision:{req_id}",
                    episode_record,
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
    auto_doctor = ctx.get("auto_doctor", True)
    if auto_doctor and not ctx.get("_doctor_triggered_by_pipeline"):
        try:
            subprocess.Popen(
                [sys.executable, "-m", "veritas_os.scripts.doctor"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
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





