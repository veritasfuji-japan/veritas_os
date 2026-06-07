"""Tests for the Evaluation Governance sample bundle validator."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.demo import (
    validate_evaluation_governance_sample_bundle as validator,
)

SCRIPT_PATH = Path(
    "scripts/demo/validate_evaluation_governance_sample_bundle.py"
)


def test_validate_bundle_reports_checked_in_sample_success() -> None:
    result = validator.validate_bundle()

    assert result.total_count == 8
    assert result.passed_count == 8
    assert result.failures == ()


def test_validator_cli_prints_reviewer_friendly_summary() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "Evaluation Governance Sample Bundle Validation" in completed.stdout
    assert "Validated 8 / 8 artifacts." in completed.stdout
    assert "FAIL" not in completed.stdout
