# veritas_os/core/pipeline_web_adapter.py
# -*- coding: utf-8 -*-
"""
Pipeline Web検索アダプタ。

_normalize_web_payload / _extract_web_results / _safe_web_search を提供する。

_safe_web_search は依存注入パターンを採用: 呼び出し元（pipeline.py）が
web_search 関数を resolver callable として渡す。これにより、テストの
monkeypatch (pipeline.web_search / pipeline._tool_web_search) が
引き続き機能する。

pipeline.py の module-level / nested 定義をここに移動した。
"""
from __future__ import annotations

import hashlib
import inspect
import logging
import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional

from .pipeline_persistence import _UNSAFE_UNICODE_CATEGORIES
from ..utils import _redact_text

# Use the pipeline module's logger name for safe_web_search so that tests
# capturing logs from "veritas_os.core.pipeline" continue to work.
# _normalize_web_payload / _extract_web_results don't log, so this is safe.
logger = logging.getLogger("veritas_os.core.pipeline")


# =========================================================
# web_search ペイロード正規化
# =========================================================

def _normalize_web_payload(payload: Any) -> Optional[Dict[str, Any]]:
    """
    web_search の戻り値を {"ok": bool, "results": list} に正規化する。

    tools.web_search の contract を基本として、異形も吸収する:
    - dict: "results" / "items" / "hits" / "organic" etc. を探して正規化
    - list: そのまま results として格納
    - str/other: 単一アイテムとして格納
    - None: None を返す
    """
    if payload is None:
        return None

    if isinstance(payload, dict):
        out = dict(payload)
        if "results" not in out or not isinstance(out.get("results"), list):
            for k in ("items", "hits", "organic", "organic_results"):
                if isinstance(out.get(k), list):
                    out["results"] = out[k]
                    break
        out.setdefault("results", [])
        if "ok" not in out:
            out["ok"] = True
        return out

    if isinstance(payload, list):
        return {"ok": True, "results": payload}

    s = str(payload)
    return {"ok": True, "results": [{"title": s, "url": "", "snippet": s}]}


# =========================================================
# web_search 結果リスト抽出
# =========================================================

def _extract_web_results(ws: Any) -> List[Any]:
    """
    web_search の戻りがどんな形でも「結果リスト」を抽出する（例外を出さない）。

    - list: そのまま返す
    - dict: results/items/data/hits を優先探索（2段ネストまで対応）
    - それ以外: []
    """
    try:
        if ws is None:
            return []
        if isinstance(ws, list):
            return ws

        if not isinstance(ws, dict):
            return []

        # 1st pass: top-level common keys
        for k in ("results", "items", "data", "hits"):
            v = ws.get(k)
            if isinstance(v, list):
                return v

        # 2nd pass: if values are dict, look one layer deeper
        for k in ("results", "items", "data", "hits"):
            v = ws.get(k)
            if isinstance(v, dict):
                for kk in ("results", "items", "data", "hits"):
                    vv = v.get(kk)
                    if isinstance(vv, list):
                        return vv

        # 3rd pass: any nested dict under typical wrappers
        for k, v in ws.items():
            if isinstance(v, dict):
                for kk in ("results", "items", "data", "hits"):
                    vv = v.get(kk)
                    if isinstance(vv, list):
                        return vv
                for k2, v2 in v.items():
                    if isinstance(v2, dict):
                        for kk in ("results", "items", "data", "hits"):
                            vv = v2.get(kk)
                            if isinstance(vv, list):
                                return vv
    except Exception:
        return []

    return []


# =========================================================
# safe web search (依存注入パターン)
# =========================================================

async def safe_web_search(
    query: str,
    *,
    max_results: int = 5,
    web_search_resolver: Optional[Callable[[], Optional[Callable]]] = None,
) -> Optional[dict]:
    """Execute web search safely, never raising exceptions.

    Supports both sync and async web_search callables.

    Args:
        query: Search query string.
        max_results: Max results (clamped to [1, 20]).
        web_search_resolver: Callable that returns the actual web_search
            function to use. This indirection allows the caller
            (pipeline.py) to resolve the function at call time, preserving
            monkeypatch support. If None or returns non-callable, returns None.

    Returns:
        Web search result dict, or None on failure.
    """
    query_text = str(query or "").strip()
    if not query_text:
        return None
    if len(query_text) > 512:
        query_text = query_text[:512]

    # Block control characters and unsafe Unicode categories (bidi
    # overrides, surrogates, etc.) to reduce risk of log injection /
    # unsafe propagation into external adapters.
    query_text = re.sub(r"[\x00-\x1f\x7f]", "", query_text)
    query_text = "".join(
        ch for ch in query_text
        if unicodedata.category(ch) not in _UNSAFE_UNICODE_CATEGORIES
    )
    if not query_text:
        return None

    try:
        max_results_int = int(max_results)
    except (TypeError, ValueError):
        max_results_int = 5
    max_results_int = max(1, min(20, max_results_int))

    # Resolve the actual web_search function via the caller-provided resolver
    fn: Optional[Callable] = None
    if callable(web_search_resolver):
        fn = web_search_resolver()
    if not callable(fn):
        return None

    query_fingerprint = hashlib.sha256(
        query_text.encode("utf-8", errors="ignore")
    ).hexdigest()[:12]

    try:
        ws = fn(query_text, max_results=max_results_int)
        if inspect.isawaitable(ws):
            ws = await ws
        return ws if isinstance(ws, dict) else None
    except (RuntimeError, TypeError, ValueError, OSError, TimeoutError, ConnectionError) as exc:
        logger.debug(
            "_safe_web_search failed for query_redacted=%r query_sha256_12=%s: %s",
            _redact_text(query_text),
            query_fingerprint,
            repr(exc),
            exc_info=True,
        )
        return None


__all__ = [
    "_normalize_web_payload",
    "_extract_web_results",
    "safe_web_search",
]
