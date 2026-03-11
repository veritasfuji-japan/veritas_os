# veritas_os/core/pipeline_retrieval.py
# -*- coding: utf-8 -*-
"""
Pipeline Stage 2/2b: MemoryOS retrieval + WebSearch.

run_decide_pipeline 内のインラインロジックを抽出し、
PipelineContext を直接操作する stage 関数として提供する。
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

from .pipeline_types import (
    PipelineContext,
    DEFAULT_CONFIDENCE,
    DOC_MIN_CONFIDENCE,
    MIN_MEMORY_SIMILARITY,
)
from .pipeline_evidence import _norm_evidence_item

logger = logging.getLogger(__name__)


# =========================================================
# Stage 2: MemoryOS retrieval
# =========================================================

def stage_memory_retrieval(
    ctx: PipelineContext,
    *,
    _get_memory_store: Callable[[], Optional[Any]],
    _memory_search: Callable[..., Any],
    _memory_put: Callable[..., None],
    _memory_add_usage: Callable[..., None],
    _flatten_memory_hits: Callable[..., List[Dict[str, Any]]],
    _warn: Callable[[str], None],
    utc_now_iso_z: Callable[[], str],
) -> None:
    """Stage 2: MemoryOS からの検索・証拠収集。ctx を直接更新する。"""
    retrieval_stage_started_at = time.time()
    retrieved: List[Dict[str, Any]] = []
    qlower = ctx.query.lower()

    # doc 種別判定
    want_doc = False
    raw_memory_kinds = ctx.context.get("memory_kinds") or ctx.body.get("memory_kinds")
    if isinstance(raw_memory_kinds, list):
        lowered = {str(k).lower() for k in raw_memory_kinds}
        want_doc = "doc" in lowered

    if ctx.is_veritas_query or any(
        key in qlower for key in ["論文", "paper", "zenodo", "veritas os", "protoagi", "プロトagi"]
    ):
        want_doc = True

    memory_store = _get_memory_store()
    if ctx.query and memory_store is not None:
        try:
            mem_hits_raw = _memory_search(
                memory_store,
                query=ctx.query,
                k=8,
                kinds=["semantic", "skills", "episodic", "doc"],
                min_sim=MIN_MEMORY_SIMILARITY,
                user_id=ctx.user_id,
            )

            doc_hits_raw = None
            if want_doc:
                try:
                    doc_hits_raw = _memory_search(
                        memory_store, query=ctx.query, k=5, kinds=["doc"], user_id=ctx.user_id,
                    )
                except Exception:  # subsystem resilience: intentionally broad
                    doc_hits_raw = None

            flat_hits: List[Dict[str, Any]] = []
            flat_hits.extend(_flatten_memory_hits(mem_hits_raw))
            flat_hits.extend(_flatten_memory_hits(doc_hits_raw, default_kind="doc"))

            seen_ids: set[str] = set()
            deduped: List[Dict[str, Any]] = []
            for h in flat_hits:
                _id = h.get("id") or h.get("key")
                _id_s = str(_id) if _id is not None else ""
                if _id_s:
                    if _id_s in seen_ids:
                        continue
                    seen_ids.add(_id_s)
                deduped.append(h)

            for h in deduped:
                v = h.get("value") or {}
                text = h.get("text") or v.get("text") or v.get("query") or ""
                if not text:
                    continue
                kind = h.get("kind") or (h.get("meta") or {}).get("kind") or "episodic"
                retrieved.append(
                    {
                        "id": h.get("id") or h.get("key"),
                        "kind": kind,
                        "text": text,
                        "score": float(h.get("score", 0.5)),
                    }
                )

            retrieved.sort(key=lambda r: r.get("score", 0.0), reverse=True)
            ctx.response_extras["metrics"]["mem_hits"] = int(len(retrieved))

            if want_doc:
                doc_only = [r for r in retrieved if r.get("kind") == "doc"]
                non_doc = [r for r in retrieved if r.get("kind") != "doc"]
                top_hits = doc_only[:3] + non_doc[: max(0, 3 - len(doc_only[:3]))]
            else:
                top_hits = retrieved[:3]

            ctx.response_extras["metrics"]["memory_evidence_count"] = int(len(top_hits))

            for r in top_hits:
                text = r.get("text") or ""
                snippet = text[:200] + ("..." if len(text) > 200 else "")
                conf = max(0.3, min(1.0, float(r.get("score", 0.5))))
                if r.get("kind") == "doc" and conf < DOC_MIN_CONFIDENCE:
                    conf = DOC_MIN_CONFIDENCE
                ev = _norm_evidence_item(
                    {
                        "source": f"memory:{r.get('kind', '')}",
                        "uri": r.get("id"),
                        "snippet": snippet,
                        "confidence": conf,
                    }
                )
                if ev:
                    ctx.evidence.append(ev)

            # record memory usage (best-effort)
            try:
                cited_ids = [str(r.get("id")) for r in top_hits if r.get("id")]
                if cited_ids:
                    ts = utc_now_iso_z()
                    _memory_put(
                        memory_store,
                        ctx.user_id,
                        key=f"memory_use_{ts}",
                        value={
                            "used": True,
                            "query": ctx.query,
                            "citations": cited_ids,
                            "timestamp": ts,
                        },
                    )
                    _memory_add_usage(memory_store, ctx.user_id, cited_ids)
            except (KeyError, TypeError, AttributeError):
                pass

        except Exception as e:  # subsystem resilience: intentionally broad
            _warn(f"[AGI-Retrieval] memory retrieval error: {repr(e)}")
            ctx.response_extras.setdefault("env_tools", {})
            ctx.response_extras["env_tools"]["memory_error"] = repr(e)

    ctx.response_extras["metrics"]["stage_latency"]["retrieval"] = max(
        0,
        int((time.time() - retrieval_stage_started_at) * 1000),
    )

    memory_citations_list: List[Dict[str, Any]] = []
    for r in retrieved[:10]:
        cid = r.get("id")
        if cid:
            memory_citations_list.append(
                {"id": cid, "kind": r.get("kind"), "score": float(r.get("score", 0.0))}
            )
    ctx.response_extras["memory_citations"] = memory_citations_list
    ctx.response_extras["memory_used_count"] = int(len(memory_citations_list))
    ctx.retrieved = retrieved


# =========================================================
# Stage 2b: WebSearch
# =========================================================

def stage_web_search(
    ctx: PipelineContext,
    *,
    _safe_web_search: Callable[..., Any],
    _normalize_web_payload: Callable[..., Optional[Dict[str, Any]]],
    _extract_web_results: Callable[..., List[Any]],
    _to_bool: Callable[..., bool],
    _get_request_params: Callable[..., Dict[str, Any]],
    _warn: Callable[[str], None],
    request: Any,
) -> None:
    """Stage 2b: WebSearch (同期版 — 呼び出し側で await する)。ctx を直接更新する。

    NOTE: _safe_web_search は async callable を想定。呼び出し側で
    ``await stage_web_search_async(...)`` としてラップする。
    """
    raise NotImplementedError("Use stage_web_search_async instead")


async def stage_web_search_async(
    ctx: PipelineContext,
    *,
    _safe_web_search: Callable[..., Any],
    _normalize_web_payload: Callable[..., Optional[Dict[str, Any]]],
    _extract_web_results: Callable[..., List[Any]],
    _to_bool: Callable[..., bool],
    _get_request_params: Callable[..., Dict[str, Any]],
    _warn: Callable[[str], None],
    request: Any,
) -> None:
    """Stage 2b: WebSearch。ctx を直接更新する。"""
    web_evidence: List[Dict[str, Any]] = []
    web_evidence_added = 0
    qlower = ctx.query.lower()

    if not isinstance(ctx.evidence, list):
        ctx.evidence = list(ctx.evidence or [])

    params = _get_request_params(request)
    web_explicit = (
        _to_bool(ctx.body.get("web"))
        or _to_bool(ctx.context.get("web"))
        or _to_bool(params.get("web"))
    )
    want_web = web_explicit or bool(ctx.is_veritas_query) or any(
        k in qlower for k in ["agi", "research", "論文", "paper", "zenodo", "arxiv"]
    )

    web_max = ctx.body.get("web_max_results") or ctx.context.get("web_max_results") or 5
    try:
        web_max = int(web_max)
    except (ValueError, TypeError):
        web_max = 5
    web_max = max(1, min(20, web_max))

    ctx.response_extras.setdefault("metrics", {})
    if not isinstance(ctx.response_extras["metrics"], dict):
        ctx.response_extras["metrics"] = {}
    ctx.response_extras["metrics"].setdefault("web_hits", 0)
    ctx.response_extras["metrics"].setdefault("web_evidence_count", 0)

    should_run_web = bool(
        ctx.query and want_web and (not ctx.fast_mode or web_explicit or ctx.is_veritas_query)
    )

    web_stage_started_at = time.time()
    if should_run_web and not ctx.mock_external_apis:
        ws = None
        ws_final_query = ctx.query

        try:
            ws0 = await _safe_web_search(ctx.query, max_results=web_max)
            ws = _normalize_web_payload(ws0)
        except Exception as e:  # subsystem resilience: intentionally broad
            ctx.response_extras.setdefault("env_tools", {})
            if isinstance(ctx.response_extras["env_tools"], dict):
                ctx.response_extras["env_tools"]["web_search_error"] = repr(e)

        if ws is None:
            ctx.response_extras["web_search"] = {"ok": True, "results": [], "degraded": True}
            ev_fallback = _norm_evidence_item(
                {
                    "source": "web",
                    "uri": "web:search",
                    "title": "web_search attempted (degraded)",
                    "snippet": f"[q={ws_final_query}] web_search unavailable or returned None",
                    "confidence": DEFAULT_CONFIDENCE,
                }
            )
            if ev_fallback:
                ev_fallback["source"] = "web"
                web_evidence.append(ev_fallback)
                ctx.evidence.append(ev_fallback)
                web_evidence_added = 1
        else:
            if isinstance(ws, dict) and "ok" not in ws:
                ws["ok"] = True
            try:
                meta = ws.get("meta") if isinstance(ws, dict) else None
                if isinstance(meta, dict):
                    ws_final_query = (
                        meta.get("final_query")
                        or meta.get("boosted_query")
                        or ws_final_query
                    )
                    meta.setdefault("final_query", ws_final_query)
            except (KeyError, TypeError, AttributeError):
                ws_final_query = ctx.query

            ctx.response_extras["web_search"] = ws
            results = _extract_web_results(ws)
            ctx.response_extras["metrics"]["web_hits"] = int(len(results))

            for item in results[:3]:
                if isinstance(item, str):
                    item = {"title": item, "snippet": item}
                elif not isinstance(item, dict):
                    item = {"title": str(item), "snippet": str(item)}
                uri = (
                    item.get("url") or item.get("uri") or item.get("link") or item.get("href")
                )
                title = item.get("title") or item.get("name") or ""
                snippet = item.get("snippet") or item.get("text") or title or (str(uri) if uri else "")
                snippet = f"[q={ws_final_query}] {snippet}"
                try:
                    confidence = float(item.get("confidence", 0.7) or 0.7)
                except (ValueError, TypeError):
                    confidence = 0.7
                ev = _norm_evidence_item(
                    {
                        "source": "web",
                        "uri": uri,
                        "title": title,
                        "snippet": snippet,
                        "confidence": confidence,
                    }
                )
                if ev:
                    ev["source"] = "web"
                    web_evidence.append(ev)
                    ctx.evidence.append(ev)
                    web_evidence_added += 1

            try:
                ok_flag = bool(ws.get("ok")) if isinstance(ws, dict) else False
            except (KeyError, TypeError, AttributeError):
                ok_flag = False

            if ok_flag and web_evidence_added == 0:
                ev_fallback = _norm_evidence_item(
                    {
                        "source": "web",
                        "uri": "web:search",
                        "title": "web_search executed",
                        "snippet": f"[q={ws_final_query}] web_search ok=True but no structured results extracted",
                        "confidence": DEFAULT_CONFIDENCE,
                    }
                )
                if ev_fallback:
                    ev_fallback["source"] = "web"
                    web_evidence.append(ev_fallback)
                    ctx.evidence.append(ev_fallback)
                    web_evidence_added = 1

    elif should_run_web and ctx.mock_external_apis:
        ctx.response_extras["web_search"] = {
            "ok": True,
            "results": [],
            "mocked": True,
            "meta": {"reason": "replay_mock_external_apis"},
        }
        ctx.response_extras.setdefault("env_tools", {})
        if isinstance(ctx.response_extras["env_tools"], dict):
            ctx.response_extras["env_tools"]["web_search_mocked"] = True
    else:
        if want_web and "web_search" not in ctx.response_extras:
            ctx.response_extras["web_search"] = {
                "ok": False,
                "results": [],
                "skipped": True,
                "reason": "fast_mode",
            }

    ctx.response_extras["metrics"]["web_evidence_count"] = int(web_evidence_added)
    ctx.response_extras["metrics"]["stage_latency"]["web"] = max(
        0,
        int((time.time() - web_stage_started_at) * 1000),
    )

    ctx.web_evidence = web_evidence
    # should_run_web を ctx に保存（persist 用）
    ctx._should_run_web = should_run_web  # type: ignore[attr-defined]


__all__ = [
    "stage_memory_retrieval",
    "stage_web_search_async",
]
