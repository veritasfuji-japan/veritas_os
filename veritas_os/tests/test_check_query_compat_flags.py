"""Tests for scripts.security.check_query_api_key_compat_flags."""

from __future__ import annotations

from scripts.security import check_query_api_key_compat_flags as checker


def test_validate_skips_non_production_profile() -> None:
    """Non-production profiles should not fail this deployment guard."""
    ok, findings = checker.validate_query_api_key_compat_flags(
        {
            "VERITAS_ENV": "dev",
            "VERITAS_ALLOW_SSE_QUERY_API_KEY": "true",
        }
    )

    assert ok is True
    assert findings == []


def test_validate_fails_when_query_flags_enabled_in_production() -> None:
    """Production must reject legacy query API key compatibility flags."""
    ok, findings = checker.validate_query_api_key_compat_flags(
        {
            "VERITAS_ENV": "production",
            "VERITAS_ALLOW_SSE_QUERY_API_KEY": "true",
            "VERITAS_ALLOW_WS_QUERY_API_KEY": "1",
        }
    )

    assert ok is False
    assert any("must be disabled in production" in line for line in findings)
    assert any("VERITAS_ALLOW_SSE_QUERY_API_KEY" in line for line in findings)
    assert any("VERITAS_ALLOW_WS_QUERY_API_KEY" in line for line in findings)


def test_main_returns_zero_when_production_flags_are_disabled(
    monkeypatch, capsys
) -> None:
    """CLI succeeds for production profiles with compatibility flags off."""
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.delenv("VERITAS_ALLOW_SSE_QUERY_API_KEY", raising=False)
    monkeypatch.setenv("VERITAS_ALLOW_WS_QUERY_API_KEY", "false")

    exit_code = checker.main([])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "disabled for production" in output


def test_main_returns_non_zero_when_production_flag_is_enabled(
    monkeypatch, capsys
) -> None:
    """CLI fails and prints a security warning for unsafe production flags."""
    monkeypatch.setenv("VERITAS_ENV", "prod")
    monkeypatch.setenv("VERITAS_ALLOW_WS_QUERY_API_KEY", "on")

    exit_code = checker.main([])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "[SECURITY]" in output
    assert "redacted for safe logging" in output
