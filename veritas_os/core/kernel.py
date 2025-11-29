# veritas_os/core/kernel.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import uuid
import time                    # ★ latency計測
import sys                     # ★ doctor起動用
import subprocess              # ★ doctor起動用
from datetime import datetime
from typing import Any, Dict, List

from . import adapt              # persona 学習
from . import evidence as evos   # いまは未使用だが将来のために残す
from . import debate             # Multi-Agent ReasonOS (DebateOS)
from . import world as world_model       # ★ WorldModel / world.simulate / inject_state_into_context
from . import planner as planner_core    # ★ code_change_plan 用
from . import agi_goals                  # ★ AGIゴール自己調整モジュール
from . import memory as mem_core         # ★ MemoryOS
from . import fuji as fuji_core          # ★ FUJI Gate
from . import debate as debate_core
from veritas_os.tools import call_tool   # env tools ラッパ用


# ============================================================
# 環境ツールラッパ（web_search / github_search など）
# ============================================================

def run_env_tool(kind: str, **kwargs) -> dict:
    """
    VERITAS から外部環境ツール(web_search / github_search など)を叩く薄いラッパー。
    decide 内では **必ずこの関数経由** で呼ぶ。
    """
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


def _detect_intent(q: str) -> str:
    q = (q or "").strip().lower()
    rules = {
        "weather": r"(天気|気温|降水|雨|晴れ|weather|forecast)",
        "health": r"(疲れ|だる|体調|休む|回復|睡眠|寝|サウナ)",
        "learn": r"(とは|仕組み|なぜ|how|why|教えて|違い|比較)",
        "plan": r"(計画|進め|やるべき|todo|最小ステップ|スケジュール|plan)",
    }
    for name, pat in rules.items():
        if re.search(pat, q):
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
# intent による alternatives のフィルタリング
# ============================================================

def _filter_alts_by_intent(
    intent: str,
    q: str,
    alts: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    intent に合わない過去オプションを落とすフィルタ。
    まずは weather 用: 天気と無関係な episodic オプションを弾く。
    """
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
    alternatives の重複を減らす:
      - title + description が同じものは1つにまとめる
      - title == 'None' や空のものは落とす
    """
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
) -> None:
    ql = (q or "").lower()
    bias = persona_bias or {}

    def _kw_hit(title: str, kws: List[str]) -> bool:
        t = (title or "").lower()
        return any(k in t for k in kws)

    for a in alts:
        base = _safe_float(a.get("score"), 1.0)
        title = a.get("title", "") or ""

        if intent == "weather" and _kw_hit(title, ["予報", "降水", "傘", "天気"]):
            base += 0.4
        elif intent == "health" and _kw_hit(title, ["休息", "回復", "散歩", "サウナ", "睡眠"]):
            base += 0.4
        elif intent == "learn" and _kw_hit(title, ["一次情報", "要約", "行動"]):
            base += 0.35
        elif intent == "plan" and _kw_hit(title, ["最小", "情報収集", "休息", "リファクタ", "テスト"]):
            base += 0.3

        if any(k in ql for k in ["雨", "降水", "umbrella", "forecast"]) and "傘" in title:
            base += 0.2

        if stakes >= 0.7 and _kw_hit(title, ["休息", "回復", "情報"]):
            base += 0.2

        by_title = bias.get(title.lower(), 0.0)
        by_fuzzy = adapt.fuzzy_bias_lookup(bias, title)
        by_id = bias.get(f"@id:{a.get('id')}", 0.0)
        bias_boost = max(by_title, by_fuzzy, by_id)
        base *= (1.0 + 0.3 * bias_boost)

        base *= (0.9 + 0.2 * max(0.0, min(1.0, telos_score)))

        a["score_raw"] = _safe_float(a.get("score"), 1.0)
        a["score"] = round(base, 4)


# ============================================================
# Simple QA モード
# ============================================================

