"""Tests for scripts.quality.check_replay_pipeline_version_unknown_rate."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.quality import check_replay_pipeline_version_unknown_rate as checker


def _write_report(path: Path, pipeline_version: str | None) -> None:
    """Write a replay report fixture with optional pipeline version."""
    meta = {}
    if pipeline_version is not None:
        meta["pipeline_version"] = pipeline_version

    payload = {
        "decision_id": "dec-1",
        "meta": meta,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_compute_version_rate_counts_unknown_known_and_invalid(tmp_path: Path) -> None:
    """Rate calculation should count unknown, known, and invalid reports."""
    _write_report(tmp_path / "replay_a.json", "abc123")
    _write_report(tmp_path / "replay_b.json", "unknown")
    (tmp_path / "replay_bad.json").write_text("{not-json", encoding="utf-8")

    result = checker._compute_version_rate(tmp_path)

    assert result.total_reports == 2
    assert result.unknown_reports == 1
    assert result.invalid_reports == 1
    assert result.unknown_rate == 0.5


def test_main_returns_success_when_rate_is_within_threshold(
    tmp_path: Path,
    capsys,
) -> None:
    """Main should return success when unknown rate is acceptable."""
    _write_report(tmp_path / "replay_a.json", "abc123")
    _write_report(tmp_path / "replay_b.json", "def456")

    code = checker.main([
        "--reports-dir",
        str(tmp_path),
        "--max-unknown-rate",
        "0.1",
    ])
    output = capsys.readouterr().out

    assert code == 0
    assert "OK: unknown pipeline version rate is within threshold." in output


def test_main_returns_failure_when_rate_exceeds_threshold(
    tmp_path: Path,
    capsys,
) -> None:
    """Main should fail and print security warning when threshold is exceeded."""
    _write_report(tmp_path / "replay_a.json", "unknown")
    _write_report(tmp_path / "replay_b.json", "abc123")

    code = checker.main([
        "--reports-dir",
        str(tmp_path),
        "--max-unknown-rate",
        "0.2",
    ])
    output = capsys.readouterr().out

    assert code == 1
    assert "SECURITY WARNING" in output


def test_main_missing_directory_non_strict_warns_and_succeeds(
    tmp_path: Path,
    capsys,
) -> None:
    """Missing report directory should be warning-only without strict mode."""
    missing_dir = tmp_path / "missing"

    code = checker.main(["--reports-dir", str(missing_dir)])
    output = capsys.readouterr().out

    assert code == 0
    assert "WARNING: replay reports directory does not exist" in output


def test_main_missing_directory_strict_fails(tmp_path: Path, capsys) -> None:
    """Missing report directory should fail in strict mode."""
    missing_dir = tmp_path / "missing"

    code = checker.main([
        "--reports-dir",
        str(missing_dir),
        "--require-reports",
    ])
    output = capsys.readouterr().out

    assert code == 1
    assert "ERROR: replay reports directory is required but does not exist" in output


def test_main_empty_directory_non_strict_warns_and_succeeds(
    tmp_path: Path,
    capsys,
) -> None:
    """Empty report directory should be warning-only without strict mode."""
    code = checker.main(["--reports-dir", str(tmp_path)])
    output = capsys.readouterr().out

    assert code == 0
    assert "WARNING: no replay reports found" in output


def test_main_empty_directory_strict_fails(tmp_path: Path, capsys) -> None:
    """Empty report directory should fail in strict mode."""
    code = checker.main([
        "--reports-dir",
        str(tmp_path),
        "--require-reports",
    ])
    output = capsys.readouterr().out

    assert code == 1
    assert "ERROR: replay reports are required" in output


def test_main_only_invalid_reports_strict_fails(tmp_path: Path, capsys) -> None:
    """Strict mode should fail when all replay reports are invalid."""
    (tmp_path / "replay_bad.json").write_text("{not-json", encoding="utf-8")

    code = checker.main([
        "--reports-dir",
        str(tmp_path),
        "--require-reports",
    ])
    output = capsys.readouterr().out

    assert code == 1
    assert "WARNING: invalid replay reports were skipped: 1" in output
    assert "no valid replay_*.json reports were found" in output


def test_main_rejects_invalid_threshold(capsys) -> None:
    """Invalid threshold should return argument error exit code."""
    code = checker.main(["--max-unknown-rate", "1.5"])
    output = capsys.readouterr().out

    assert code == 2
    assert "must be between 0.0 and 1.0" in output


def test_cli_help_includes_require_reports(capsys) -> None:
    """CLI help should describe the strict report requirement flag."""
    try:
        checker.main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    output = capsys.readouterr().out
    assert "--require-reports" in output
