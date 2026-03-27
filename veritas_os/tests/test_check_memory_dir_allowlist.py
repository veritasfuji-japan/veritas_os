"""Tests for scripts.security.check_memory_dir_allowlist."""

from __future__ import annotations

from pathlib import Path

from scripts.security import check_memory_dir_allowlist as checker


def test_validate_skips_non_production(tmp_path: Path) -> None:
    """Non-production profiles do not require MemoryOS allowlist validation."""
    ok, findings = checker.validate_memory_dir_configuration(
        {
            "VERITAS_ENV": "dev",
            "VERITAS_MEMORY_DIR": str(tmp_path / "memory"),
        }
    )

    assert ok is True
    assert findings == []


def test_validate_rejects_missing_allowlist_in_production(tmp_path: Path) -> None:
    """Production deployments must provide an allowlist when overriding memory dir."""
    ok, findings = checker.validate_memory_dir_configuration(
        {
            "VERITAS_ENV": "production",
            "VERITAS_MEMORY_DIR": str(tmp_path / "memory"),
        }
    )

    assert ok is False
    assert any("VERITAS_MEMORY_DIR_ALLOWLIST must be set" in line for line in findings)


def test_validate_rejects_allowlist_mismatch_in_production(tmp_path: Path) -> None:
    """Production deployments fail when configured memory dir is outside allowlist."""
    ok, findings = checker.validate_memory_dir_configuration(
        {
            "VERITAS_ENV": "prod",
            "VERITAS_MEMORY_DIR": str(tmp_path / "denied" / "memory"),
            "VERITAS_MEMORY_DIR_ALLOWLIST": str(tmp_path / "allowed"),
        }
    )

    assert ok is False
    assert any("outside VERITAS_MEMORY_DIR_ALLOWLIST" in line for line in findings)
    assert any("configured_dir:" in line for line in findings)


def test_validate_accepts_allowlisted_production_dir(tmp_path: Path) -> None:
    """Production deployments pass when configured memory dir is allowlisted."""
    allow_root = tmp_path / "allowed"
    configured = allow_root / "memory"

    ok, findings = checker.validate_memory_dir_configuration(
        {
            "VERITAS_ENV": "production",
            "VERITAS_MEMORY_DIR": str(configured),
            "VERITAS_MEMORY_DIR_ALLOWLIST": str(allow_root),
        }
    )

    assert ok is True
    assert findings == []


def test_main_returns_non_zero_for_invalid_configuration(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """CLI exits non-zero and prints a security warning on invalid config."""
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.setenv("VERITAS_MEMORY_DIR", str(tmp_path / "denied" / "memory"))
    monkeypatch.setenv("VERITAS_MEMORY_DIR_ALLOWLIST", str(tmp_path / "allowed"))

    exit_code = checker.main([])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "[SECURITY]" in output
    assert "VERITAS_MEMORY_DIR" in output


def test_main_strict_mode_fails_when_production_validation_is_skipped(
    monkeypatch, capsys
) -> None:
    """Strict mode requires production-profile MemoryOS validation in CI."""
    monkeypatch.setenv("VERITAS_MEMORY_DIR_CHECK_REQUIRE_PRODUCTION", "1")
    monkeypatch.delenv("VERITAS_ENV", raising=False)
    monkeypatch.delenv("VERITAS_MEMORY_DIR", raising=False)
    monkeypatch.delenv("VERITAS_MEMORY_DIR_ALLOWLIST", raising=False)

    exit_code = checker.main([])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Strict mode enabled" in output


def test_main_strict_mode_passes_with_valid_production_configuration(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Strict mode passes when CI provides valid production allowlist config."""
    allow_root = tmp_path / "allowed"
    configured = allow_root / "memory"
    monkeypatch.setenv("VERITAS_MEMORY_DIR_CHECK_REQUIRE_PRODUCTION", "1")
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.setenv("VERITAS_MEMORY_DIR", str(configured))
    monkeypatch.setenv("VERITAS_MEMORY_DIR_ALLOWLIST", str(allow_root))

    exit_code = checker.main([])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "MemoryOS production directory configuration is valid." in output


def test_main_ci_env_enforces_strict_validation_when_skipped(
    monkeypatch, capsys
) -> None:
    """CI environment must fail when production-profile validation is skipped."""
    monkeypatch.setenv("CI", "true")
    monkeypatch.delenv("VERITAS_MEMORY_DIR_CHECK_REQUIRE_PRODUCTION", raising=False)
    monkeypatch.delenv("VERITAS_ENV", raising=False)
    monkeypatch.delenv("VERITAS_MEMORY_DIR", raising=False)
    monkeypatch.delenv("VERITAS_MEMORY_DIR_ALLOWLIST", raising=False)

    exit_code = checker.main([])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Strict mode enabled" in output
