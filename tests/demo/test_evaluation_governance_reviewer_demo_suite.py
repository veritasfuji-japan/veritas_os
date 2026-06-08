"""Tests for the Evaluation Governance reviewer demo suite runner."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.demo import run_evaluation_governance_reviewer_demo_suite as suite
from scripts.demo.validate_evaluation_governance_reviewer_demo import (
    validate_reviewer_demo,
)

EXAMPLE_INPUT_DIR = Path(
    "docs/en/demo/examples/evaluation-governance-offline-chain-v1"
)
SCRIPT_PATH = Path(
    "scripts/demo/run_evaluation_governance_reviewer_demo_suite.py"
)
EXPECTED_OUTPUT_FILES = [
    "outcome-delta-attribution-1.generated.example.json",
    "outcome-delta-attribution-2.generated.example.json",
    "evaluation-drift-detection-1.generated.example.json",
    "evaluation-drift-detection-2.generated.example.json",
    "trajectory-admissibility-monitor.generated.example.json",
    "legitimacy-impact-review.generated.example.json",
    "chain-manifest.generated.example.json",
    "reviewer-evidence-packet.generated.example.json",
    "demo-summary.generated.example.json",
]


def test_suite_imports_cleanly() -> None:
    assert callable(suite.resolve_output_dir)
    assert callable(suite.select_report_output_path)
    assert callable(suite.run_reviewer_demo_suite)
    assert callable(suite.main)


def test_run_reviewer_demo_suite_generates_validated_report(
    tmp_path: Path,
) -> None:
    result = suite.run_reviewer_demo_suite(EXAMPLE_INPUT_DIR, output_dir=tmp_path)

    for file_name in EXPECTED_OUTPUT_FILES:
        assert (tmp_path / file_name).is_file()

    report_path = tmp_path / "reviewer-demo-report.md"
    assert result.output_dir == tmp_path.resolve()
    assert result.report_path == report_path
    assert report_path.is_file()

    report = report_path.read_text(encoding="utf-8")
    assert "Evaluation Governance Reviewer Demo Report" in report
    assert "Validation status: PASS" in report
    assert "does not establish legitimacy" in report
    assert "does not certify regulatory compliance" in report

    validation_result = validate_reviewer_demo(tmp_path)
    assert validation_result.expected_files_count == len(EXPECTED_OUTPUT_FILES)


def test_suite_cli_writes_to_output_dir(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--input-dir",
            str(EXAMPLE_INPUT_DIR),
            "--output-dir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "PASS generated reviewer demo outputs" in completed.stdout
    assert "PASS validated reviewer demo outputs" in completed.stdout
    assert "PASS generated reviewer demo report" in completed.stdout
    assert (tmp_path / "reviewer-demo-report.md").is_file()


def test_suite_cli_requires_output_mode() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--input-dir",
            str(EXAMPLE_INPUT_DIR),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "--output-dir or --write-example-output is required" in completed.stderr


def test_suite_can_run_twice_in_temporary_output_dir(tmp_path: Path) -> None:
    first_result = suite.run_reviewer_demo_suite(
        EXAMPLE_INPUT_DIR,
        output_dir=tmp_path,
    )
    second_result = suite.run_reviewer_demo_suite(
        EXAMPLE_INPUT_DIR,
        output_dir=tmp_path,
    )

    assert first_result.report_path == second_result.report_path
    assert (tmp_path / "reviewer-demo-report.md").is_file()
    validate_reviewer_demo(tmp_path)
