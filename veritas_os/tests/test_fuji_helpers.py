"""Tests for extracted FUJI helper utilities.

The helpers were split from ``fuji.py`` to reduce file size without changing
FUJI behavior. These tests pin the extracted behavior directly.
"""

from __future__ import annotations

from veritas_os.core import fuji_helpers


def test_safe_nonneg_int_returns_default_for_negative_values() -> None:
    """Negative values must not silently become valid thresholds."""
    assert fuji_helpers.safe_nonneg_int(-3, 7) == 7


def test_safe_nonneg_int_converts_valid_string_numbers() -> None:
    """String inputs should continue to work for env/context parsing."""
    assert fuji_helpers.safe_nonneg_int("5", 1) == 5


def test_build_followups_includes_scope_hint() -> None:
    """Scope hints should remain embedded in clarify prompts."""
    followups = fuji_helpers.build_followups(
        "query",
        {"scope": "internal audit"},
    )

    clarify = next(
        item for item in followups if item["type"] == "clarify"
    )
    assert any("internal audit" in question for question in clarify["questions"])


def test_redact_text_for_trust_log_respects_disabled_pii_redaction() -> None:
    """Disabling PII in policy must skip redaction to preserve compatibility."""
    policy = {
        "audit": {"redact_before_log": True},
        "pii": {"enabled": False},
    }

    assert (
        fuji_helpers.redact_text_for_trust_log("user@example.com", policy)
        == "user@example.com"
    )


def test_resolve_trust_log_id_falls_back_to_unknown() -> None:
    """Missing IDs should produce the stable sentinel used by FUJI."""
    assert fuji_helpers.resolve_trust_log_id({}) == "TL-UNKNOWN"
