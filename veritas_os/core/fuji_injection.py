# veritas_os/core/fuji_injection.py
# -*- coding: utf-8 -*-
"""
FUJI Gate: Prompt injection detection and text normalization.

Extracted from fuji.py to isolate the rule-based prompt injection
detection subsystem.  This module has **no** dependency on fuji.py
and may be imported independently.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List

from .config import capability_cfg

# =========================================================
# Zero-width / non-alphanumeric regexes
# =========================================================
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff\u2060]")
_NON_ALNUM_RE = re.compile(r"[^\w\u3040-\u30ff\u4e00-\u9fff]+", re.UNICODE)

# =========================================================
# Confusable character map (Cyrillic / Greek -> ASCII)
# =========================================================
_CONFUSABLE_ASCII_MAP = str.maketrans(
    {
        "а": "a",  # Cyrillic
        "е": "e",  # Cyrillic
        "і": "i",  # Cyrillic
        "о": "o",  # Cyrillic
        "р": "p",  # Cyrillic
        "с": "c",  # Cyrillic
        "у": "y",  # Cyrillic
        "х": "x",  # Cyrillic
        "Α": "a",  # Greek
        "Β": "b",  # Greek
        "Ε": "e",  # Greek
        "Ι": "i",  # Greek
        "Κ": "k",  # Greek
        "Μ": "m",  # Greek
        "Ν": "n",  # Greek
        "Ο": "o",  # Greek
        "Ρ": "p",  # Greek
        "Τ": "t",  # Greek
        "Χ": "x",  # Greek
    }
)

# =========================================================
# Prompt injection detection patterns
# =========================================================
_PROMPT_INJECTION_PATTERNS: tuple[tuple[re.Pattern[str], float, str], ...] = (
    (
        re.compile(
            r"(ignore|disregard|override).{0,40}"
            r"(system|previous|developer|safety|policy)",
            re.IGNORECASE,
        ),
        0.4,
        "override_instructions",
    ),
    (
        re.compile(
            r"(reveal|show|leak).{0,40}"
            r"(system prompt|developer message|policy)",
            re.IGNORECASE,
        ),
        0.4,
        "reveal_system",
    ),
    (
        re.compile(r"\b(jailbreak|dan|prompt injection)\b", re.IGNORECASE),
        0.5,
        "jailbreak_keyword",
    ),
    (
        re.compile(
            r"(bypass|disable).{0,30}(safety|guard|policy|filter)",
            re.IGNORECASE,
        ),
        0.5,
        "bypass_safety",
    ),
    (
        re.compile(r"(act as|roleplay).{0,30}(system|developer|root)", re.IGNORECASE),
        0.2,
        "role_override",
    ),
)


# =========================================================
# Text normalization for injection detection
# =========================================================
def _normalize_injection_text(text: str) -> str:
    """Normalize obfuscated text before prompt-injection detection.

    Security note:
        This routine is heuristic and intentionally conservative. It reduces
        bypasses using zero-width characters, Unicode confusables, and excessive
        spacing, but it does not provide complete protection against all prompt
        injection variants.
    """
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = _ZERO_WIDTH_RE.sub("", normalized)
    normalized = normalized.translate(_CONFUSABLE_ASCII_MAP)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip().lower()


# =========================================================
# Main detection entry point
# =========================================================
def _detect_prompt_injection(text: str) -> Dict[str, Any]:
    """
    FUJI Gate に対するプロンプトインジェクションの兆候を検出する。

    安全ヘッド自体をハックしようとする試行に対する防御層として、
    ルールベースでシグナルを抽出しスコア化する。
    """
    score = 0.0
    signals: List[str] = []
    if not text:
        return {"score": 0.0, "signals": signals}

    normalized = _normalize_injection_text(text)
    compact = _NON_ALNUM_RE.sub("", normalized)

    for pattern, weight, label in _PROMPT_INJECTION_PATTERNS:
        if pattern.search(normalized) or pattern.search(compact):
            score += weight
            signals.append(label)

    compact_keyword_rules = (
        ("jailbreak", 0.5, "jailbreak_keyword"),
        ("promptinjection", 0.5, "jailbreak_keyword"),
    )
    for keyword, weight, label in compact_keyword_rules:
        if keyword in compact and label not in signals:
            score += weight
            signals.append(label)

    return {"score": min(1.0, score), "signals": signals}


# =========================================================
# Runtime pattern rebuild from YAML policy
# =========================================================
def _build_injection_patterns_from_policy(policy: Dict[str, Any]) -> None:
    """Rebuild prompt injection patterns and confusable map from YAML policy.

    Called at policy load/reload time.  Replaces module-level patterns
    via atomic swap (immutable tuple) for thread safety.
    """
    global _PROMPT_INJECTION_PATTERNS, _CONFUSABLE_ASCII_MAP

    import logging
    _logger = logging.getLogger(__name__)

    # ---- Prompt injection patterns ----
    pi_section = policy.get("prompt_injection") or {}
    raw_patterns = pi_section.get("patterns") or []
    if raw_patterns:
        built: List[tuple[re.Pattern[str], float, str]] = []
        for item in raw_patterns:
            if not isinstance(item, dict):
                continue
            try:
                compiled = re.compile(item["pattern"], re.IGNORECASE)
                weight = float(item.get("weight", 0.4))
                label = str(item.get("label", "unknown"))
                built.append((compiled, weight, label))
            except (re.error, KeyError, TypeError, ValueError) as exc:
                _logger.warning("[FUJI] prompt_injection pattern skipped: %r – %s", item, exc)
        if built:
            _PROMPT_INJECTION_PATTERNS = tuple(built)  # atomic swap with immutable

    # ---- Unicode confusable character map ----
    confusables = (policy.get("unicode_normalization") or {}).get("confusables") or {}
    if confusables and isinstance(confusables, dict):
        try:
            _CONFUSABLE_ASCII_MAP = str.maketrans(confusables)
        except (TypeError, ValueError) as exc:
            _logger.warning("[FUJI] unicode_normalization.confusables invalid: %s", exc)
