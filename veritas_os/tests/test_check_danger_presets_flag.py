"""Tests for scripts.security.check_danger_presets_production_flag."""

from __future__ import annotations

from scripts.security import check_danger_presets_production_flag as checker


def test_validate_skips_non_production_profile() -> None:
    """Non-production profiles should not fail this deployment guard."""
    ok, findings = checker.validate_danger_presets_flag(
        {
            "VERITAS_ENV": "dev",
            "NEXT_PUBLIC_ENABLE_DANGER_PRESETS": "true",
        }
    )

    assert ok is True
    assert findings == []


def test_validate_fails_when_danger_presets_enabled_in_production() -> None:
    """Production must reject exposed danger preset toggles."""
    ok, findings = checker.validate_danger_presets_flag(
        {
            "VERITAS_ENV": "production",
            "NEXT_PUBLIC_ENABLE_DANGER_PRESETS": "1",
        }
    )

    assert ok is False
    assert any("must be disabled in production" in line for line in findings)


def test_validate_uses_node_env_production_alias() -> None:
    """NODE_ENV=production also triggers the guard even without VERITAS_ENV."""
    ok, findings = checker.validate_danger_presets_flag(
        {
            "NODE_ENV": "production",
            "NEXT_PUBLIC_ENABLE_DANGER_PRESETS": "on",
        }
    )

    assert ok is False
    assert findings


def test_main_returns_zero_when_flag_disabled(monkeypatch, capsys) -> None:
    """CLI succeeds for production profiles with danger presets disabled."""
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.setenv("NEXT_PUBLIC_ENABLE_DANGER_PRESETS", "false")

    exit_code = checker.main([])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "check passed" in output


def test_main_returns_non_zero_when_flag_enabled(monkeypatch, capsys) -> None:
    """CLI fails and prints a safe security warning for enabled danger flag."""
    monkeypatch.setenv("NODE_ENV", "prod")
    monkeypatch.setenv("NEXT_PUBLIC_ENABLE_DANGER_PRESETS", "true")

    exit_code = checker.main([])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "[SECURITY]" in output
    assert "redacted for safe logging" in output
