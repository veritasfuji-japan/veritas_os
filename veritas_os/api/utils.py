# veritas_os/api/utils.py
"""Common utilities: error formatting, PII masking, ID generation, JSON/payload coercion."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import secrets
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---- PII検出・マスク（sanitize.py から。失敗時はフォールバック）----
try:
    from veritas_os.core.sanitize import mask_pii as _sanitize_mask_pii
    _HAS_SANITIZE = True
except Exception as _sanitize_import_err:
    _HAS_SANITIZE = False
    _sanitize_mask_pii = None  # type: ignore
    logger.warning("sanitize import failed, PII masking disabled: %s", _sanitize_import_err)


try:
    from veritas_os.core.utils import utc_now_iso_z
except Exception as _utils_import_err:
    from datetime import datetime, timezone
    logger.debug("utils import failed, using fallback utc_now_iso_z: %s", _utils_import_err)
    def utc_now_iso_z() -> str:  # type: ignore[misc]
        """UTC now helper（fallback: utils import failed）"""
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _errstr(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"


def _stage_summary(stage_payload: Any, default_text: str) -> str:
    """Return a safe summary string from heterogeneous stage payloads."""
    if isinstance(stage_payload, dict):
        summary = stage_payload.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    elif isinstance(stage_payload, list):
        for item in stage_payload:
            if isinstance(item, dict):
                summary = item.get("summary")
                if isinstance(summary, str) and summary.strip():
                    return summary.strip()
            elif isinstance(item, str) and item.strip():
                return item.strip()
    elif isinstance(stage_payload, str) and stage_payload.strip():
        return stage_payload.strip()
    return default_text


def redact(text: str) -> str:
    """PIIをマスク（redact）する。"""
    if not text:
        return text

    if _HAS_SANITIZE and _sanitize_mask_pii is not None:
        try:
            return _sanitize_mask_pii(text)
        except Exception:
            logger.warning("sanitize.mask_pii failed; falling back to basic regex")

    text = re.sub(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", "[redacted@email]", text)
    text = re.sub(r"\b\d{2,4}[-・\s]?\d{2,4}[-・\s]?\d{3,4}\b", "[redacted:phone]", text)
    return text


def _gen_request_id(seed: str = "") -> str:
    base = f"{utc_now_iso_z()}|{seed}|{secrets.token_hex(8)}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


def _coerce_alt_list(v: Any) -> list:
    """alternatives/options の壊れ入力を "list[dict]" に寄せる。"""
    if v is None:
        return []
    if isinstance(v, dict):
        v = [v]
    if not isinstance(v, list):
        return [{"id": "alt_0", "title": str(v), "description": "", "score": 1.0}]

    out = []
    for i, it in enumerate(v):
        if isinstance(it, dict):
            d = dict(it)
        else:
            d = {"title": str(it)}
        d.setdefault("id", d.get("id") or f"alt_{i}")
        d.setdefault("title", d.get("title") or d.get("text") or f"alt_{i}")
        d.setdefault("description", d.get("description") or "")
        if "score" in d and d["score"] is not None:
            try:
                score_value = float(d["score"])
                d["score"] = score_value if math.isfinite(score_value) else 1.0
            except Exception:
                d["score"] = 1.0
        else:
            d.setdefault("score", 1.0)
        out.append(d)
    return out


def _coerce_decide_payload(payload: Any, *, seed: str = "") -> Dict[str, Any]:
    """response_model を "効かせつつ" server を落とさないための最終整形。"""
    if not isinstance(payload, dict):
        payload = {
            "ok": True,
            "request_id": _gen_request_id(seed),
            "chosen": {"title": str(payload)},
            "alternatives": [],
            "options": [],
            "trust_log": None,
        }
        return payload

    d = dict(payload)

    if "trust_log" not in d:
        d["trust_log"] = None
    if "ok" not in d:
        d["ok"] = True

    if not d.get("request_id"):
        d["request_id"] = _gen_request_id(seed)

    if "chosen" not in d or d["chosen"] is None:
        d["chosen"] = {}
    elif not isinstance(d["chosen"], dict):
        d["chosen"] = {"title": str(d["chosen"])}

    alts = d.get("alternatives")
    opts = d.get("options")

    if (alts is None or alts == []) and opts:
        d["alternatives"] = _coerce_alt_list(opts)
    else:
        d["alternatives"] = _coerce_alt_list(alts)

    if not opts and d.get("alternatives"):
        d["options"] = list(d["alternatives"])
    else:
        d["options"] = _coerce_alt_list(opts)

    return d


def _coerce_fuji_payload(payload: Any, *, action: str = "") -> Dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {"status": "allow", "reasons": ["coerced"], "violations": [], "action": action}
        return payload

    d = dict(payload)
    if not d.get("status"):
        d["status"] = "allow"
    if "reasons" not in d or d["reasons"] is None:
        d["reasons"] = []
    if "violations" not in d or d["violations"] is None:
        d["violations"] = []
    return d


def _decide_example() -> dict:
    return {
        "context": {"user_id": "demo"},
        "query": "VERITASを進化させるには？",
        "options": [{"title": "最小ステップで前進"}],
        "min_evidence": 1,
    }


DECIDE_GENERIC_ERROR = "service_unavailable"


def _log_decide_failure(message: str, err: Optional[Exception | str]) -> None:
    """Log internal decide pipeline errors without exposing details to clients."""
    if err is None:
        logger.error("decide failed: %s", message)
        return
    if isinstance(err, Exception):
        err_detail = _errstr(err)
    else:
        err_detail = str(err)
    logger.error("decide failed: %s (%s)", message, err_detail)


def _classify_decide_failure(err: BaseException) -> str:
    """Classify decide failure causes for safe-side operational diagnostics."""
    if isinstance(err, TimeoutError):
        return "timeout"
    if isinstance(err, PermissionError):
        return "permission_denied"
    if isinstance(err, (ValueError, TypeError, KeyError)):
        return "invalid_input"
    return "internal"


def _is_debug_mode() -> bool:
    """Return whether debug mode is explicitly enabled by environment variable."""
    import os
    debug_flag = os.getenv("VERITAS_DEBUG_MODE", "")
    normalized_flag = debug_flag.strip().lower()
    debug_truthy_values = {"1", "true", "yes", "on"}
    return normalized_flag in debug_truthy_values


def _is_direct_fuji_api_enabled() -> bool:
    """Return whether direct FUJI API access is explicitly allowed.

    Security guard:
    Production profiles always force this feature off even when the flag is
    set, because direct FUJI access bypasses `/v1/decide` pipeline controls.
    """
    import os

    flag = os.getenv("VERITAS_ENABLE_DIRECT_FUJI_API", "")
    normalized_flag = flag.strip().lower()
    truthy_values = {"1", "true", "yes", "on"}
    if normalized_flag not in truthy_values:
        return False

    profile = (os.getenv("VERITAS_ENV") or "").strip().lower()
    if profile in {"prod", "production"}:
        logger.warning(
            "[security-warning] VERITAS_ENABLE_DIRECT_FUJI_API was ignored in "
            "VERITAS_ENV=%s. Direct FUJI API is blocked in production.",
            profile,
        )
        return False
    return True


def _parse_risk_from_trust_entry(entry: Dict[str, Any]) -> float | None:
    """Extract risk score from trust-log payload in a backward compatible way."""
    if not isinstance(entry, dict):
        return None

    candidates = (
        entry.get("risk"),
        (entry.get("gate") or {}).get("risk") if isinstance(entry.get("gate"), dict) else None,
        (entry.get("fuji") or {}).get("risk") if isinstance(entry.get("fuji"), dict) else None,
    )
    for item in candidates:
        try:
            if item is None:
                continue
            risk_value = float(item)
            if not math.isfinite(risk_value):
                continue
            return risk_value
        except (TypeError, ValueError):
            continue
    return None


def _prov_actor_for_entry(entry: Dict[str, Any]) -> str:
    """Resolve PROV agent label from trust entry metadata."""
    for key in ("updated_by", "actor", "user_id", "request_user_id"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "veritas_api"
