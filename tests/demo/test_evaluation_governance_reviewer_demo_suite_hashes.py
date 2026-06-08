"""Tests for reviewer demo suite local hash verification integration."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.demo import run_evaluation_governance_reviewer_demo as runner
from scripts.demo import run_evaluation_governance_reviewer_demo_suite as suite
from scripts.demo import validate_evaluation_governance_reviewer_demo as validator
from scripts.demo.generate_evaluation_governance_reviewer_demo_report import (
    generate_reviewer_demo_report,
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
SHA256_SHAPED_BUT_INVALID = "f" * 64


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        f"{json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)}\n",
        encoding="utf-8",
    )


def test_suite_imports_cleanly_with_hash_options() -> None:
    assert callable(suite.run_reviewer_demo_suite)
    assert callable(suite.main)


def test_run_reviewer_demo_suite_with_local_hashes_writes_report(
    tmp_path: Path,
) -> None:
    result = suite.run_reviewer_demo_suite(
        EXAMPLE_INPUT_DIR,
        output_dir=tmp_path,
        verify_local_hashes=True,
        artifact_base_dir=EXAMPLE_INPUT_DIR,
    )

    for file_name in EXPECTED_OUTPUT_FILES:
        assert (tmp_path / file_name).is_file()

    report_path = tmp_path / "reviewer-demo-report.md"
    assert result.report_path == report_path
    assert report_path.is_file()
    assert result.validation_result.local_hash_checks_passed > 0
    assert result.validation_result.local_hash_failures == ()

    report = report_path.read_text(encoding="utf-8")
    assert "Evaluation Governance Reviewer Demo Report" in report
    assert "Validation status: PASS" in report
    assert "Local hash consistency: PASS" in report
    assert "does not establish legitimacy" in report
    assert "does not certify regulatory compliance" in report


def test_suite_cli_reports_local_hash_success(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--input-dir",
            str(EXAMPLE_INPUT_DIR),
            "--output-dir",
            str(tmp_path),
            "--artifact-base-dir",
            str(EXAMPLE_INPUT_DIR),
            "--verify-local-hashes",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "PASS generated reviewer demo outputs" in completed.stdout
    assert "PASS validated reviewer demo outputs" in completed.stdout
    assert "PASS local hash consistency" in completed.stdout
    assert "PASS generated reviewer demo report" in completed.stdout
    assert (tmp_path / "reviewer-demo-report.md").is_file()


def test_local_hash_mismatch_fails_before_report_generation(
    tmp_path: Path,
) -> None:
    runner.run_reviewer_demo(EXAMPLE_INPUT_DIR, tmp_path)
    summary_path = tmp_path / "demo-summary.generated.example.json"
    summary = _load_json(summary_path)
    summary["generated_artifacts"][0]["artifact_hash"] = (
        SHA256_SHAPED_BUT_INVALID
    )
    _write_json(summary_path, summary)

    with pytest.raises(validator.ReviewerDemoValidationError) as exc_info:
        validator.validate_reviewer_demo(
            tmp_path,
            verify_local_hashes=True,
            artifact_base_dir=EXAMPLE_INPUT_DIR,
        )

    assert exc_info.value.check == "local hash consistency"
    assert "hash mismatch" in exc_info.value.message


def test_report_generator_with_local_hashes_mentions_hash_status(
    tmp_path: Path,
) -> None:
    runner.run_reviewer_demo(EXAMPLE_INPUT_DIR, tmp_path)

    report = generate_reviewer_demo_report(
        tmp_path,
        validate=True,
        verify_local_hashes=True,
        artifact_base_dir=EXAMPLE_INPUT_DIR,
    )

    assert "Validation status: PASS" in report
    assert "Local hash consistency: PASS" in report
    assert "Local hash checks:" in report
