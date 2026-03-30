"""Tests for veritas_os.scripts.run_benchmarks_enhanced security behavior."""

from __future__ import annotations

from veritas_os.scripts import run_benchmarks_enhanced as module


def test_resolve_api_key_rejects_empty_value() -> None:
    """Empty API key must fail fast."""
    try:
        module._resolve_api_key("")
    except ValueError as exc:
        assert "VERITAS_API_KEY is not configured" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for empty API key")


def test_resolve_api_key_rejects_placeholder_value() -> None:
    """Placeholder API key must fail fast."""
    try:
        module._resolve_api_key(module._API_KEY_PLACEHOLDER)
    except ValueError as exc:
        assert "VERITAS_API_KEY is not configured" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for placeholder API key")


def test_resolve_api_key_accepts_real_value() -> None:
    """Non-empty non-placeholder key should pass validation."""
    actual = module._resolve_api_key("real-key-123")
    assert actual == "real-key-123"
