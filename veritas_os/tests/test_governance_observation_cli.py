"""Tests for governance_observation CLI dry-run checker."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


CLI_PATH = Path("scripts/check_governance_observation.py")


def _run_cli(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI_PATH), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_valid_fixture_returns_zero() -> None:
    fixture_path = Path("fixtures/governance_observation_live_snapshot.json")

    result = _run_cli(fixture_path)

    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "valid" in output
    assert "issues: 0" in output


def test_missing_governance_observation_returns_non_zero(tmp_path: Path) -> None:
    fixture_path = tmp_path / "missing_observation.json"
    fixture_path.write_text(
        json.dumps({"governance_layer_snapshot": {}}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = _run_cli(fixture_path)

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "governance_observation not found" in output


def test_invalid_semantic_combination_returns_non_zero(tmp_path: Path) -> None:
    fixture_path = tmp_path / "invalid_semantic.json"
    fixture_path.write_text(
        json.dumps(
            {
                "governance_layer_snapshot": {
                    "governance_observation": {
                        "policy_mode": "observe",
                        "environment": "production",
                        "would_have_blocked": True,
                        "would_have_blocked_reason": "policy_violation:missing_authority_evidence",
                        "effective_outcome": "proceed",
                        "observed_outcome": "block",
                        "operator_warning": True,
                        "audit_required": True,
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _run_cli(fixture_path)

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "OBSERVE_MODE_NOT_ALLOWED_IN_PRODUCTION" in output


def test_schema_validation_error_returns_non_zero(tmp_path: Path) -> None:
    fixture_path = tmp_path / "schema_error.json"
    fixture_path.write_text(
        json.dumps(
            {
                "governance_layer_snapshot": {
                    "governance_observation": {
                        "policy_mode": "shadow",
                        "environment": "development",
                        "would_have_blocked": True,
                        "effective_outcome": "proceed",
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _run_cli(fixture_path)

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "SCHEMA_VALIDATION_FAILED" in output
    assert "Traceback" not in output