def _detect_simple_qa(q: str) -> str | None:
    q = (q or "").strip()
    ql = q.lower()

    agi_block_keywords = [
        "agi",
        "ＡＧＩ",
        "veritas",
        "ヴェリタス",
        "ベリタス",
        "プロトagi",
        "proto-agi",
    ]
    if any(k in ql for k in agi_block_keywords):
        return None

    if len(q) > 25:
        return None

    qj = q.replace("　", " ")

    if re.search(r"^(今|いま).*(何時|なんじ)[？?]?$", qj):
        return "time"

    if re.search(r"^(今日|きょう).*(何曜日|なんようび)[？?]?$", qj):
        return "weekday"

    if re.search(r"^(今日|きょう).*(何日|なんにち|日付)[？?]?$", qj):
        return "date"

    if re.search(r"^what time is it[？?]?$", ql):
        return "time"
    if re.search(r"^what day is it[？?]?$", ql):
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

    decision = {
        "request_id": req_id,
        "chosen": chosen,
        "alternatives": [chosen],
        "evidence": evidence,
        "critique": [],
        "debate": [],
        "telos_score": telos_score,
        "fuji": {"status": "allow", "reasons": [], "violations": [], "risk": 0.05},
        "rsi_note": None,
        "summary": "simple QA モードで直接回答しました（DebateOS / WorldModel / AGI自己調整はスキップ）。",
        "description": (
            "「今何時？」「今日何曜日？」などの単純質問だったため、"
            "過去のAGIゴールやpersonaバイアスを無視して、システム時刻から直接回答しました。"
        ),
        "extras": extras,
    }
    decision.setdefault("meta", {})
    decision["meta"]["kind"] = "simple_qa"
    return decision


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
        answer_desc = (
            "knowledge_qa モードで web_search を試みましたが、有効な結果が見つかりませんでした。"
            f"error={search_res.get('error')}"
        )

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

    decision = {
        "request_id": req_id,
        "chosen": chosen,
        "alternatives": [chosen],
        "evidence": evidence,
        "critique": [],
        "debate": [],
        "telos_score": telos_score,
        "fuji": {"status": "allow", "reasons": [], "violations": [], "risk": 0.05},
        "rsi_note": None,
        "summary": "knowledge_qa モードで web_search の結果から直接回答しました（DebateOS / WorldModel / AGI自己調整はスキップ）。",
        "description": (
            "「○○とは？」「どこ？」「誰？」などの一般知識系の質問だったため、"
            "過去のAGIゴールやpersonaバイアスを無視して、web_search の上位結果から直接回答しました。"
        ),
        "extras": extras,
    }
    decision.setdefault("meta", {})
    decision["meta"]["kind"] = "knowledge_qa"
    return decision


# ============================================================
# decide 本体
# ============================================================

