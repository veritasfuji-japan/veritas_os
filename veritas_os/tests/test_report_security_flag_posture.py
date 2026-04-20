"""Tests for scripts.security.report_security_flag_posture."""

from __future__ import annotations

from scripts.security import report_security_flag_posture as reporter


def test_build_security_flag_posture_reports_enabled_states() -> None:
    """Flag posture should only expose normalized enabled/disabled booleans."""
    posture = reporter.build_security_flag_posture(
        {
            "VERITAS_ENV": "production",
            "VERITAS_ALLOW_SSE_QUERY_API_KEY": "true",
            "VERITAS_ALLOW_WS_QUERY_API_KEY": "false",
            "NEXT_PUBLIC_ENABLE_DANGER_PRESETS": "on",
        }
    )

    assert posture["profile"] == "VERITAS_ENV=production"
    assert posture["VERITAS_ALLOW_SSE_QUERY_API_KEY"] is True
    assert posture["VERITAS_ALLOW_WS_QUERY_API_KEY"] is False
    assert posture["NEXT_PUBLIC_ENABLE_DANGER_PRESETS"] is True


def test_main_prints_redacted_summary_without_raw_values(monkeypatch, capsys) -> None:
    """CLI output must never include raw environment values."""
    monkeypatch.setenv("VERITAS_ALLOW_SSE_QUERY_API_KEY", "secret-value")
    monkeypatch.setenv("NODE_ENV", "dev")

    exit_code = reporter.main([])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "values redacted" in output
    assert "secret-value" not in output
    assert "VERITAS_ALLOW_SSE_QUERY_API_KEY: disabled" in output
