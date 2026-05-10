"""Tests for bind coverage evidence freshness guard."""

from __future__ import annotations

from pathlib import Path

from scripts.governance.check_bind_coverage_evidence_freshness import (
    FIXED_GENERATED_AT,
    REGENERATE_COMMAND,
    check_bind_coverage_evidence_freshness,
)
from scripts.governance.export_bind_coverage_evidence import write_bind_coverage_evidence


def _write_committed_artifacts(directory: Path, generated_at: str) -> tuple[Path, Path]:
    committed_json = directory / "bind-coverage-evidence.latest.json"
    committed_md = directory / "bind-coverage-evidence.latest.md"
    write_bind_coverage_evidence(
        json_path=committed_json,
        markdown_path=committed_md,
        generated_at=generated_at,
    )
    return committed_json, committed_md


def test_fresh_artifacts_exit_zero(tmp_path: Path, capsys) -> None:
    """Fresh artifacts should produce a success status."""
    committed_json, committed_md = _write_committed_artifacts(tmp_path, FIXED_GENERATED_AT)

    result = check_bind_coverage_evidence_freshness(committed_json, committed_md)
    output = capsys.readouterr().out

    assert result == 0
    assert "Bind coverage evidence artifacts are fresh." in output


def test_stale_json_fails_with_regenerate_message(tmp_path: Path, capsys) -> None:
    """JSON drift should fail and print regenerate guidance."""
    committed_json, committed_md = _write_committed_artifacts(tmp_path, FIXED_GENERATED_AT)
    committed_json.write_text('{"stale": true}\n', encoding="utf-8")

    result = check_bind_coverage_evidence_freshness(committed_json, committed_md)
    output = capsys.readouterr().out

    assert result == 1
    assert "Bind coverage evidence artifacts are stale." in output
    assert str(committed_json) in output
    assert REGENERATE_COMMAND in output


def test_stale_markdown_fails_with_regenerate_message(tmp_path: Path, capsys) -> None:
    """Markdown drift should fail and print regenerate guidance."""
    committed_json, committed_md = _write_committed_artifacts(tmp_path, FIXED_GENERATED_AT)
    committed_md.write_text("# stale\n", encoding="utf-8")

    result = check_bind_coverage_evidence_freshness(committed_json, committed_md)
    output = capsys.readouterr().out

    assert result == 1
    assert str(committed_md) in output
    assert REGENERATE_COMMAND in output


def test_generated_at_only_difference_is_not_stale(tmp_path: Path) -> None:
    """Freshness check should normalize generated_at by deterministic regeneration."""
    committed_json, committed_md = _write_committed_artifacts(
        tmp_path,
        "2026-01-01T00:00:00+00:00",
    )

    result = check_bind_coverage_evidence_freshness(committed_json, committed_md)
    assert result == 0


def test_missing_committed_json_is_stale(tmp_path: Path, capsys) -> None:
    """Missing committed JSON should be stale without traceback."""
    committed_json, committed_md = _write_committed_artifacts(tmp_path, FIXED_GENERATED_AT)
    committed_json.unlink()

    result = check_bind_coverage_evidence_freshness(committed_json, committed_md)
    output = capsys.readouterr().out

    assert result == 1
    assert "Bind coverage evidence artifacts are stale." in output
    assert REGENERATE_COMMAND in output


def test_missing_committed_markdown_is_stale(tmp_path: Path, capsys) -> None:
    """Missing committed Markdown should be stale without traceback."""
    committed_json, committed_md = _write_committed_artifacts(tmp_path, FIXED_GENERATED_AT)
    committed_md.unlink()

    result = check_bind_coverage_evidence_freshness(committed_json, committed_md)
    output = capsys.readouterr().out

    assert result == 1
    assert "Bind coverage evidence artifacts are stale." in output
    assert REGENERATE_COMMAND in output


def test_invalid_committed_json_is_stale(tmp_path: Path, capsys) -> None:
    """Invalid committed JSON should be stale without traceback."""
    committed_json, committed_md = _write_committed_artifacts(tmp_path, FIXED_GENERATED_AT)
    committed_json.write_text("{invalid", encoding="utf-8")

    result = check_bind_coverage_evidence_freshness(committed_json, committed_md)
    output = capsys.readouterr().out

    assert result == 1
    assert "Bind coverage evidence artifacts are stale." in output
    assert REGENERATE_COMMAND in output


def test_non_object_committed_json_is_stale(tmp_path: Path, capsys) -> None:
    """Non-object committed JSON should be stale without traceback."""
    committed_json, committed_md = _write_committed_artifacts(tmp_path, FIXED_GENERATED_AT)
    committed_json.write_text("[]\n", encoding="utf-8")

    result = check_bind_coverage_evidence_freshness(committed_json, committed_md)
    output = capsys.readouterr().out

    assert result == 1
    assert "Bind coverage evidence artifacts are stale." in output
    assert REGENERATE_COMMAND in output
