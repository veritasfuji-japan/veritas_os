"""TrustLog entry redaction — PII and secret masking before persistence.

This module provides deep redaction of dict-based log entries so that
sensitive values (PII, API keys, bearer tokens, secret-like strings)
are replaced with safe placeholders **before** the entry is
canonicalized, hashed, or encrypted.

Usage::

    from veritas_os.logging.redact import redact_entry

    safe = redact_entry(raw_entry)
    # safe contains no PII or secret values in any string field
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Secret / credential patterns
# ---------------------------------------------------------------------------

# API key patterns (various providers)
_RE_API_KEY = re.compile(
    r"""(?x)
    (?:
        (?:sk|pk|ak|rk)[-_][a-zA-Z0-9]{20,}            # sk-xxx, pk-xxx style
        | (?:AKIA|ASIA)[A-Z0-9]{16}                      # AWS access key ID
        | ghp_[a-zA-Z0-9]{36}                             # GitHub PAT
        | gho_[a-zA-Z0-9]{36}                             # GitHub OAuth
        | glpat-[a-zA-Z0-9\-_]{20,}                      # GitLab PAT
        | xox[bpars]-[a-zA-Z0-9\-]+                       # Slack token
        | AIza[a-zA-Z0-9_\-]{35}                          # Google API key
    )
    """,
)

# Bearer / Authorization header values
_RE_BEARER = re.compile(
    r"[Bb]earer\s+[A-Za-z0-9\-_\.]{20,}",
)

# Generic secret-like strings: long hex or base64 that look like keys/tokens
# Matches 32+ hex chars or 40+ base64-ish chars
_RE_SECRET_HEX = re.compile(r"\b[0-9a-fA-F]{40,}\b")
_RE_SECRET_B64 = re.compile(
    r"\b[A-Za-z0-9+/\-_]{40,}={0,3}\b"
)

# Key=value patterns for common secret field names
_RE_SECRET_KV = re.compile(
    r"""(?xi)
    (?:api[_-]?key|api[_-]?secret|access[_-]?token|secret[_-]?key
       |auth[_-]?token|private[_-]?key|client[_-]?secret
       |password|passwd|credential)
    \s*[=:]\s*
    \S{8,}
    """,
)

_SECRET_PLACEHOLDER = "〔REDACTED-SECRET〕"
_API_KEY_PLACEHOLDER = "〔REDACTED-API-KEY〕"
_BEARER_PLACEHOLDER = "〔REDACTED-BEARER〕"

# Fields that are part of the hash chain or structural metadata — never redact
_STRUCTURAL_FIELDS = frozenset({
    "sha256",
    "sha256_prev",
    "created_at",
    "request_id",
    "decision_id",
    "timestamp",
})

# ---------------------------------------------------------------------------
# PII redaction (delegates to core.sanitize)
# ---------------------------------------------------------------------------

try:
    from veritas_os.core.sanitize import mask_pii as _mask_pii
except (ImportError, AttributeError):
    _mask_pii = None  # type: ignore[assignment]


def _redact_secrets(text: str) -> str:
    """Replace API keys, bearer tokens, and secret-like strings in *text*."""
    text = _RE_BEARER.sub(_BEARER_PLACEHOLDER, text)
    text = _RE_API_KEY.sub(_API_KEY_PLACEHOLDER, text)
    text = _RE_SECRET_KV.sub(
        lambda m: m.group(0).split("=")[0] + "=" + _SECRET_PLACEHOLDER
        if "=" in m.group(0)
        else m.group(0).split(":")[0] + ":" + _SECRET_PLACEHOLDER,
        text,
    )
    return text


def _redact_string(value: str) -> str:
    """Apply all redaction rules to a single string value."""
    result = _redact_secrets(value)
    if _mask_pii is not None:
        result = _mask_pii(result)
    return result


def _redact_value(value: Any) -> Any:
    """Recursively redact a value (str, list, or dict)."""
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in value]
    return value


def redact_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-redact a TrustLog entry dict.

    Structural fields (sha256, sha256_prev, request_id, etc.) are
    preserved as-is; all other string-bearing fields are scanned for
    PII and secrets.

    Args:
        entry: Raw log entry.

    Returns:
        A **new** dict with sensitive values replaced by placeholders.
    """
    result: Dict[str, Any] = {}
    for key, value in entry.items():
        if key in _STRUCTURAL_FIELDS:
            result[key] = value
        else:
            result[key] = _redact_value(value)
    return result


__all__ = ["redact_entry"]
