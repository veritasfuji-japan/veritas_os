"""Tests for performance evidence freshness checker."""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from scripts.performance.check_performance_evidence_freshness import (
    REGENERATE_COMMAND,
    check_performance_evidence_freshness,
    main,
)
from scripts.performance.export_performance_evidence import write_performance_evidence


def _write_fresh_artifacts(tmp_path: Path) -> tuple[Path, Path]:
    committed_json = tmp_path / "docs/en/validation/performance-evidence.latest.json"
    committed_md = tmp_path / "docs/en/validation/performance-evidence.latest.md"
    write_performance_evidence(json_path=committed_json, markdown_path=committed_md)
    return committed_json, committed_md


def test_fresh_artifacts_pass(tmp_path: Path) -> None:
    committed_json, committed_md = _write_fresh_artifacts(tmp_path)

    result = check_performance_evidence_freshness(committed_json, committed_md)

    assert result.fresh is True
    assert result.stale_files == ()


def test_missing_json_is_stale(tmp_path: Path) -> None:
    committed_json = tmp_path / "docs/en/validation/performance-evidence.latest.json"
    _, committed_md = _write_fresh_artifacts(tmp_path)

    committed_json.unlink()
    result = check_performance_evidence_freshness(committed_json, committed_md)

    assert result.fresh is False
    assert committed_json in result.stale_files
    assert any("FileNotFoundError" in reason for reason in result.reasons)


def test_missing_markdown_is_stale(tmp_path: Path) -> None:
    committed_json, committed_md = _write_fresh_artifacts(tmp_path)

    committed_md.unlink()
    result = check_performance_evidence_freshness(committed_json, committed_md)

    assert result.fresh is False
    assert committed_md in result.stale_files


def test_invalid_json_is_stale(tmp_path: Path) -> None:
    committed_json, committed_md = _write_fresh_artifacts(tmp_path)

    committed_json.write_text("{bad json", encoding="utf-8")
    result = check_performance_evidence_freshness(committed_json, committed_md)

    assert result.fresh is False
    assert committed_json in result.stale_files
    assert any(
        "JSONDecodeError" in reason or "ValueError" in reason
        for reason in result.reasons
    )


def test_invalid_utf8_json_is_stale(tmp_path: Path) -> None:
    committed_json, committed_md = _write_fresh_artifacts(tmp_path)

    committed_json.write_bytes(b"\xff\xfe\x00")
    result = check_performance_evidence_freshness(committed_json, committed_md)

    assert result.fresh is False
    assert any("UnicodeDecodeError" in reason for reason in result.reasons)


def test_invalid_utf8_markdown_is_stale(tmp_path: Path) -> None:
    committed_json, committed_md = _write_fresh_artifacts(tmp_path)

    committed_md.write_bytes(b"\xff\xfe\x00")
    result = check_performance_evidence_freshness(committed_json, committed_md)

    assert result.fresh is False
    assert any("UnicodeDecodeError" in reason for reason in result.reasons)


def test_json_drift_is_stale(tmp_path: Path) -> None:
    committed_json, committed_md = _write_fresh_artifacts(tmp_path)

    payload = json.loads(committed_json.read_text(encoding="utf-8"))
    payload["measurement_mode"] = "tampered"
    committed_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    result = check_performance_evidence_freshness(committed_json, committed_md)

    assert result.fresh is False
    assert committed_json in result.stale_files
    assert any("JSON payload mismatch" in reason for reason in result.reasons)


def test_markdown_drift_is_stale(tmp_path: Path) -> None:
    committed_json, committed_md = _write_fresh_artifacts(tmp_path)

    committed_md.write_text(
        committed_md.read_text(encoding="utf-8") + "extra line\n",
        encoding="utf-8",
    )

    result = check_performance_evidence_freshness(committed_json, committed_md)

    assert result.fresh is False
    assert committed_md in result.stale_files
    assert any("Markdown text mismatch" in reason for reason in result.reasons)


def test_missing_required_field_is_stale(tmp_path: Path) -> None:
    committed_json, committed_md = _write_fresh_artifacts(tmp_path)

    payload = json.loads(committed_json.read_text(encoding="utf-8"))
    del payload["metrics"]
    committed_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    result = check_performance_evidence_freshness(committed_json, committed_md)

    assert result.fresh is False
    assert any("missing required field metrics" in reason for reason in result.reasons)


def test_markdown_double_trailing_newline_is_stale(tmp_path: Path) -> None:
    committed_json, committed_md = _write_fresh_artifacts(tmp_path)

    committed_md.write_text(
        committed_md.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    result = check_performance_evidence_freshness(committed_json, committed_md)

    assert result.fresh is False
    assert any("trailing newline" in reason for reason in result.reasons)


def test_cli_main_fresh_returns_0(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    committed_json, committed_md = _write_fresh_artifacts(tmp_path)
    checker_module = __import__(
        "scripts.performance.check_performance_evidence_freshness",
        fromlist=["dummy"],
    )
    monkeypatch.setattr(checker_module, "OUTPUT_JSON", committed_json)
    monkeypatch.setattr(checker_module, "OUTPUT_MD", committed_md)

    exit_code = main()

    assert exit_code == 0
    assert "Performance evidence artifacts are fresh." in capsys.readouterr().out


def test_cli_main_stale_returns_1(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    committed_json, committed_md = _write_fresh_artifacts(tmp_path)
    payload = json.loads(committed_json.read_text(encoding="utf-8"))
    payload["sample_count"] = 999
    committed_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    checker_module = __import__(
        "scripts.performance.check_performance_evidence_freshness",
        fromlist=["dummy"],
    )
    monkeypatch.setattr(checker_module, "OUTPUT_JSON", committed_json)
    monkeypatch.setattr(checker_module, "OUTPUT_MD", committed_md)

    exit_code = main()

    assert exit_code == 1
    output = capsys.readouterr().out
    assert REGENERATE_COMMAND in output
