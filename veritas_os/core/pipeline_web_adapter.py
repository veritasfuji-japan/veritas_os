# veritas_os/core/pipeline_web_adapter.py
# -*- coding: utf-8 -*-
"""
Pipeline Web検索アダプタ。

_normalize_web_payload と _extract_web_results を提供する。
_safe_web_search は globals() によるテストフック機構のため pipeline.py に残す。

pipeline.py の module-level / nested 定義をここに移動した。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


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


__all__ = [
    "_normalize_web_payload",
    "_extract_web_results",
]