async def decide(
    context: Dict[str, Any],
    query: str,
    alternatives: List[Dict[str, Any]] | None,
    min_evidence: int = 1,
) -> Dict[str, Any]:
    """
    VERITAS kernel.decide:

      - 意図検出
      - Simple QA モード（time/date/weekday）はパイプラインをバイパス
      - knowledge_qa（簡易ナレッジ質問）バイパス
      - MemoryOS 要約を取り込み
      - env tools（web_search / github_search）実行（必要なときだけ）
      - ★ PlannerOS(plan_for_veritas_agi / code_change_plan) による steps 生成
      - Multi-Agent DebateOS による再評価
      - WorldModel（world.simulate）による「一手先の世界予測」
      - FUJI Gate による最終安全判定
      - Decision ログを MemoryOS にエピソード保存
      - world_state.json / doctor_report フック
      - ★ experiments / curriculum による「今日やる実験 / 今日の3タスク」生成
    """
    start_ts = time.time()   # ★ latency計測開始

    # ---- context を安全に固める & world_state を注入 ----
    ctx_raw: Dict[str, Any] = dict(context or {})
    user_id = ctx_raw.get("user_id") or "cli"

    ctx: Dict[str, Any] = world_model.inject_state_into_context(
        context=ctx_raw,
        user_id=user_id,
    )

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

    # --- MemoryOS 要約を取得（Planner には context 経由で伝える前提） ---
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
            "source": "MemoryOS.summarize_for_planner",
        }

    # Persona
    persona = adapt.load_persona()
    persona_bias: Dict[str, float] = adapt.clean_bias_weights(
        dict(persona.get("bias_weights") or {})
    )

    # WorldModel（将来の auto_adjust / UI 用の軽い simulate）
    world_sim = None
    if not fast_mode:
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
                "source": "world.simulate()",
            }
    else:
        extras["world"] = {
            "skipped": True,
            "reason": "fast_mode",
            "source": "world.simulate()",
        }

    # env tools
    env_logs: Dict[str, Any] = {}
    if not fast_mode:
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
    else:
        env_logs["skipped"] = {"reason": "fast_mode"}

    if env_logs:
        extras["env_tools"] = env_logs

    # intent（旧DecisionOS互換のため一応残す）
    intent = _detect_intent(q_text)

    # =======================================================
    # ★ Planner: code_change_plan 専用経路 or AGI Planner 経路
    # =======================================================

    alts: List[Dict[str, Any]] = list(alternatives or [])
    alts = _filter_alts_by_intent(intent, q_text, alts)

    planner_obj: Dict[str, Any] | None = None

    # ---- 1) code_change_plan モード（bench → generate_code_tasks 経路） ----
    if intent == "plan" and mode == "code_change_plan":
        bench_payload = (
            ctx.get("bench_payload")
            or ctx.get("bench")
            or {}
        )
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

                desc_parts = [
                    f"kind={kind}",
                    f"module={module}",
                ]
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
            extras["code_change_plan_error"] = (
                f"generate_code_tasks failed: {repr(e)[:120]}"
            )

    # ---- 2) 通常 / VERITAS-AGI モード → 新 PlannerOS を必ず使う ----
    if not alts:
        try:
            planner_obj = planner_core.plan_for_veritas_agi(
                context=ctx,
                query=q_text,
            )
            steps = planner_obj.get("steps") or []

            # Planner の steps を Debate 用 options にマッピング
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
            # Planner が死んだら、従来の intent ベース fallback を使う
            if not alts:
                alts = _gen_options_by_intent(intent)

    # Planner 情報を extras に格納
    if planner_obj is not None:
        extras["planner"] = planner_obj

    # ---- 最終的な alternatives 整形・スコアリング ----
    alts = _dedupe_alts(alts)
    _score_alternatives(intent, q_text, alts, telos_score, stakes, persona_bias)

    # =======================================================
    # DebateOS
    # =======================================================
    chosen: Dict[str, Any] | None = None

    if fast_mode:
        chosen = max(alts, key=lambda d: _safe_float(d.get("score"), 1.0))
        debate_logs.append(
            {
                "summary": "fast_mode のため DebateOS をスキップし、ローカルスコア最大案を採択しました。",
                "risk_delta": 0.0,
                "suggested_choice_id": chosen.get("id"),
                "source": "fast_mode_local",
            }
        )
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

            debate_logs.append(
                {
                    "summary": "Multi-Agent DebateOS により候補が評価されました。",
                    "risk_delta": 0.0,
                    "suggested_choice_id": chosen.get("id") if isinstance(chosen, dict) else None,
                    "source": debate_result.get("source", "openai_llm"),
                }
            )

            alts = _dedupe_alts(enriched_alts)

        except Exception as e:
            chosen = max(alts, key=lambda d: _safe_float(d.get("score"), 1.0))
            debate_logs.append(
                {
                    "summary": f"DebateOS フォールバック (例外: {repr(e)[:80]})",
                    "risk_delta": 0.0,
                    "suggested_choice_id": chosen.get("id"),
                    "source": "fallback",
                }
            )

    if chosen is None:
        chosen = {
            "id": f"debate_reject_all_{uuid.uuid4().hex[:8]}",
            "title": "全ての候補案がDebateOSにより却下されました",
            "description": (
                "質問内容と無関係、または安全性・目的適合性の観点から不適切と判断されたため、"
                "既存の候補からは何も選択していません。"
            ),
            "score": 0.0,
            "score_raw": 0.0,
            "verdict": "reject_all",
        }
        extras.setdefault("debate", {})
        extras["debate"]["reject_all"] = True

    if isinstance(world_sim, dict) and isinstance(chosen, dict):
        chosen["world"] = world_sim

    # Evidence（kernel 自身の evidence）
    evidence.append(
        {
            "source": "internal:kernel",
            "uri": None,
            "snippet": f"query='{q_text}' evaluated with {len(alts)} alternatives (mode={mode})",
            "confidence": 0.8,
        }
    )

    # =======================================================
    # ★ MemoryOS から episodic evidence を追加
    # =======================================================
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

    # 学習＋AGIゴール自己調整
    if not fast_mode:
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
                "world_progress": world_snap.get("progress")
                                   or world_snap.get("predicted_progress")
                                   or world_snap.get("base_progress"),
                "world_risk": world_snap.get("last_risk")
                               or world_snap.get("predicted_risk")
                               or world_snap.get("base_risk"),
                "value_ema": value_ema,
                "fuji_risk": fuji_risk,
            }

        except Exception as e:
            extras.setdefault("agi_goals", {})
            extras["agi_goals"]["error"] = repr(e)
    else:
        extras.setdefault("agi_goals", {})
        extras["agi_goals"]["skipped"] = {"reason": "fast_mode"}

    # =======================================================
    # ★ Decision ログを MemoryOS にエピソードとして保存
    # =======================================================
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

    # =======================================================
    # ★ metrics / world_state / doctor / experiments / curriculum
    # =======================================================
    latency_ms: int | None = None
    try:
        latency_ms = int((time.time() - start_ts) * 1000)
        extras.setdefault("metrics", {})
        extras["metrics"]["latency_ms"] = latency_ms
    except Exception as e:
        extras.setdefault("metrics", {})
        extras["metrics"]["error"] = f"latency_failed:{repr(e)[:60]}"

    # world_state.json 更新（decision history / progress）
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

    # doctor 自動実行（ctx.auto_doctor が False のときはスキップ）
    auto_doctor = ctx.get("auto_doctor", True)
    if auto_doctor:
        try:
            subprocess.Popen(
                [sys.executable, "-m", "veritas_os.scripts.doctor"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            extras.setdefault("doctor", {})
            extras["doctor"]["error"] = repr(e)

    # ---- 今日の「実験」と「カリキュラム」も extras にぶら下げる ----
    try:
        # ★ ここで初めて import（ローカル import なので循環しない）
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

    # =======================================================
    # レスポンス構築
    # =======================================================
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
        "summary": (
            "意図検出＋Simple QA / knowledge QA バイパス＋MemoryOS 要約＋env tools＋"
            "PlannerOS(plan_for_veritas_agi / code_change_plan)＋Multi-Agent DebateOS＋"
            "WorldModel予測＋FUJI Gate＋AGIゴール自己調整(auto_adjust_goals)＋"
            "Decision episodic logging＋world_state更新＋doctor自動実行＋"
            "experiments / curriculum による『今日やる実験と3タスク』の提示を行いました。"
        ),
        "description": (
            "与えられた選択肢がある場合はその中から選択し、無い場合は PlannerOS が steps を生成します。"
            "ローカル学習バイアスと Multi-Agent DebateOS により、徐々に“選択の癖”と安全性を反映します。"
            "WorldModel(world_state) を用いて、『この一手が世界にどう効きそうか』を軽く予測します。"
            "FUJI Gate で安全性を確認し、AGIゴール管理モジュール(auto_adjust_goals)で、"
            "progress / risk / telos に応じてゴール重みを自己調整します。"
            "mode=code_change_plan のときは、bench/world/doctor から生成したコード変更タスク群の中から、"
            "どれに着手すべきかを優先度付きで決定します。"
            "fast_mode=True または mode='fast' の場合、WorldModel / env_tools / DebateOS / auto_adjust をスキップし、"
            "ローカルスコアのみで高速に決定します。"
            "各 decision は MemoryOS にエピソードとして保存され、"
            "world_state.json や doctor_report の更新、および daily experiments / curriculum の提案に利用されます。"
        ),
        "extras": extras,
        "memory_evidence_count": memory_evidence_count,
        "memory_citations": extras.get("memory", {}).get("citations", []),
        "memory_used_count": memory_evidence_count,
        "meta": {
            "memory_evidence_count": memory_evidence_count,
        },
    }
