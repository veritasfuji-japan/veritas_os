# veritas_os/core/pipeline_critique.py
# -*- coding: utf-8 -*-
"""
Pipeline クリティーク強制モジュール。

run_decide_pipeline 内にネスト定義されていたクリティーク関連ヘルパーを
モジュールレベルに昇格させ、単一責務で管理する。

ISSUE-2 対応:
- critique は常に dict（list/text/None は正規化）
- findings は常に >= 3 件
- 例外は出さない（best-effort）
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .pipeline_helpers import (
    _as_str,
    _lazy_import,
    _norm_severity,
    _now_iso,
    _set_bool_metric,
    _set_int_metric,
)


# =========================================================
# findings デフォルト（監査定番指摘）
# =========================================================

def _default_findings() -> List[Dict[str, Any]]:
    """最低3項目を満たすための監査デフォルト指摘を返す。"""
    return [
        {
            "severity": "med",
            "message": "Evidence coverage may be insufficient or not independently verified",
            "code": "CRITIQUE_EVIDENCE_COVERAGE",
            "fix": "一次ソース + 独立ソース2件以上で裏取りし、根拠を decision.evidence に紐付けてください。",
            "details": {"hint": "primary+independent", "min_sources": 3},
        },
        {
            "severity": "med",
            "message": "Assumptions / scope / constraints might be under-specified",
            "code": "CRITIQUE_SCOPE_UNSPECIFIED",
            "fix": "目的・スコープ・制約・禁止事項・KPI を context に固定してください。",
            "details": {"hint": "goal/scope/constraints/kpi"},
        },
        {
            "severity": "med",
            "message": "Alternatives / trade-offs are not fully compared",
            "code": "CRITIQUE_ALTERNATIVES_WEAK",
            "fix": "少なくとも2案を比較し、採用/不採用理由（トレードオフ）を明示してください。",
            "details": {"hint": "compare>=2", "include": ["pros", "cons", "tradeoffs"]},
        },
    ]


# =========================================================
# findings パディング（正規化 + min_items 保証）
# =========================================================

def _pad_findings(findings: Any, *, min_items: int = 3) -> List[Dict[str, Any]]:
    """findings を List[Dict] に正規化し、min_items 件まで不足分をパッドする。"""
    out: List[Dict[str, Any]] = []

    if isinstance(findings, list):
        for it in findings:
            if isinstance(it, dict):
                it2 = dict(it)
                it2["severity"] = _norm_severity(it2.get("severity", "med"))
                it2.setdefault(
                    "message",
                    it2.get("message")
                    or it2.get("issue")
                    or it2.get("msg")
                    or "Critique finding",
                )
                it2.setdefault("code", it2.get("code") or "CRITIQUE_GENERIC")
                if "details" in it2 and not isinstance(it2.get("details"), dict):
                    it2["details"] = {"raw": _as_str(it2.get("details"), limit=500)}
                if "fix" in it2 and it2.get("fix") is not None:
                    it2["fix"] = _as_str(it2.get("fix"), limit=1000)
                out.append(it2)
            else:
                out.append(
                    {
                        "severity": "med",
                        "message": _as_str(it, limit=500),
                        "code": "CRITIQUE_TEXT",
                    }
                )

    elif isinstance(findings, dict):
        it2 = dict(findings)
        it2["severity"] = _norm_severity(it2.get("severity", "med"))
        it2.setdefault(
            "message",
            it2.get("message") or it2.get("issue") or it2.get("msg") or "Critique finding",
        )
        it2.setdefault("code", it2.get("code") or "CRITIQUE_GENERIC")
        if "details" in it2 and not isinstance(it2.get("details"), dict):
            it2["details"] = {"raw": _as_str(it2.get("details"), limit=500)}
        if "fix" in it2 and it2.get("fix") is not None:
            it2["fix"] = _as_str(it2.get("fix"), limit=1000)
        out = [it2]

    elif findings is not None:
        out = [
            {
                "severity": "med",
                "message": _as_str(findings, limit=500),
                "code": "CRITIQUE_TEXT",
            }
        ]

    defaults = _default_findings()
    i = 0
    while len(out) < int(min_items):
        out.append(dict(defaults[i % len(defaults)]))
        i += 1

    # 最終固定（必須キー保証）
    fixed: List[Dict[str, Any]] = []
    for it in out:
        if not isinstance(it, dict):
            fixed.append(
                {
                    "severity": "med",
                    "message": _as_str(it, limit=500),
                    "code": "CRITIQUE_TEXT",
                }
            )
            continue
        it2 = dict(it)
        it2["severity"] = _norm_severity(it2.get("severity", "med"))
        it2["message"] = _as_str(it2.get("message") or "Critique finding", limit=1000)
        it2["code"] = _as_str(it2.get("code") or "CRITIQUE_GENERIC", limit=120)
        if "details" in it2 and not isinstance(it2.get("details"), dict):
            it2["details"] = {"raw": _as_str(it2.get("details"), limit=500)}
        fixed.append(it2)

    return fixed


# =========================================================
# フォールバック critique
# =========================================================

def _critique_fallback(
    *,
    reason: str,
    query: str = "",
    chosen: Any = None,
) -> Dict[str, Any]:
    """critique が取得できない場合の dict 契約フォールバック（findings >= 3 保証）。"""
    chosen_title = ""
    try:
        if isinstance(chosen, dict):
            chosen_title = _as_str(
                chosen.get("title") or chosen.get("name") or chosen.get("chosen") or "",
                limit=120,
            )
        elif chosen is not None:
            chosen_title = _as_str(chosen, limit=120)
    except Exception:
        chosen_title = ""

    findings = _pad_findings(
        [
            {
                "severity": "high",
                "message": "Critique unavailable -> auditability reduced",
                "code": "CRITIQUE_MISSING",
                "fix": "critique module / pipeline integration を確認し、再実行してください。",
            }
        ],
        min_items=3,
    )

    return {
        "ok": False,
        "mode": "fallback",
        "reason": _as_str(reason, limit=200),
        "summary": "Critique missing/failed. Manual review required.",
        "findings": findings,
        "recommendations": [
            "Re-run decision with critique enabled",
            "Inspect TrustLog for evidence/debate/gate consistency",
        ],
        "query": _as_str(query, limit=500),
        "chosen_title": chosen_title,
        "ts": _now_iso(),
    }


# =========================================================
# List[item] -> findings 変換
# =========================================================

def _list_to_findings(items: List[Any]) -> List[Dict[str, Any]]:
    """critique.analyze() が返す List[{issue,severity,details,fix}] を findings に変換する。"""
    out: List[Dict[str, Any]] = []
    for it in items or []:
        if isinstance(it, dict):
            sev = _norm_severity(it.get("severity", "med"))
            issue = it.get("issue") or it.get("message") or it.get("msg") or "Critique finding"
            fix = it.get("fix")
            details = it.get("details") if isinstance(it.get("details"), dict) else {}
            out.append(
                {
                    "severity": sev,
                    "message": _as_str(issue, limit=1000),
                    "code": _as_str(it.get("code") or "CRITIQUE_RULE", limit=120),
                    "details": details,
                    "fix": _as_str(fix, limit=1000) if fix is not None else None,
                }
            )
        else:
            out.append(
                {
                    "severity": "med",
                    "message": _as_str(it, limit=500),
                    "code": "CRITIQUE_TEXT",
                }
            )
    return out


# =========================================================
# critique ペイロード正規化
# =========================================================

def _normalize_critique_payload(x: Any, *, min_findings: int = 3) -> Dict[str, Any]:
    """
    critique を常に dict に正規化する（例外を出さない）。
    findings >= min_findings を保証する。

    受け入れ形式:
      - dict: passthrough + defaults + findings padding
      - list: critique items list として findings に変換
      - str/other: テキスト finding としてラップ
      - None: {} を返す（呼び出し側でフォールバック）
    """
    if x is None:
        return {}

    if isinstance(x, list):
        findings = _pad_findings(_list_to_findings(x), min_items=min_findings)
        return {
            "ok": True,
            "mode": "legacy_list",
            "summary": "Critique generated (legacy list normalized).",
            "findings": findings,
            "recommendations": [],
            "ts": _now_iso(),
        }

    if isinstance(x, dict):
        out = dict(x)
        if "ok" not in out:
            out["ok"] = True
        out.setdefault("mode", out.get("mode") or "normal")
        out.setdefault("ts", out.get("ts") or _now_iso())
        out.setdefault("summary", out.get("summary") or "Critique generated.")

        findings = out.get("findings")
        if findings is None:
            if isinstance(out.get("items"), list):
                findings = _list_to_findings(out["items"])
            elif isinstance(out.get("issues"), list):
                findings = _list_to_findings(out["issues"])
            else:
                findings = []

        out["findings"] = _pad_findings(findings, min_items=min_findings)

        rec = out.get("recommendations")
        if rec is None:
            out["recommendations"] = []
        elif not isinstance(rec, list):
            out["recommendations"] = [_as_str(rec, limit=500)]

        return out

    s = _as_str(x, limit=1000)
    findings = _pad_findings(
        [{"severity": "med", "message": s, "code": "CRITIQUE_TEXT"}],
        min_items=min_findings,
    )
    return {
        "ok": True,
        "mode": "text",
        "summary": "Critique normalized from text.",
        "findings": findings,
        "recommendations": [],
        "ts": _now_iso(),
    }


# =========================================================
# critique 要求強制
# =========================================================

def _ensure_critique_required(
    *,
    response_extras: Dict[str, Any],
    query: str,
    chosen: Any,
    critique_obj: Any,
    min_findings: int = 3,
) -> Dict[str, Any]:
    """
    critique が常に存在し dict かつ findings >= min_findings であることを強制する。

    副作用:
      - extras.env_tools.critique_degraded = True（フォールバック時）
      - extras.metrics.critique_findings_count / critique_ok
    """
    c = _normalize_critique_payload(critique_obj, min_findings=min_findings)
    if not isinstance(c, dict) or not c:
        c = _critique_fallback(reason="missing_in_response", query=query, chosen=chosen)

    c["findings"] = _pad_findings(c.get("findings"), min_items=min_findings)

    used_fallback = bool(c.get("ok") is False) or (c.get("mode") == "fallback")
    if used_fallback:
        response_extras.setdefault("env_tools", {})
        if isinstance(response_extras["env_tools"], dict):
            response_extras["env_tools"]["critique_degraded"] = True

    response_extras.setdefault("metrics", {})
    if isinstance(response_extras["metrics"], dict):
        response_extras["metrics"]["critique_findings_count"] = len(c.get("findings") or [])
        response_extras["metrics"]["critique_ok"] = bool(c.get("ok") is True)

    c.setdefault("query", _as_str(query, limit=500))
    return c


# =========================================================
# chosen -> option 変換（critique.analyze に渡す用）
# =========================================================

def _chosen_to_option(chosen: Any) -> Dict[str, Any]:
    """critique.analyze() に渡す option を chosen から合成する（壊れない）。"""
    opt: Dict[str, Any] = {}

    if isinstance(chosen, dict):
        opt["title"] = chosen.get("title") or chosen.get("name") or chosen.get("chosen") or "chosen"
        for k in ("risk", "complexity", "value", "feasibility", "timeline"):
            if k in chosen:
                opt[k] = chosen.get(k)

        score = chosen.get("score")
        if isinstance(score, dict):
            for k in ("risk", "value", "feasibility"):
                if k not in opt and k in score:
                    opt[k] = score.get(k)
    else:
        opt["title"] = _as_str(chosen, limit=120) if chosen is not None else "chosen"

    opt["title"] = _as_str(opt.get("title") or "chosen", limit=120)
    return opt


# =========================================================
# critique best-effort 実行（async）
# =========================================================

async def _run_critique_best_effort(
    *,
    query: str,
    chosen: Any,
    evidence: List[Dict[str, Any]],
    debate: Any,
    context: Dict[str, Any],
    user_id: str,
    min_findings: int = 3,
) -> Dict[str, Any]:
    """
    critique モジュールが利用可能なら critique を生成する。
    例外は出さない。findings >= min_findings の dict を返す。

    NOTE: analyze() が list を返してもここで dict に正規化する。
    """
    crit_mod = _lazy_import("veritas_os.core.critique", None)
    if crit_mod is None:
        return _critique_fallback(reason="critique_module_missing", query=query, chosen=chosen)

    fn_dict = getattr(crit_mod, "analyze_dict", None)
    fn_list = getattr(crit_mod, "analyze", None)

    option = _chosen_to_option(chosen)

    try:
        if callable(fn_dict):
            out = fn_dict(option, evidence, context, min_items=min_findings)
            norm = _normalize_critique_payload(out, min_findings=min_findings)
        elif callable(fn_list):
            out = fn_list(option, evidence, context)
            norm = _normalize_critique_payload(out, min_findings=min_findings)
        else:
            return _critique_fallback(reason="critique_analyze_missing", query=query, chosen=chosen)

        if not norm:
            return _critique_fallback(reason="critique_returned_empty", query=query, chosen=chosen)

        norm["findings"] = _pad_findings(norm.get("findings"), min_items=min_findings)
        norm.setdefault("summary", norm.get("summary") or "Critique generated.")
        norm.setdefault("recommendations", norm.get("recommendations") or [])
        norm.setdefault("mode", norm.get("mode") or "normal")
        norm.setdefault("ts", norm.get("ts") or _now_iso())

        return norm

    except Exception as e:
        return _critique_fallback(
            reason=f"exception:{type(e).__name__}",
            query=query,
            chosen=chosen,
        )


__all__ = [
    "_default_findings",
    "_pad_findings",
    "_critique_fallback",
    "_list_to_findings",
    "_normalize_critique_payload",
    "_ensure_critique_required",
    "_chosen_to_option",
    "_run_critique_best_effort",
]
