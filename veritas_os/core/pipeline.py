# veritas_os/api/pipeline.py など
from __future__ import annotations

import asyncio
import inspect
import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import Request

from . import (
    kernel as veritas_core,
    fuji as fuji_core,
    memory as mem,
    value_core,
    world as world_model,
    planner as planner_core,
    llm_client,
    reason as reason_core,
    debate as debate_core,
)
from veritas_os.logging.paths import LOG_DIR, DATASET_DIR, VAL_JSON, META_LOG
from veritas_os.logging.dataset_writer import (
    build_dataset_record,
    append_dataset_record,
)
from veritas_os.api.schemas import DecideRequest, DecideResponse
from veritas_os.api.evolver import load_persona
from veritas_os.tools.web_search import web_search
from veritas_os.logging.trust_log import append_trust_log, write_shadow_decide


# =========================================================
# Memory / MemoryModel 初期化
# =========================================================

MEM = mem  # 既存 MemoryOS KVS

try:
    from veritas_os.core.models import memory_model as memory_model_core

    MEM_VEC = getattr(memory_model_core, "MEM_VEC", None)
    MEM_CLF = getattr(memory_model_core, "MEM_CLF", None)

    if hasattr(memory_model_core, "predict_gate_label"):
        from veritas_os.core.models.memory_model import (  # type: ignore
            predict_gate_label,
        )
    else:
        def predict_gate_label(text: str) -> Dict[str, float]:
            return {"allow": 0.5}
except Exception:  # モデル無し環境での fallback
    MEM_VEC = None
    MEM_CLF = None

    def predict_gate_label(text: str) -> Dict[str, float]:
        return {"allow": 0.5}


# =========================================================
# 汎用ヘルパー
# =========================================================

async def call_core_decide(
    core_fn,
    *,
    context: Dict[str, Any],
    query: str,
    alternatives: List[Dict[str, Any]],
    min_evidence: int,
):
    """
    veritas_core.decide の呼び出しラッパ。
    シグネチャが多少変わっても動くように、inspect でパラメータを合わせる。
    """
    params = set(inspect.signature(core_fn).parameters.keys())
    kw: Dict[str, Any] = {}
    ctx = dict(context or {})

    # query を context にも埋める
    if "query" not in params and query:
        ctx.setdefault("query", query)
        ctx.setdefault("prompt", query)
        ctx.setdefault("text", query)

    if "ctx" in params:
        kw["ctx"] = ctx
    elif "context" in params:
        kw["context"] = ctx

    if "options" in params:
        kw["options"] = alternatives or []
    elif "alternatives" in params:
        kw["alternatives"] = alternatives or []

    if "min_evidence" in params:
        kw["min_evidence"] = min_evidence
    elif "k" in params:
        kw["k"] = min_evidence
    elif "top_k" in params:
        kw["top_k"] = min_evidence

    if "query" in params:
        kw["query"] = query

    if inspect.iscoroutinefunction(core_fn):
        return await core_fn(**kw)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: core_fn(**kw))


def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "y", "on")
    return False


def _to_float_or(v: Any, default: float) -> float:
    if v in (None, "", "null", "None"):
        return default
    try:
        return float(v)
    except Exception:
        return default


def _to_dict(o: Any) -> Dict[str, Any]:
    if isinstance(o, dict):
        return o
    if hasattr(o, "model_dump"):
        return o.model_dump(exclude_none=True)  # type: ignore
    if hasattr(o, "dict"):
        return o.dict()  # type: ignore
    return {}


def _norm_alt(o: Any) -> Dict[str, Any]:
    d = _to_dict(o) or {}
    if "title" not in d and "text" in d:
        d["title"] = d.pop("text")
    d.setdefault("title", "")
    d["description"] = (d.get("description") or d.get("text") or "")
    d["score"] = _to_float_or(d.get("score", 1.0), 1.0)
    d["score_raw"] = _to_float_or(d.get("score_raw", d["score"]), d["score"])
    d["id"] = str(d.get("id") or uuid4().hex)
    return d


def _mem_model_path() -> str:
    try:
        from veritas_os.core.models import memory_model as mm

        if hasattr(mm, "MODEL_FILE"):
            return str(mm.MODEL_FILE)
        if hasattr(mm, "MODEL_PATH"):
            return str(mm.MODEL_PATH)
    except Exception:
        pass
    return ""


def _allow_prob(text: str) -> float:
    d = predict_gate_label(text)
    return float(d.get("allow", 0.0))


def _clip01(x: float) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except Exception:
        return 0.0


def _load_valstats() -> Dict[str, Any]:
    try:
        with open(VAL_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "ema": 0.5,
            "alpha": 0.2,
            "n": 0,
            "history": [],
        }


