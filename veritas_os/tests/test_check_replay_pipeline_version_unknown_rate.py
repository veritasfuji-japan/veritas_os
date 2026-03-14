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


def test_compute_version_rate_counts_unknown_and_known(tmp_path: Path) -> None:
    """Rate calculation should count unknown and known reports correctly."""
    _write_report(tmp_path / "replay_a.json", "abc123")
    _write_report(tmp_path / "replay_b.json", "unknown")
    _write_report(tmp_path / "replay_c.json", None)

    result = checker._compute_version_rate(tmp_path)

    assert result.total_reports == 3
    assert result.unknown_reports == 2
    assert result.unknown_rate == 2 / 3


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


def test_main_returns_warning_when_directory_missing(
    tmp_path: Path,
    capsys,
) -> None:
    """Missing report directory should not fail CI in cold-start environments."""
    missing_dir = tmp_path / "missing"

    code = checker.main(["--reports-dir", str(missing_dir)])
    output = capsys.readouterr().out

    assert code == 0
    assert "does not exist" in output


def test_main_rejects_invalid_threshold(capsys) -> None:
    """Invalid threshold should return argument error exit code."""
    code = checker.main(["--max-unknown-rate", "1.5"])
    output = capsys.readouterr().out

    assert code == 2
    assert "must be between 0.0 and 1.0" in output


def test_compute_version_rate_skips_invalid_json(tmp_path: Path) -> None:
    """Malformed JSON files should be ignored rather than crashing the checker."""
    bad = tmp_path / "replay_bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    _write_report(tmp_path / "replay_good.json", "unknown")

    result = checker._compute_version_rate(tmp_path)

    assert result.total_reports == 1
    assert result.unknown_reports == 1
