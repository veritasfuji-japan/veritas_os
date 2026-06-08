"""Tests for the Evaluation Governance reviewer demo report generator."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.demo import run_evaluation_governance_reviewer_demo as runner
from scripts.demo import validate_evaluation_governance_reviewer_demo as validator
from scripts.demo import (
    generate_evaluation_governance_reviewer_demo_report as report_generator,
)

EXAMPLE_INPUT_DIR = Path(
    "docs/en/demo/examples/evaluation-governance-offline-chain-v1"
)
SCRIPT_PATH = Path(
    "scripts/demo/generate_evaluation_governance_reviewer_demo_report.py"
)


def _generate_demo(tmp_path: Path) -> Path:
    runner.run_reviewer_demo(EXAMPLE_INPUT_DIR, tmp_path)
    return tmp_path


def test_report_generator_imports_cleanly() -> None:
    assert callable(report_generator.load_json)
    assert callable(report_generator.render_markdown_report)
    assert callable(report_generator.summarize_chain_manifest)
    assert callable(report_generator.summarize_reviewer_packet)
    assert callable(report_generator.summarize_trajectory_monitor)
    assert callable(report_generator.summarize_legitimacy_review)
    assert callable(report_generator.generate_reviewer_demo_report)
    assert callable(report_generator.main)


def test_generate_reviewer_demo_report_contains_reviewer_sections(
    tmp_path: Path,
) -> None:
    demo_dir = _generate_demo(tmp_path)
    validator.validate_reviewer_demo(demo_dir)

    report = report_generator.generate_reviewer_demo_report(demo_dir)

    assert "Evaluation Governance Reviewer Demo Report" in report
    assert "non-runtime" in report
    assert "non-enforcing" in report
    assert "does not call /v1/decide" in report
    assert "does not establish legitimacy" in report
    assert "Reviewer Evidence Packet attachments" in report
    assert "Trajectory-level admissibility signals" in report
    assert "Legitimacy impact review signals" in report
    assert "Validation status: PASS" in report


def test_report_generator_cli_writes_output(tmp_path: Path) -> None:
    demo_dir = _generate_demo(tmp_path)
    output_path = tmp_path / "report.md"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--demo-dir",
            str(demo_dir),
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "PASS generated reviewer demo report" in completed.stdout
    assert output_path.is_file()
    assert "Validation status: PASS" in output_path.read_text(encoding="utf-8")


def test_report_generator_cli_stdout_mode(tmp_path: Path) -> None:
    demo_dir = _generate_demo(tmp_path)

    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--demo-dir", str(demo_dir)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Evaluation Governance Reviewer Demo Report" in completed.stdout


def test_report_generator_cli_fails_validation_before_writing(
    tmp_path: Path,
) -> None:
    demo_dir = _generate_demo(tmp_path)
    missing_path = demo_dir / "demo-summary.generated.example.json"
    missing_path.unlink()
    output_path = tmp_path / "report.md"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--demo-dir",
            str(demo_dir),
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "FAIL generated reviewer demo report" in completed.stderr
    assert "demo-summary.generated.example.json" in completed.stderr
    assert not output_path.exists()
