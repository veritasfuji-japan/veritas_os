# veritas_os/core/fuji_safety_head.py
# -*- coding: utf-8 -*-
"""
FUJI Gate: Safety head evaluation — LLM-based scoring with heuristic fallback.

Extracted from fuji.py.  This module depends on fuji_policy (for POLICY,
keyword sets, PII patterns) but does **not** depend on fuji.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List

from .config import capability_cfg
from .utils import _safe_float
from .fuji_policy import (
    POLICY,
    _PII_RE,
    _policy_blocked_keywords,
    BANNED_KEYWORDS_FALLBACK,
    SENSITIVE_KEYWORDS_FALLBACK,
)

_logger = logging.getLogger(__name__)

# =========================================================
# Risk threshold constants
# =========================================================
RISK_BASELINE = 0.05          # 安全テキストのベースラインリスク
RISK_FLOOR_PII = 0.35         # PII 検出時の最低リスク
RISK_FLOOR_PII_UNMASKED = 0.50  # PII 未マスク時の最低リスク
RISK_FLOOR_ILLICIT = 0.70     # illicit 検出時の最低リスク (deny 閾値)
RISK_FLOOR_ILLICIT_HEURISTIC = 0.80  # illicit キーワードヒューリスティクス検出時
RISK_FLOOR_SELF_HARM = 0.80   # self_harm 検出時の最低リスク
RISK_FLOOR_FLAG = 0.20        # uncertainty/evidence 不足時のフラグリスク
RISK_DENY_THRESHOLD = 0.70    # deny 判定の閾値


# =========================================================
# Data structure
# =========================================================
@dataclass
class SafetyHeadResult:
    risk_score: float
    categories: List[str]
    rationale: str
    model: str
    raw: Dict[str, Any]


# =========================================================
# Tool bridge wrappers (local, avoids importing from fuji.py)
# =========================================================
from veritas_os.tools import call_tool as _call_tool


def call_tool(kind: str, **kwargs: Any) -> Dict[str, Any]:
    """Call external tool bridge only when explicitly enabled by capability flag."""
    if not capability_cfg.enable_fuji_tool_bridge:
        raise RuntimeError(
            "fuji tool bridge is disabled by VERITAS_CAP_FUJI_TOOL_BRIDGE"
        )
    return _call_tool(kind, **kwargs)


# =========================================================
# Normalize helper
# =========================================================
def _normalize_text(s: str) -> str:
    return (s or "").replace("\u3000", " ").strip().lower()


# =========================================================
# Heuristic fallback safety head
# =========================================================
def _fallback_safety_head(text: str) -> SafetyHeadResult:
    t = _normalize_text(text)
    categories: List[str] = []
    risk = RISK_BASELINE
    rationale_parts: List[str] = []

    hard_block, sensitive = _policy_blocked_keywords(POLICY)
    hits = [w for w in hard_block if w in t] + [w for w in sensitive if w in t]
    if hits:
        categories.append("illicit")
        risk = max(risk, RISK_FLOOR_ILLICIT_HEURISTIC)
        rationale_parts.append(f"危険・違法系キーワード検出: {', '.join(sorted(set(hits)))}")

    pii_hits: List[str] = []
    if _PII_RE["phone"].search(text):
        pii_hits.append("phone")
    if _PII_RE["email"].search(text):
        pii_hits.append("email")
    if _PII_RE["address_jp"].search(text):
        pii_hits.append("address")

    # person_name_jp は誤検出が多いので PII 判定に使わない
    if pii_hits:
        categories.append("PII")
        risk = max(risk, RISK_FLOOR_PII)
        rationale_parts.append(f"PII パターン検出: {', '.join(pii_hits)}")

    if not categories:
        rationale_parts.append("特段の危険キーワードや PII パターンは検出されませんでした。")

    return SafetyHeadResult(
        risk_score=min(1.0, risk),
        categories=sorted(set(categories)),
        rationale=" / ".join(rationale_parts),
        model="heuristic_fallback",
        raw={"fallback": True, "hits": hits, "pii_hits": pii_hits},
    )


# =========================================================
# LLM fallback penalty
# =========================================================
def _apply_llm_fallback_penalty(
    result: SafetyHeadResult,
    ctx: Dict[str, Any],
    *,
    label: str = "LLM unavailable",
) -> None:
    """Apply risk floor penalty when LLM safety head is unavailable.

    セキュリティ監査 F-03/F-04 対応:
    - deterministic layer がリスクありと判定した場合 → stakes に応じたリスクフロア
    - リスク検出なし → 不確実性ベースライン 0.30
    """
    _has_risk_cats = any(
        c for c in result.categories
        if c not in ("safety_head_error",)
    )
    stakes = _safe_float(ctx.get("stakes", 0.5), 0.5)
    if _has_risk_cats:
        if stakes >= 0.7:
            result.risk_score = max(result.risk_score, 0.70)
            result.rationale += f" / [deterministic_layer] {label} + high stakes → risk floor 0.70"
        else:
            result.risk_score = max(result.risk_score, 0.50)
            result.rationale += f" / [deterministic_layer] {label} → risk floor 0.50"
    else:
        result.risk_score = max(result.risk_score, 0.30)
        result.rationale += f" / [deterministic_layer] {label} → baseline risk floor 0.30"


# =========================================================
# Main safety head runner
# =========================================================
def run_safety_head(
    text: str,
    context: Dict[str, Any] | None = None,
    alternatives: List[Dict[str, Any]] | None = None,
) -> SafetyHeadResult:
    ctx = context or {}
    try:
        res = call_tool(
            "llm_safety",
            text=text,
            context=ctx,
            alternatives=alternatives or [],
            max_categories=5,
        )

        if not isinstance(res, dict) or not res.get("ok"):
            raise RuntimeError(res.get("error") or "llm_safety returned ok=False")

        risk = _safe_float(res.get("risk_score"), 0.05)
        cats = res.get("categories") or []
        rat = res.get("rationale") or ""
        model = res.get("model") or "llm_safety_unknown"

        # セキュリティ監査 F-01 対応: LLM fallback 検出時の追加ペナルティ
        llm_fallback = bool(res.get("llm_fallback"))

        result = SafetyHeadResult(
            risk_score=max(0.0, min(1.0, risk)),
            categories=[str(c) for c in cats],
            rationale=str(rat),
            model=str(model),
            raw=res,
        )

        if llm_fallback:
            result.raw["llm_fallback"] = True
            _apply_llm_fallback_penalty(result, ctx, label="LLM unavailable")

        return result

    except (TypeError, ValueError, RuntimeError, OSError) as e:
        _logger.error(
            "[FUJI] Safety head LLM evaluation failed; falling back to heuristics: %s",
            repr(e),
            exc_info=True,
        )
        fb = _fallback_safety_head(text)
        fb.categories.append("safety_head_error")
        fb.rationale += f" / safety_head error: {repr(e)[:120]}"
        fb.raw.setdefault("safety_head_error", repr(e))
        fb.raw["llm_fallback"] = True
        _apply_llm_fallback_penalty(fb, ctx, label="LLM error")
        return fb
