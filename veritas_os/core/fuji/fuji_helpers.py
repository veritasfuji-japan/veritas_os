"""Shared FUJI helper functions used by runtime decision code.

This module keeps small, side-effect-free utilities out of ``fuji.py`` so the
main gate logic stays focused on policy application and decision assembly.
The helpers remain inside the FUJI boundary and do not alter Planner, Kernel,
or MemoryOS responsibilities.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from .fuji_injection import _normalize_injection_text as _normalize_injection
from .fuji_policy import RISKY_KEYWORDS_POC, _PII_RE
from ..types import FujiFollowup

RISK_DENY_THRESHOLD = 0.70


def now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def safe_nonneg_int(value: Any, default: int) -> int:
    """Convert ``value`` to a non-negative integer or fall back to ``default``."""
    try:
        resolved = int(value)
        return resolved if resolved >= 0 else default
    except (TypeError, ValueError):
        return default


def resolve_trust_log_id(context: Dict[str, Any]) -> str:
    """Resolve a stable trust log identifier from FUJI request context."""
    if context.get("trust_log_id"):
        return str(context["trust_log_id"])
    if context.get("request_id"):
        return str(context["request_id"])
    return "TL-UNKNOWN"


def redact_text_for_trust_log(text: str, policy: Dict[str, Any]) -> str:
    """Redact PII from TrustLog previews when the active policy requires it."""
    audit_cfg = policy.get("audit") or {}
    if not audit_cfg.get("redact_before_log", False):
        return text

    pii_cfg = policy.get("pii") or {}
    if not pii_cfg.get("enabled", True):
        return text

    masked_markers = pii_cfg.get("masked_markers") or ["●"]
    mask_token = str(masked_markers[0]) if masked_markers else "●"
    text_value = text or ""

    redact_kinds = pii_cfg.get("redact_kinds") or {}
    if redact_kinds.get("phone", True):
        text_value = _PII_RE["phone"].sub(mask_token * 4, text_value)
    if redact_kinds.get("email", True):
        text_value = _PII_RE["email"].sub(mask_token * 4, text_value)
    if redact_kinds.get("address_jp", True):
        text_value = _PII_RE["address_jp"].sub(mask_token * 4, text_value)
    if redact_kinds.get("person_name_jp", False):
        text_value = _PII_RE["person_name_jp"].sub(mask_token * 2, text_value)

    return text_value


def select_fuji_code(*, violations: List[str], meta: Dict[str, Any]) -> str:
    """Map FUJI gate signals to a standard rejection/audit code."""
    normalized = {str(v).strip().lower() for v in violations}

    prompt_injection = meta.get("prompt_injection") or {}
    if prompt_injection.get("score", 0.0) >= 0.4 or prompt_injection.get(
        "signals"
    ):
        return "F-4001"

    if "pii" in normalized or "secret_leak" in normalized:
        return "F-4003"

    if "policy_load_error" in normalized:
        return "F-3005"

    if meta.get("policy_eval_exception") or "compliance_evaluator_exception" in normalized:
        return "F-3006"

    if "unauthorized_financial_advice" in normalized:
        return "F-3002"

    if "definitive_legal_judgment" in normalized:
        return "F-3003"

    if "medical_high_risk" in normalized:
        return "F-3004"

    if "toxicity" in normalized:
        return "F-2001"

    if "bias_discrimination" in normalized:
        return "F-2002"

    if meta.get("low_evidence"):
        return "F-1002"

    if any(
        violation in {"illicit", "self_harm", "violence", "minors"}
        for violation in normalized
    ):
        return "F-3008"

    return "F-3008"


def ctx_bool(context: Dict[str, Any], key: str, default: bool) -> bool:
    """Read a bool-ish value from context while tolerating strings and numbers."""
    value = context.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on")
    return default


def is_high_risk_context(
    *,
    risk: float,
    stakes: float,
    categories: List[str],
    text: str,
) -> bool:
    """Return True when low-evidence requests should be pushed to deny/hold."""
    if stakes >= 0.7:
        return True
    if risk >= RISK_DENY_THRESHOLD:
        return True

    normalized_categories = {
        str(category).strip().lower() for category in (categories or [])
    }
    if any(
        category in normalized_categories
        for category in ("self_harm", "illicit", "violence", "minors", "pii")
    ):
        return True

    if RISKY_KEYWORDS_POC.search(text or ""):
        return True

    return False


def build_followups(text: str, context: Dict[str, Any]) -> List[FujiFollowup]:
    """Build the default follow-up actions for low-evidence FUJI decisions."""
    query = (text or "").strip()
    scope_hint = str(context.get("scope", "") or "").strip()
    scope_suffix = f" / hint: {scope_hint}" if scope_hint else ""
    return [
        {
            "type": "web_search",
            "title": "一次ソースで裏取り（独立ソース2件以上）",
            "query": query,
            "acceptance": "公式/一次情報 + 信頼できる独立ソースの2件以上",
        },
        {
            "type": "clarify",
            "title": "前提条件の確認（PoC要件）",
            "questions": [
                "PoCのゴール（監査ログ/意思決定支援/安全ゲート）の最優先は？",
                "評価指標（正確性/再現性/説明可能性/速度）の優先順位は？",
                (
                    "この判断のスコープ（対象業務・対象期間・制約）は？"
                    f"{scope_suffix}"
                ),
            ],
        },
        {
            "type": "evidence_request",
            "title": "追加エビデンス投入（社内ルール/要件）",
            "items": [
                "PoC要件定義（対象業務、判断ポイント、想定入力/出力）",
                "セキュリティ/法務制約（禁止事項・承認フロー・保管要件）",
                "成功条件（KPI、合格ライン、評価手順）",
            ],
        },
    ]


def normalize_text(text: str) -> str:
    """Normalize plain text before heuristic keyword checks."""
    return (text or "").replace("　", " ").strip().lower()


def normalize_injection_text(text: str) -> str:
    """Normalize obfuscated text before prompt-injection detection."""
    return _normalize_injection(text)
