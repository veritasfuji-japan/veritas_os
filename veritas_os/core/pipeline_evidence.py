# veritas_os/core/pipeline_evidence.py
# -*- coding: utf-8 -*-
"""
VERITAS Pipeline — Evidence normalization, extraction, and deduplication.

Handles both pipeline-contract evidence and legacy evidence.py formats.
Never raises; always returns safe defaults.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _norm_evidence_item_simple(ev: Any) -> Optional[Dict[str, Any]]:
    """Module-level evidence normalizer (lightweight shim).

    Used by ``_evidencepy_to_pipeline_item`` which is defined at module level.
    """
    if not isinstance(ev, dict):
        return None
    try:
        ev2 = dict(ev)
        if "confidence" not in ev2 and "weight" in ev2:
            ev2["confidence"] = ev2.get("weight")
        if ("title" not in ev2 or ev2.get("title") in (None, "")) and "kind" in ev2:
            ev2["title"] = f"local:{ev2.get('kind')}"
        if ("uri" not in ev2 or ev2.get("uri") in (None, "")) and "kind" in ev2:
            ev2["uri"] = f"internal:evidence:{ev2.get('kind')}"
        src = ev2.get("source") or "local"
        conf_raw = ev2.get("confidence", 0.7)
        conf = max(0.0, min(1.0, float(conf_raw if conf_raw is not None else 0.7)))
        snippet = ev2.get("snippet")
        snippet_s = "" if snippet is None else str(snippet)
        uri = ev2.get("uri")
        uri_s = str(uri) if uri is not None else None
        return {
            "source": str(src),
            "uri": uri_s,
            "title": str(ev2.get("title") or ""),
            "snippet": snippet_s,
            "confidence": conf,
        }
    except Exception:
        return None


def _evidencepy_to_pipeline_item(ev: dict) -> dict | None:
    return _norm_evidence_item_simple(
        {
            "source": ev.get("source", "local"),
            "uri": f"internal:evidence:{ev.get('kind','unknown')}",
            "title": f"local_{ev.get('kind','unknown')}",
            "snippet": ev.get("snippet", ""),
            "confidence": float(ev.get("weight", 0.5) or 0.5),
            "tags": ev.get("tags") or [],
        }
    )


def _norm_evidence_item(ev: Any) -> Optional[Dict[str, Any]]:
    """Normalize evidence entries to dict; never raise.
    Accepts both pipeline-contract evidence and legacy/local evidence.py style:
      - confidence <- weight (if confidence missing)
      - title/uri synthesized from kind (if missing)
    """
    if not isinstance(ev, dict):
        return None

    try:
        ev2 = dict(ev)

        # ---- compat: evidence.py style -> pipeline contract ----
        # evidence.py: {source, kind, weight, snippet, tags}
        if "confidence" not in ev2 and "weight" in ev2:
            try:
                ev2["confidence"] = ev2.get("weight")
            except Exception:
                pass

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

        # ---- core normalize ----
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

        # uri は外部契約的に str に統一（dedupe/serialize 安定）
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


def _extract_web_results(ws: Any) -> List[Any]:
    """
    web_search の戻りがどんな形でも「結果リスト」を吸い上げる。
    - ws が list: そのまま返す
    - ws が dict: results/items/data/hits を優先探索
    - nested dict にも対応（1段〜2段）
    - それ以外は []
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
                # one more nested level
                for k2, v2 in v.items():
                    if isinstance(v2, dict):
                        for kk in ("results", "items", "data", "hits"):
                            vv = v2.get(kk)
                            if isinstance(vv, list):
                                return vv
    except Exception:
        return []

    return []


def _dedupe_evidence(evs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Stable dedupe for evidence list; never raise."""
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


def _query_is_step1_hint(q: Any) -> bool:
    try:
        qs = (q or "")
        ql = qs.lower()
        return (
            ("step1" in ql)
            or ("step 1" in ql)
            or ("inventory" in ql)
            or ("audit" in ql)
            or ("棚卸" in qs)
            or ("現状" in qs and ("棚卸" in qs or "整理" in qs))
        )
    except Exception:
        return False


def _has_step1_minimum_evidence(evs: Any) -> bool:
    try:
        if not isinstance(evs, list):
            return False
        has_inv = False
        has_issues = False
        for e in evs:
            if not isinstance(e, dict):
                continue
            title = str(e.get("title") or "")
            uri = str(e.get("uri") or "")
            snip = str(e.get("snippet") or "")
            kind = str(e.get("kind") or "")

            if (
                ("inventory" in kind)
                or ("local:inventory" in title)
                or ("evidence:inventory" in uri)
                or ("現状機能（棚卸し）" in snip)
                or ("棚卸" in snip and "現状" in snip)
            ):
                has_inv = True

            if (
                ("known_issues" in kind)
                or ("local:known_issues" in title)
                or ("evidence:known_issues" in uri)
                or ("既知の課題/注意" in snip)
                or ("既知" in snip and "課題" in snip)
            ):
                has_issues = True

            if has_inv and has_issues:
                return True
        return False
    except Exception:
        return False
