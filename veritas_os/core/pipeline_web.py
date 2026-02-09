# veritas_os/core/pipeline_web.py
# -*- coding: utf-8 -*-
"""
VERITAS Pipeline — Web search adapter.

Safe wrappers for web_search tool integration.
Never raises; returns None on failure.
"""
from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional

_tool_web_search = None
try:
    from veritas_os.tools.web_search import web_search as _tool_web_search  # type: ignore
except Exception:
    # optional dependency / env missing in CI or local
    _tool_web_search = None


async def _safe_web_search(query: str, *, max_results: int = 5) -> Optional[dict]:
    """Returns web_search result dict or None (never raises).
    Supports both sync/async web_search (tests often monkeypatch async).
    """
    fn = _tool_web_search
    if not callable(fn):
        return None

    try:
        ws = fn(query, max_results=max_results)  # type: ignore[misc]
        if inspect.isawaitable(ws):
            ws = await ws
        return ws if isinstance(ws, dict) else None
    except Exception:
        return None


def _normalize_web_payload(payload: Any) -> Optional[Dict[str, Any]]:
    """
    web_search の戻り値を {"ok": bool, "results": list} に正規化する。
    tools.web_search の contract を基本として、異形も吸収する。
    """
    if payload is None:
        return None

    if isinstance(payload, dict):
        out = dict(payload)
        # results が無い/壊れている場合の救済
        if "results" not in out or not isinstance(out.get("results"), list):
            for k in ("items", "hits", "organic", "organic_results"):
                if isinstance(out.get(k), list):
                    out["results"] = out[k]
                    break
        out.setdefault("results", [])
        # ok が無ければ「取得できた扱い」で True
        if "ok" not in out:
            out["ok"] = True
        return out

    if isinstance(payload, list):
        return {"ok": True, "results": payload}

    s = str(payload)
    return {"ok": True, "results": [{"title": s, "url": "", "snippet": s}]}