def _save_valstats(d: Dict[str, Any]) -> None:
    with open(VAL_JSON, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


# =========================================================
# メイン: 決定パイプライン
# =========================================================

async def run_decide_pipeline(
    req: DecideRequest,
    request: Request,
) -> Dict[str, Any]:
    """
    /v1/decide の中身を HTTP から切り離した“頭脳側パイプライン”。
    FastAPI 側はこれを呼んで payload(dict) を受け取り、そのまま返すだけ。
    """
    started_at = time.time()
    body = req.model_dump()

    # ---------- SAFE INIT ----------
    raw: Dict[str, Any] = {}
    evidence: List[Any] = []
    critique: List[Any] = []
    debate: List[Any] = []
    telos: float = 0.0
    fuji_dict: Dict[str, Any] = {}
    alternatives: List[Dict[str, Any]] = []
    extras_payload: Dict[str, Any] = {
        "safe_instructions": [],
        "redactions": [],
        "masked_example": None,
    }
    modifications: List[Any] = []
    response_extras: Dict[str, Any] = {"metrics": {}}

    # ---------- Query / Context / user_id ----------
    context = body.get("context") or {}
    raw_query = body.get("query") or context.get("query") or ""
    if not isinstance(raw_query, str):
        raw_query = str(raw_query)
    query = raw_query.strip()
    user_id = context.get("user_id") or body.get("user_id") or "anon"

    # ---------- fast モード ----------
    fast_from_body = _to_bool(body.get("fast"))
    fast_from_ctx = _to_bool(context.get("fast")) or (
        isinstance(context.get("mode"), str)
        and context.get("mode").lower() == "fast"
    )
    fast_from_query = _to_bool(request.query_params.get("fast"))
    fast_mode = fast_from_body or fast_from_ctx or fast_from_query

    if fast_mode:
        context["fast"] = True
        if not context.get("mode"):
            context["mode"] = "fast"
        body["fast"] = True

    # === WorldOS: context に world_state を注入 ===
    try:
        context = world_model.inject_state_into_context(context, user_id)
        body["context"] = context
    except Exception as e:
        print("[WorldOS] inject_state_into_context skipped:", e)

    # VERITAS / AGI 系クエリ判定
    qlower = query.lower()
    is_veritas_query = any(
        k in qlower for k in ["veritas", "agi", "protoagi", "プロトagi", "veritasのagi化"]
    )

    # -------- PlannerOS ----------
    try:
        from veritas_os.core.planner import plan_for_veritas_agi

        plan: Dict[str, Any] = plan_for_veritas_agi(
            context=context,
            query=query,
        )
        print(
            f"[PlannerOS] steps={len(plan.get('steps', []))}, "
            f"source={plan.get('source')}"
        )
    except Exception as e:
        print("[PlannerOS] skipped:", e)
        plan = {"steps": [], "raw": None, "source": "fallback"}

    response_extras["planner"] = {
        "steps": plan.get("steps", []),
        "raw": plan.get("raw"),
        "source": plan.get("source"),
    }

    # ---------- MemoryOS: prior / retrieval ----------
    recent_logs = mem.recent(user_id, limit=20)
    similar = [
        r
        for r in recent_logs
        if query and query[:8] in str(((r.get("value") or {}).get("query") or ""))
    ]
    prior_scores: Dict[str, float] = {}
    for r in similar:
        c = (r.get("value") or {}).get("chosen") or {}
        t = c.get("title") or c.get("id")
        if t:
            prior_scores[t] = prior_scores.get(t, 0.0) + 1.0

    request_id = body.get("request_id") or secrets.token_hex(16)
    min_ev = int(body.get("min_evidence") or 1)

    # retrieval
    mem_hits_raw: Any = None
    retrieved: List[Dict[str, Any]] = []

    try:
        if query:
            mem_hits_raw = MEM.search(
                query,
                k=6,
                kinds=["semantic", "skills", "episodic"],
                min_sim=0.0,
                user_id=user_id,
            )

        flat_hits: List[Dict[str, Any]] = []

        if isinstance(mem_hits_raw, dict):
            for kind, hits in mem_hits_raw.items():
                if not isinstance(hits, list):
                    continue
                for h in hits:
                    if not isinstance(h, dict):
                        continue
                    h = dict(h)
                    h.setdefault("kind", kind)
                    flat_hits.append(h)

        elif isinstance(mem_hits_raw, list):
            for h in mem_hits_raw:
                if isinstance(h, dict):
                    flat_hits.append(h)

        for h in flat_hits:
            text = (
                h.get("text")
                or (h.get("value") or {}).get("text")
                or (h.get("value") or {}).get("query")
                or ""
            )
            if not text:
                continue

            kind = (
                h.get("kind")
                or (h.get("meta") or {}).get("kind")
                or "episodic"
            )

            retrieved.append(
                {
                    "id": h.get("id") or h.get("key"),
                    "kind": kind,
                    "text": text,
                    "score": float(h.get("score", 0.5)),
                }
            )

        retrieved.sort(key=lambda r: r.get("score", 0.0), reverse=True)
        top_hits = retrieved[:3]

        metrics = response_extras.setdefault("metrics", {})
        metrics["mem_hits"] = len(retrieved)
        metrics["memory_evidence_count"] = len(top_hits)

        for r in top_hits:
            snippet = r["text"]
            if len(snippet) > 200:
                snippet = snippet[:197] + "..."

            evidence.append(
                {
                    "source": f"memory:{r.get('kind','')}",
                    "uri": r.get("id"),
                    "snippet": snippet,
                    "confidence": max(0.3, min(1.0, r.get("score", 0.5))),
                }
            )

        print(
            f"[AGI-Retrieval] Added memory evidences: {len(top_hits)} "
            f"(raw_hits={len(retrieved)})"
        )

        if retrieved:
            cited_ids = [str(r.get("id")) for r in top_hits if r.get("id")]
            if cited_ids:
                ts = datetime.utcnow().isoformat() + "Z"
                mem.put(
                    user_id,
                    key=f"memory_use_{ts}",
                    value={
                        "used": True,
                        "query": query,
                        "citations": cited_ids,
                        "timestamp": ts,
                    },
                )
                mem.add_usage(user_id, cited_ids)

    except Exception as e:
        print("[AGI-Retrieval] memory retrieval error:", repr(e))
        response_extras.setdefault("metrics", {})
        response_extras["metrics"].setdefault("mem_hits", 0)
        response_extras["metrics"].setdefault("memory_evidence_count", 0)
        response_extras.setdefault("env_tools", {})
        response_extras["env_tools"]["memory_error"] = repr(e)

    response_extras.setdefault("metrics", {})
    response_extras["metrics"]["mem_hits"] = len(retrieved)

    # memory citations (extras)
    memory_citations_list: List[Dict[str, Any]] = []
    for r in retrieved[:10]:
        cid = r.get("id")
        if cid:
            memory_citations_list.append(
                {
                    "id": cid,
                    "kind": r.get("kind"),
                    "score": float(r.get("score", 0.0)),
                }
            )

    response_extras["memory_citations"] = memory_citations_list
    response_extras["memory_used_count"] = len(memory_citations_list)

    # ---------- WebSearch ----------
    try:
        if any(k in qlower for k in ["agi", "research", "論文", "paper"]):
            ws = web_search(query, max_results=5)
            response_extras["web_search"] = ws

            if ws.get("ok") and ws.get("results"):
                for item in ws["results"][:3]:
                    evidence.append(
                        {
                            "source": "web",
                            "uri": item.get("url"),
                            "snippet": item.get("snippet") or item.get("title") or "",
                            "confidence": 0.7,
                        }
                    )
    except Exception as e:
        print("[WebSearch] skipped:", e)

    # ---------- options 正規化 ----------
    input_alts = body.get("options") or body.get("alternatives") or []
    if not isinstance(input_alts, list):
        input_alts = []
    input_alts = [_norm_alt(a) for a in input_alts]

    # VERITAS / AGI クエリ向け alternatives (Planner → alt)
    if not input_alts and is_veritas_query:
        step_alts: List[Dict[str, Any]] = []
        for i, st in enumerate(plan.get("steps") or [], 1):
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

        if step_alts:
            input_alts = step_alts
        else:
            input_alts = [
                _norm_alt(
                    {
                        "id": "veritas_mvp_demo",
                        "title": "MVPデモを最短で見せられる形にする",
                        "description": "Swagger/CLI で実際に /v1/decide を叩きながら説明できる30〜60秒のデモを作る。",
                    }
                ),
                _norm_alt(
                    {
                        "id": "veritas_report",
                        "title": "技術監査レポートを仕上げる",
                        "description": "VERITAS 技術監査レポートを第三者が読めるレベルにブラッシュアップする。",
                    }
                ),
                _norm_alt(
                    {
                        "id": "veritas_spec_sheet",
                        "title": "MVP仕様書を1枚にまとめる",
                        "description": "CLI/API・FUJI・DebateOS・MemoryOS の流れを1枚の図＋テキストに整理する。",
                    }
                ),
                _norm_alt(
                    {
                        "id": "veritas_demo_script",
                        "title": "第三者向けデモ台本を作る",
                        "description": "どの順番で画面を見せ、何を喋るかのシナリオを作成する。",
                    }
                ),
            ]

    # 過去傾向でスコア微調整（最大+5%）
    if prior_scores:
        max_prior = max(prior_scores.values())
        if max_prior > 0:
            for d in input_alts:
                title = d.get("title") or d.get("id")
                boost = prior_scores.get(title, 0.0) / max_prior
                d["score_raw"] = d.get("score_raw", d.get("score", 1.0))
                d["score"] = float(d.get("score", 1.0)) * (1.0 + 0.05 * boost)

    # 過去の plan → alternatives
    try:
        plan_alts = []
        for r in recent_logs:
            v = r.get("value") or {}
            if v.get("kind") != "plan":
                continue
            if query and query[:10] not in str(v.get("query") or ""):
                continue

            p = v.get("planner") or {}
            steps = p.get("steps") or []
            if not steps:
                continue

            first = steps[0]
            step_title = first.get("title") or first.get("name") or "過去プランの継続"

            alt = _norm_alt(
                {
                    "title": f"過去プランを継続: {step_title}",
                    "description": f"以前の決定ログのplanを引き継ぐ: {v.get('query')}",
                    "score": 0.8,
                    "meta": {
                        "source": "plan",
                        "origin_query": v.get("query"),
                    },
                }
            )
            plan_alts.append(alt)

        if plan_alts and not input_alts:
            input_alts = plan_alts

    except Exception as e:
        print("[MemoryOS] plan→alternatives skipped:", e)

    # episodic メモリから alternatives
    try:
        mem_alts: List[Dict[str, Any]] = []

        episodic_hits = [
            r
            for r in (retrieved or [])
            if isinstance(r, dict) and r.get("kind") == "episodic"
        ]

        for h in episodic_hits:
            txt = (h.get("text") or "").strip()
            if not txt:
                continue

            title = ""

            if "[chosen]" in txt:
                try:
                    _, tail = txt.split("[chosen]", 1)
                    title = tail.split("\n", 1)[0].strip(" :　")
                except Exception:
                    pass

            if not title and "chosen:" in txt:
                try:
                    _, tail = txt.split("chosen:", 1)
                    title = tail.split("|", 1)[0].strip()
                except Exception:
                    pass

            if (not title) or (title.strip().lower() == "none"):
                title = txt[:40]

            alt = _norm_alt(
                {
                    "title": title,
                    "description": f"過去の決定ログから復元: {title}",
                    "score": float(h.get("score", 0.8)),
                    "meta": {
                        "source": "episodic",
                        "memory_id": h.get("id"),
                    },
                }
            )
            mem_alts.append(alt)

        if mem_alts:
            input_alts.extend(mem_alts)

    except Exception as e:
        print("[episodic] alternative generation failed:", e)

    # ---------- core 呼び出し ----------
    try:
        raw = await call_core_decide(
            core_fn=veritas_core.decide,
            context=context,
            query=query,
            alternatives=input_alts,
            min_evidence=min_ev,
        )
    except Exception as e:
        print("[decide] core error:", e)
        raw = {}

    # ---------- 吸収 ----------
    if isinstance(raw, dict) and raw:
        raw_evi = raw.get("evidence")
        if isinstance(raw_evi, list):
            evidence.extend(raw_evi)

        critique = raw.get("critique") or critique
        debate = raw.get("debate") or debate
        telos = float(raw.get("telos_score") or telos)
        fuji_dict = raw.get("fuji") or fuji_dict

        alts_from_core = raw.get("alternatives") or raw.get("options") or []
        if isinstance(alts_from_core, list):
            alternatives = [_norm_alt(a) for a in alts_from_core]

        if isinstance(raw.get("extras"), dict):
            extras_payload.update(raw["extras"])

    # fallback alternatives
    alts = alternatives
    if not alts:
        alts = [
            _norm_alt({"title": "最小ステップで前進する"}),
            _norm_alt({"title": "情報収集を優先する"}),
            _norm_alt({"title": "今日は休息に充てる"}),
        ]
    alts = veritas_core._dedupe_alts(alts)

    # --- WorldModel boost ---
    try:
        boosted = []
        uid_for_world = (context or {}).get("user_id") or user_id or "anon"
        for d in alts:
            sim = world_model.simulate(
                user_id=uid_for_world,
                query=query,
                chosen=d,
            )
            d["world"] = sim
            micro = max(
                0.0,
                min(
                    0.03,
                    0.02 * sim.get("utility", 0.0)
                    + 0.01 * sim.get("confidence", 0.5),
                ),
            )
            d["score"] = float(d.get("score", 1.0)) * (1.0 + micro)
            boosted.append(d)
        alts = boosted
    except Exception as e:
        print("[WorldModelOS] skip:", e)

    # --- MemoryModel boost ---
    try:
        response_extras.setdefault("metrics", {})
        if MEM_VEC is not None and MEM_CLF is not None:
            response_extras["metrics"]["mem_model"] = {
                "applied": True,
                "reason": "loaded",
                "path": _mem_model_path(),
                "classes": getattr(MEM_CLF, "classes_", []).tolist()
                if hasattr(MEM_CLF, "classes_")
                else None,
            }

            for d in alts:
                text = (d.get("title") or "") + " " + (d.get("description") or "")
                p_allow = _allow_prob(text)
                base = float(d.get("score", 1.0))
                d["score_raw"] = float(d.get("score_raw", base))
                d["score"] = base * (1.0 + 0.10 * p_allow)
        else:
            response_extras["metrics"]["mem_model"] = {
                "applied": False,
                "reason": "model_not_loaded",
                "path": _mem_model_path(),
            }
    except Exception as e:
        response_extras.setdefault("metrics", {})
        response_extras["metrics"]["mem_model"] = {
            "applied": False,
            "error": str(e),
            "path": _mem_model_path(),
        }

    # --- chosen 決定（pre-Debate） ---
    chosen = raw.get("chosen") if isinstance(raw, dict) else {}
    if not isinstance(chosen, dict) or not chosen:
        try:
            def _choice_key(d: Dict[str, Any]) -> float:
                w = (d.get("world") or {}).get("utility")
                try:
                    return float(w)
                except Exception:
                    return float(d.get("score", 1.0))

            chosen = max(alts, key=_choice_key)
        except Exception:
            chosen = alts[0] if alts else {}

    # ---------- DebateOS ----------
    debate_result: Dict[str, Any] = {}
    try:
        debate_result = debate_core.run_debate(
            query=query,
            options=alts,
            context={
                "user_id": user_id,
                "stakes": (context or {}).get("stakes"),
                "telos_weights": (context or {}).get("telos_weights"),
            },
        )
    except Exception as e:
        print("[DebateOS] skipped:", e)
        debate_result = {}

    if isinstance(debate_result, dict):
        deb_opts = debate_result.get("options") or []
        if isinstance(deb_opts, list) and deb_opts:
            # run_debate が元 options をマージした enriched options を返す前提
            alts = deb_opts

        deb_chosen = debate_result.get("chosen")
        if isinstance(deb_chosen, dict) and deb_chosen:
            chosen = deb_chosen

        # 互換用: debate は「options のリスト」として保持
        if isinstance(deb_opts, list):
            debate = deb_opts

        # extras に Debate 情報を保存（raw はフル JSON）
        try:
            response_extras.setdefault("debate", {})
            response_extras["debate"].update(
                {
                    "source": debate_result.get("source"),
                    "raw": debate_result.get("raw"),
                }
            )
        except Exception as e:
            print("[DebateOS] extras attach skipped:", e)

        # 却下候補数から簡易 risk_delta を計算して 1件目に埋め込む
        try:
            rejected_cnt = 0
            for o in deb_opts:
                v = str(o.get("verdict") or "").strip()
                if v in ("却下", "reject", "Rejected", "NG"):
                    rejected_cnt += 1
            if rejected_cnt > 0 and deb_opts:
                # 最大 +0.20 まで
                risk_delta = min(0.20, 0.05 * rejected_cnt)
                deb_opts[0]["risk_delta"] = risk_delta
        except Exception as e:
            print("[DebateOS] risk_delta heuristic skipped:", e)

    # ---------- FUJI 事前チェック ----------
    try:
        fuji_pre = fuji_core.validate_action(query, context)
    except Exception as e:
        print("[fuji] error:", e)
        fuji_pre = {
            "status": "allow",
            "reasons": [],
            "violations": [],
            "risk": 0.0,
        }

    status_map = {
        "ok": "allow",
        "allow": "allow",
        "pass": "allow",
        "modify": "modify",
        "block": "rejected",
        "deny": "rejected",
        "rejected": "rejected",
    }
    fuji_pre["status"] = status_map.get(
        (fuji_pre.get("status") or "allow").lower(), "allow"
    )
    fuji_dict = {
        **(fuji_dict if isinstance(fuji_dict, dict) else {}),
        **fuji_pre,
    }

    fuji_status = fuji_dict.get("status", "allow")
    risk_val = float(fuji_dict.get("risk", 0.0))
    reasons_list = fuji_dict.get("reasons", []) or []
    viols = fuji_dict.get("violations", []) or []
    evidence.append(
        {
            "source": "internal:fuji",
            "uri": None,
            "snippet": (
                f"[FUJI pre] status={fuji_status}, risk={risk_val}, "
                f"reasons={'; '.join(reasons_list) if reasons_list else '-'}, "
                f"violations={', '.join(viols) if viols else '-'}"
            ),
            "confidence": 0.9
            if fuji_status in ("modify", "rejected")
            else 0.8,
        }
    )

    # ---------- ValueCore ----------
    try:
        vc = value_core.evaluate(query, context or {})
        values_payload = {
            "scores": vc.scores,
            "total": vc.total,
            "top_factors": vc.top_factors,
            "rationale": vc.rationale,
        }
    except Exception as e:
        print("[value_core] evaluation error:", e)
        values_payload = {
            "scores": {},
            "total": 0.0,
            "top_factors": [],
            "rationale": "evaluation failed",
        }

    # ---- EMA 読込 ----
    value_ema = 0.5
    try:
        if VAL_JSON.exists():
            vs = json.load(open(VAL_JSON, encoding="utf-8"))
            value_ema = float(vs.get("ema", 0.5))
    except Exception as e:
        print("[value_ema] load skipped:", e)

    BOOST_MAX = float(os.getenv("VERITAS_VALUE_BOOST_MAX", "0.05"))
    boost = (value_ema - 0.5) * 2.0  # -1..+1
    boost = max(-1.0, min(1.0, boost)) * BOOST_MAX

    def _apply_boost(arr: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for d in arr:
            try:
                s = float(d.get("score", 1.0))
                d["score_raw"] = float(d.get("score_raw", s))
                d["score"] = max(0.0, s * (1.0 + boost))
            except Exception:
                pass
            out.append(d)
        return out

    input_alts = _apply_boost(input_alts)
    alts = _apply_boost(alts)

    # FUJI risk × EMA
    RISK_EMA_WEIGHT = float(os.getenv("VERITAS_RISK_EMA_WEIGHT", "0.15"))
    effective_risk = float(fuji_dict.get("risk", 0.0)) * (
        1.0 - RISK_EMA_WEIGHT * value_ema
    )
    effective_risk = max(0.0, min(1.0, effective_risk))

    BASE_TELOS_TH = 0.55
    TELOS_EMA_DELTA = float(os.getenv("VERITAS_TELOS_EMA_DELTA", "0.10"))
    telos_threshold = BASE_TELOS_TH - TELOS_EMA_DELTA * (value_ema - 0.5) * 2.0
    telos_threshold = max(0.35, min(0.75, telos_threshold))

    # ---- world_state snapshot ----
    world_state = (
        (context or {}).get("world_state")
        or (context or {}).get("world")
        or {}
    )

    # world.utility 生成
    try:
        v_total = _clip01(values_payload.get("total", 0.5))
        t_val = _clip01(telos)
        r_val = _clip01(effective_risk)

        for d in alts:
            base = _clip01(d.get("score", 0.0))
            util = base
            util *= (0.5 + 0.5 * v_total)
            util *= (1.0 - r_val)
            util *= (0.5 + 0.5 * t_val)
            util = _clip01(util)

            d.setdefault("world", {})
            d["world"]["utility"] = util

        if alts:
            avg_u = sum(
                (d.get("world") or {}).get("utility", 0.0) for d in alts
            ) / len(alts)
        else:
            avg_u = 0.0

        response_extras.setdefault("metrics", {})
        response_extras["metrics"]["avg_world_utility"] = round(
            float(avg_u), 4
        )

    except Exception as e:
        print("[world.utility] skipped:", e)

    # ---------- gate 決定 ----------
    risk = float(fuji_dict.get("risk", 0.0))
    decision_status, rejection_reason = "allow", None
    modifications = fuji_dict.get("modifications") or []

    # DebateOS の risk_delta を統合
    try:
        if isinstance(debate, list) and debate:
            deb = debate[0]
            delta = float(deb.get("risk_delta", 0.0))

            new_risk = risk + delta
            new_risk = max(0.0, min(1.0, new_risk))

            print(
                f"[Debate→FUJI] risk {risk:.3f} → {new_risk:.3f} "
                f"(delta={delta:+.3f})"
            )
            risk = new_risk

    except Exception as e:
        print("[Debate→FUJI] merge failed:", e)

    # FUJI × World utility 連携（effective_risk 再調整）
    try:
        if alts:
            topw = max(
                alts, key=lambda d: float(d.get("score", 1.0))
            ).get("world", {})
            utility = float(topw.get("utility", 0.0))
            conf = float(topw.get("confidence", 0.5))
            penalty = max(0.0, -utility) * 0.05 * conf
            effective_risk = max(
                0.0, min(1.0, risk + penalty)
            )
            print(
                f"[RiskTune] effective_risk tuned → "
                f"{effective_risk:.3f}"
            )
    except Exception as e:
        print("[RiskTune] skip:", e)

    if fuji_dict.get("status") == "modify":
        modifications = fuji_dict.get("modifications") or []
    elif fuji_dict.get("status") == "rejected":
        decision_status = "rejected"
        rejection_reason = "FUJI gate: " + ", ".join(
            fuji_dict.get("reasons", []) or ["policy_violation"]
        )
        chosen, alts = {}, []
    elif effective_risk >= 0.90 and telos < telos_threshold:
        decision_status = "rejected"
        rejection_reason = (
            f"FUJI gate: high risk ({effective_risk:.2f}) & "
            f"low telos (<{telos_threshold:.2f})"
        )
        chosen, alts = {}, []

    # --- Value learning: EMA 更新 ---
    try:
        valstats = _load_valstats()
        alpha = float(valstats.get("alpha", 0.2))
        ema_prev = float(valstats.get("ema", 0.5))
        n_prev = int(valstats.get("n", 0))
        v_val = float(values_payload.get("total", 0.5))

        ema_new = (1.0 - alpha) * ema_prev + alpha * v_val
        hist = valstats.get("history", [])
        hist.append(
            {
                "ts": datetime.utcnow().isoformat() + "Z",
                "ema": ema_new,
                "value": v_val,
            }
        )
        hist = hist[-1000:]

        valstats.update(
            {"ema": ema_new, "n": n_prev + 1, "last": v_val, "history": hist}
        )
        _save_valstats(valstats)

        values_payload["ema"] = round(ema_new, 4)

    except Exception as e:
        print("[value-learning] skip:", e)

    # ----- extras マージ -----
    try:
        prev_extras = dict(((raw or {}).get("extras") or {}))
    except Exception:
        prev_extras = {}

    try:
        metrics = {}
        metrics.update(prev_extras.get("metrics") or {})
        metrics.update(response_extras.get("metrics") or {})
        metrics.update(
            {
                "alts_count": len(alts),
                "has_evidence": bool(evidence),
                "value_ema": round(value_ema, 4),
                "effective_risk": round(effective_risk, 4),
                "telos_threshold": round(telos_threshold, 3),
            }
        )

        merged = dict(prev_extras)
        merged.update(response_extras)
        merged["metrics"] = metrics
        response_extras = merged
    except Exception:
        response_extras.setdefault("metrics", {})
        response_extras["metrics"].update(
            {
                "alts_count": len(alts),
                "has_evidence": bool(evidence),
            }
        )

    # PlannerOS の結果を extras に格納（最終版）
    try:
        response_extras["planner"] = plan
    except Exception as e:
        print("[PlannerOS] extras attach skipped:", e)

    # ----- metrics 追記: latency_ms / mem_evidence_count -----
    try:
        duration_ms = int((time.time() - started_at) * 1000)

        mem_evi_cnt = 0
        for ev in (evidence or []):
            src = str(ev.get("source", "") or "")
            if src.startswith("memory"):
                mem_evi_cnt += 1

        response_extras.setdefault("metrics", {})
        response_extras["metrics"].update(
            {
                "latency_ms": duration_ms,
                "mem_evidence_count": mem_evi_cnt,
            }
        )
    except Exception as e:
        print("[metrics] latency/memory_evidence skipped:", e)

    # MemoryOS retrieval メタ
    try:
        mem_result = {
            "query": query,
            "context": context,
            "user_id": (context or {}).get("user_id", "unknown"),
        }
        response_extras["memory_meta"] = mem_result
    except Exception as e:
        print("[MemoryOS ERROR]", e)

    # ---------- Episodic / Decision Memory logging ----------
    try:
        uid_mem = (context or {}).get("user_id") or user_id or "anon"
        ts = datetime.utcnow().isoformat() + "Z"

        episode_text = "\n".join(
            [
                f"[query] {query}",
                f"[chosen] {(chosen or {}).get('title') or str(chosen)}",
                f"[decision_status] {decision_status}",
                f"[risk] {float(fuji_dict.get('risk', 0.0)):.3f}",
            ]
        )

        mem.put(
            uid_mem,
            key=f"decision_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            value={
                "kind": "decision",
                "query": query,
                "alternatives": alts,
                "chosen": chosen,
                "values_total": float(values_payload.get("total", 0.0)),
                "gate_risk": float(fuji_dict.get("risk", 0.0)),
                "decision_status": decision_status,
                "telos_score": float(telos),
                "timestamp": ts,
            },
        )

        mem.put(
            uid_mem,
            key=f"episode_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            value={
                "kind": "episodic",
                "text": episode_text,
                "tags": ["episode", "decide", "veritas"],
                "meta": {
                    "user_id": uid_mem,
                    "request_id": request_id,
                    "fuji_risk": float(fuji_dict.get("risk", 0.0)),
                    "decision_status": decision_status,
                    "telos_score": float(telos),
                    "ts": ts,
                },
            },
        )

        print(f"[MemoryOS] episodic & decision saved for {uid_mem}")

    except Exception as e:
        print("[MemoryOS] episodic save failed:", e)

    # ---------- レスポンス dict 組み立て ----------
    res = {
        "request_id": request_id,
        "chosen": chosen,
        "alternatives": alts,
        "options": list(alts),
        "evidence": evidence,
        "critique": critique,
        "debate": debate,
        "telos_score": telos,
        "fuji": fuji_dict,
        "rsi_note": raw.get("rsi_note") if isinstance(raw, dict) else None,
        "extras": response_extras,
        "gate": {
            "risk": effective_risk,
            "telos_score": telos,
            "decision_status": decision_status,
            "reason": rejection_reason,
            "modifications": modifications,
        },
        "values": values_payload,
        "persona": load_persona(),
        "version": os.getenv("VERITAS_API_VERSION", "veritas-api 1.x"),
        "evo": raw.get("evo") if isinstance(raw, dict) else None,
        "decision_status": decision_status,
        "rejection_reason": rejection_reason,
        "memory_citations": response_extras.get("memory_citations", []),
        "memory_used_count": response_extras.get("memory_used_count", 0),
        "plan": plan,
        "planner": response_extras.get("planner", plan),
        "query": query,
    }

    # ---------- 監査ログ ----------
    try:
        fuji_safe = fuji_dict if isinstance(fuji_dict, dict) else {}

        audit_entry = {
            "request_id": request_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "context": context,
            "query": query,
            "chosen": chosen,
            "telos_score": float(telos),
            "fuji": fuji_safe,
            "gate_status": fuji_safe.get("status", "n/a"),
            "gate_risk": float(fuji_safe.get("risk", 0.0)),
            "gate_total": float(values_payload.get("total", 0.0)),
            "plan_steps": len(plan.get("steps", [])) if isinstance(plan, dict) else 0,
        }

        append_trust_log(audit_entry)
        write_shadow_decide(request_id, body, chosen, telos, fuji_dict)

    except Exception as e:
        print("[audit] log write skipped:", repr(e))

    # ---------- 型保証 ----------
    try:
        payload = DecideResponse.model_validate(res).model_dump()
    except Exception as e:
        print("[model] decide response coerce:", e)
        payload = res

    # ---------- ReasonOS 反省 & Value EMA 微調整 ----------
    try:
        reflection = reason_core.reflect(
            {
                "query": query,
                "chosen": payload.get("chosen", {}),
                "gate": payload.get("gate", {}),
                "values": payload.get("values", {}),
            }
        )

        vs_path = VAL_JSON
        valstats2: Dict[str, Any] = {}
        if vs_path.exists():
            valstats2 = json.load(open(vs_path, encoding="utf-8"))
        ema2 = float(valstats2.get("ema", 0.5))
        ema2 = max(
            0.0,
            min(1.0, ema2 + float(reflection.get("next_value_boost", 0.0))),
        )
        valstats2["ema"] = round(ema2, 4)
        json.dump(
            valstats2,
            open(vs_path, "w", encoding="utf-8"),
            ensure_ascii=False,
            indent=2,
        )

        try:
            try:
                nv = float(reflection.get("next_value_boost", 0.0))
            except Exception:
                nv = 0.0

            META_LOG.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "created_at": datetime.utcnow().isoformat() + "Z",
                "request_id": request_id,
                "next_value_boost": nv,
                "value_ema": ema2,
                "source": "reason_core",
            }
            with open(META_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e2:
            print("[ReasonOS] meta_log append skipped:", e2)

        try:
            tmpl = await reason_core.generate_reflection_template(
                query=query,
                chosen=payload.get("chosen", {}),
                gate=payload.get("gate", {}),
                values=payload.get("values", {}),
                planner=payload.get("planner") or payload.get("plan"),
            )
            if tmpl:
                response_extras.setdefault("reason_templates", [])
                response_extras["reason_templates"].append(tmpl)
                payload["extras"] = response_extras
        except Exception as e2:
            print("[ReasonOS] reflection_template failed:", e2)

        try:
            llm_reason = reason_core.generate_reason(
                query=query,
                planner=payload.get("planner") or payload.get("plan"),
                values=payload.get("values"),
                gate=payload.get("gate"),
                context=context,
            )

            note_text = ""
            if isinstance(llm_reason, dict):
                note_text = llm_reason.get("text") or ""
            elif isinstance(llm_reason, str):
                note_text = llm_reason

            if not note_text:
                tips = reflection.get("improvement_tips") or []
                note_text = " / ".join(tips) if tips else "自動反省メモはありません。"

            payload["reason"] = {
                "note": note_text,
                "next_value_boost": reflection.get("next_value_boost", 0.0),
                "reflection": reflection,
                "llm": llm_reason,
            }

        except Exception as e2:
            print("[ReasonOS] LLM reason failed:", e2)
            tips = reflection.get("improvement_tips") or []
            note_text = " / ".join(tips) if tips else "reflection only."
            payload["reason"] = {
                "note": note_text,
                "next_value_boost": reflection.get("next_value_boost", 0.0),
                "reflection": reflection,
            }

    except Exception as e:
        print("[ReasonOS] final fallback failed:", e)
        payload["reason"] = {"note": "reflection/LLM both failed"}

    # ---------- Planner → MemoryOS 保存 ----------
    try:
        uid_plan = (context or {}).get("user_id") or user_id or "anon"
        extras_pl = payload.get("extras") or {}
        planner_dict = extras_pl.get("planner") or {}

        if planner_dict:
            mem.put(
                uid_plan,
                key=f"plan_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                value={
                    "kind": "plan",
                    "query": query,
                    "chosen": payload.get("chosen"),
                    "planner": planner_dict,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
            )

            steps = planner_dict.get("steps") or []
            if steps:
                step_lines = []
                for i, st in enumerate(steps, 1):
                    title = (
                        st.get("title")
                        or st.get("name")
                        or f"Step {i}"
                    )
                    step_lines.append(f"{i}. {title}")
                plan_text = "\n".join(step_lines)

                mem.put(
                    uid_plan,
                    key=f"plan_text_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                    value={
                        "kind": "plan_text",
                        "query": query,
                        "text": plan_text,
                        "tags": ["plan", "veritas", "decide"],
                        "timestamp": datetime.utcnow().isoformat()
                        + "Z",
                    },
                )

            print(
                f"[MemoryOS] plan saved for {uid_plan} "
                f"(steps={len(steps)})"
            )
        else:
            print("[MemoryOS] no planner in extras; skip plan save")

    except Exception as e:
        print("[MemoryOS] plan save failed:", e)

    # ---------- データセット ----------
    try:
        meta_ds = {
            "session_id": (context or {}).get("user_id") or "anon",
            "request_id": request_id,
            "model": "gpt-5-thinking",
            "api_version": os.getenv(
                "VERITAS_API_VERSION", "veritas-api 1.x"
            ),
            "kernel_version": os.getenv(
                "VERITAS_KERNEL_VERSION", "core-kernel 0.x"
            ),
            "git_commit": os.getenv("VERITAS_GIT_COMMIT"),
            "latency_ms": int((time.time() - started_at) * 1000),
        }
        eval_meta = {
            "task_type": "decision",
            "policy_tags": ["no_harm", "privacy_ok"],
            "rater": {"type": "ai", "id": "telos-proxy"},
        }
        append_dataset_record(
            build_dataset_record(
                req_payload=body,
                res_payload=payload,
                meta=meta_ds,
                eval_meta=eval_meta,
            )
        )
    except Exception as e:
        print("[dataset] skip:", e)

    # ---------- 決定レコードを LOG/DATASET に保存 ----------
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        DATASET_DIR.mkdir(parents=True, exist_ok=True)

        metrics2 = (response_extras.get("metrics") or {})
        latency_ms2 = int(metrics2.get("latency_ms", 0))
        mem_evidence_count = int(metrics2.get("mem_evidence_count", 0))

        evidence_list: List[Dict[str, Any]] = []
        if isinstance(payload.get("evidence"), list):
            evidence_list = payload["evidence"]  # type: ignore
        elif isinstance(evidence, list):
            evidence_list = evidence  # type: ignore

        mem_evidence_count = 0
        for ev in evidence_list:
            if not isinstance(ev, dict):
                continue
            src = str(ev.get("source", "")).lower()
            if (
                "memory" in src
                or "episodic" in src
                or "semantic" in src
                or "skills" in src
            ):
                mem_evidence_count += 1

        if isinstance(chosen, dict):
            src = str(chosen.get("source", "")).lower()
            if (
                "memory" in src
                or "episodic" in src
                or "semantic" in src
                or "skills" in src
            ):
                mem_evidence_count = max(mem_evidence_count, 1)

        meta_payload = payload.get("meta") or {}
        meta_payload["memory_evidence_count"] = mem_evidence_count
        payload["meta"] = meta_payload

        fuji_full = payload.get("fuji") or {}
        world_snapshot = (context or {}).get("world")

        persist = {
            "request_id": request_id,
            "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "query": query,
            "chosen": chosen,
            "decision_status": payload.get("decision_status") or "unknown",
            "telos_score": float(payload.get("telos_score", 0.0)),
            "gate_risk": float(
                payload.get("gate", 0.0).get("risk", 0.0)  # type: ignore
            )
            if isinstance(payload.get("gate"), dict)
            else 0.0,
            "fuji_status": fuji_full.get("status"),
            "fuji": fuji_full,
            "latency_ms": latency_ms2,
            "evidence": evidence_list[-5:] if evidence_list else [],
            "memory_evidence_count": mem_evidence_count,
            "context": context,
            "world": world_snapshot,
        }

        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        fname = f"decide_{stamp}.json"

        (LOG_DIR / fname).write_text(
            json.dumps(persist, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (DATASET_DIR / fname).write_text(
            json.dumps(persist, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        print("[persist] decide record skipped:", e)

    # ======== WorldState 更新 ========
    try:
        uid_world = (context or {}).get("user_id") or user_id or "anon"

        extras_w = payload.get("extras") or {}
        planner_obj = (
            extras_w.get("planner") or extras_w.get("plan") or None
        )
        latency_ms3 = (extras_w.get("metrics") or {}).get("latency_ms")

        world_model.update_from_decision(
            user_id=uid_world,
            query=payload.get("query") or query,
            chosen=payload.get("chosen") or {},
            gate=payload.get("gate") or {},
            values=payload.get("values") or {},
            planner=planner_obj
            if isinstance(planner_obj, dict)
            else None,
            latency_ms=int(latency_ms3)
            if isinstance(latency_ms3, (int, float))
            else None,
        )
        print(f"[WorldModel] state updated for {uid_world}")
    except Exception as e:
        print("[WorldModel] update_from_decision skipped:", e)

    # ---------- AGIヒント（VERITAS_AGI用） ----------
    try:
        agi_info = world_model.next_hint_for_veritas_agi()
        extras2 = payload.setdefault("extras", {})
        extras2["veritas_agi"] = agi_info
    except Exception as e:
        print("[WorldModel] next_hint_for_veritas_agi skipped:", e)

    return payload
    
