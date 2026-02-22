# veritas_os/core/pipeline_evidence.py
# -*- coding: utf-8 -*-
"""
Pipeline 証拠正規化モジュール。

evidence アイテムの正規化・重複排除・evidence.py 互換変換を担う。
run_decide_pipeline 内のネスト定義と module-level 定義を統合。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# =========================================================
# evidence アイテム正規化（module-level / nested 共通実装）
# =========================================================

def _norm_evidence_item(ev: Any) -> Optional[Dict[str, Any]]:
    """
    evidence エントリを dict に正規化する（例外を出さない）。

    legacy evidence.py 形式 {source, kind, weight, snippet, tags} と
    pipeline contract 形式 {source, uri, title, snippet, confidence} の両方を受け入れる。
    """
    if not isinstance(ev, dict):
        return None

    try:
        ev2 = dict(ev)

        # evidence.py 互換: weight -> confidence
        if "confidence" not in ev2 and "weight" in ev2:
            try:
                ev2["confidence"] = ev2.get("weight")
            except Exception:
                pass

        # evidence.py 互換: kind -> title / uri
        if ("title" not in ev2 or ev2.get("title") in (None, "")) and "kind" in ev2:
            try:
                ev2["title"] = f"local:{ev2.get('kind')}"
            except Exception:
                pass

        if ("uri" not in ev2 or ev2.get("uri") in (None, "")) and "kind" in ev2:
            try:
                ev2["uri"] = f"internal:evidence:{ev2.get('kind')}"
            except Exception:
                pass

        # source
        src = ev2.get("source")
        if src in (None, ""):
            src = "local"

        uri = ev2.get("uri")
        title = ev2.get("title") or ""

        snippet = ev2.get("snippet")
        try:
            snippet_s = "" if snippet is None else str(snippet)
        except Exception:
            snippet_s = repr(snippet)

        conf_raw = ev2.get("confidence", 0.7)
        try:
            conf = float(conf_raw if conf_raw is not None else 0.7)
        except Exception:
            conf = 0.7
        conf = max(0.0, min(1.0, conf))

        if uri is None:
            uri_s = None
        else:
            try:
                uri_s = str(uri)
            except Exception:
                uri_s = repr(uri)

        return {
            "source": str(src),
            "uri": uri_s,
            "title": str(title),
            "snippet": snippet_s,
            "confidence": conf,
        }
    except Exception:
        return None


def _dedupe_evidence(evs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """evidence リストを安定的に重複排除する（例外を出さない）。"""
    try:
        seen: set[tuple[str, str, str, str]] = set()
        out: List[Dict[str, Any]] = []
        for ev in evs:
            if not isinstance(ev, dict):
                continue
            k = (
                str(ev.get("source") or ""),
                str(ev.get("uri") or ""),
                str(ev.get("title") or ""),
                str(ev.get("snippet") or ""),
            )
            if k in seen:
                continue
            seen.add(k)
            out.append(ev)
        return out
    except Exception:
        return []


# =========================================================
# module-level 軽量版（_evidencepy_to_pipeline_item から使用）
# =========================================================

def _norm_evidence_item_simple(ev: Any) -> Optional[Dict[str, Any]]:
    """
    モジュールレベルの軽量 evidence 正規化（_evidencepy_to_pipeline_item が使用）。

    _norm_evidence_item と同じロジック。後方互換のため名前を維持する。
    """
    return _norm_evidence_item(ev)


def _evidencepy_to_pipeline_item(ev: dict) -> Optional[Dict[str, Any]]:
    """evidence.py 形式の dict を pipeline contract 形式に変換する。"""
    return _norm_evidence_item_simple(
        {
            "source": ev.get("source", "local"),
            "uri": f"internal:evidence:{ev.get('kind', 'unknown')}",
            "title": f"local_{ev.get('kind', 'unknown')}",
            "snippet": ev.get("snippet", ""),
            "confidence": float(ev.get("weight", 0.5) or 0.5),
            "tags": ev.get("tags") or [],
        }
    )


__all__ = [
    "_norm_evidence_item",
    "_dedupe_evidence",
    "_norm_evidence_item_simple",
    "_evidencepy_to_pipeline_item",
]
