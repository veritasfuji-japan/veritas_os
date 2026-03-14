"""Tests for scripts.quality.generate_safety_calibration_report."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.quality import generate_safety_calibration_report as report


def _write_jsonl(path: Path, records: list[dict]) -> None:
    """Write newline-delimited JSON fixtures."""
    lines = [json.dumps(item, ensure_ascii=False) for item in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_load_samples_accepts_multiple_supported_shapes(tmp_path: Path) -> None:
    """Loader should parse supported risk and label field variants."""
    input_path = tmp_path / "samples.jsonl"
    _write_jsonl(
        input_path,
        [
            {"predicted_risk": 0.9, "actual_unsafe": True},
            {"risk": 0.2, "label": "safe"},
            {"fuji": {"risk": 0.7}, "actual_unsafe": 1},
            {"predicted_risk": 1.2, "actual_unsafe": True},
            {"predicted_risk": 0.5, "label": "unknown"},
        ],
    )

    samples = report._load_samples(input_path)

    assert samples == [(0.9, 1), (0.2, 0), (0.7, 1)]


def test_main_generates_json_and_markdown_reports(tmp_path: Path, capsys) -> None:
    """Main should produce both report formats for valid samples."""
    input_path = tmp_path / "samples.jsonl"
    output_json = tmp_path / "out" / "calibration.json"
    output_md = tmp_path / "out" / "calibration.md"
    _write_jsonl(
        input_path,
        [
            {"predicted_risk": 0.8, "actual_unsafe": 1},
            {"predicted_risk": 0.2, "actual_unsafe": 0},
            {"predicted_risk": 0.6, "actual_unsafe": 1},
            {"predicted_risk": 0.3, "actual_unsafe": 0},
        ],
    )

    code = report.main(
        [
            "--input",
            str(input_path),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
            "--bins",
            "5",
        ]
    )
    output = capsys.readouterr().out

    assert code == 0
    assert "Generated safety calibration report" in output
    assert output_json.exists()
    assert output_md.exists()

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["total_samples"] == 4
    assert payload["brier_score"] >= 0.0
    assert payload["expected_calibration_error"] >= 0.0

    markdown = output_md.read_text(encoding="utf-8")
    assert "# Safety Calibration Report" in markdown
    assert "| Bin | Samples |" in markdown


def test_main_returns_security_warning_for_empty_valid_samples(
    tmp_path: Path,
    capsys,
) -> None:
    """No valid records should return non-zero with security warning."""
    input_path = tmp_path / "empty.jsonl"
    _write_jsonl(input_path, [{"predicted_risk": "bad", "actual_unsafe": "x"}])

    code = report.main(["--input", str(input_path)])
    output = capsys.readouterr().out

    assert code == 1
    assert "SECURITY WARNING" in output


def test_main_rejects_invalid_bins_argument(tmp_path: Path, capsys) -> None:
    """Invalid bin count should fail with argument error."""
    input_path = tmp_path / "samples.jsonl"
    _write_jsonl(input_path, [{"predicted_risk": 0.5, "actual_unsafe": 1}])

    code = report.main(["--input", str(input_path), "--bins", "1"])
    output = capsys.readouterr().out

    assert code == 2
    assert "must be greater than 1" in output
