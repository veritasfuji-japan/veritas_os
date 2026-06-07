"""Tests for the Evaluation Governance end-to-end reviewer demo runner."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.demo import run_evaluation_governance_reviewer_demo as runner

EXAMPLE_DIR = Path(
    "docs/en/demo/examples/evaluation-governance-offline-chain-v1"
)
SCRIPT_PATH = Path("scripts/demo/run_evaluation_governance_reviewer_demo.py")
GENERATED_FILE_NAMES = [
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
REQUIRED_ARTIFACT_TYPES = {
    "evaluation_receipt",
    "manifest_change_receipt",
    "outcome_delta_attribution",
    "evaluation_drift_detection",
    "trajectory_admissibility_monitor",
    "legitimacy_impact_review",
}
REQUIRED_NON_GOALS = {
    "does_not_call_v1_decide",
    "does_not_establish_legitimacy",
    "does_not_certify_compliance",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_runner_imports_cleanly() -> None:
    assert callable(runner.run_reviewer_demo)
    assert callable(runner.canonical_json_hash)
    assert callable(runner.build_demo_summary)
    assert callable(runner.write_json)
    assert callable(runner.load_json)
    assert callable(runner.main)


def test_run_reviewer_demo_generates_expected_artifacts(tmp_path: Path) -> None:
    result = runner.run_reviewer_demo(EXAMPLE_DIR, tmp_path)

    for file_name in GENERATED_FILE_NAMES:
        assert (tmp_path / file_name).is_file()

    packet = _load_json(tmp_path / "reviewer-evidence-packet.generated.example.json")
    artifacts = packet.get("evaluation_governance_artifacts")
    assert isinstance(artifacts, list)
    artifact_types = {artifact["artifact_type"] for artifact in artifacts}
    assert REQUIRED_ARTIFACT_TYPES <= artifact_types

    summary = _load_json(tmp_path / "demo-summary.generated.example.json")
    assert summary["schema_version"] == runner.DEMO_SUMMARY_SCHEMA_VERSION
    assert summary["non_runtime"] is True
    assert summary["non_enforcing"] is True
    assert REQUIRED_NON_GOALS <= set(summary["non_goals"])
    assert result.reviewer_packet == packet
    assert result.demo_summary == summary


def test_runner_cli_writes_to_output_dir(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--input-dir",
            str(EXAMPLE_DIR),
            "--output-dir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Evaluation Governance Reviewer Demo" in completed.stdout
    assert "PASS generated offline chain artifacts" in completed.stdout
    assert "PASS generated reviewer evidence packet" in completed.stdout
    assert "PASS generated demo summary" in completed.stdout
    assert "Generated 9 reviewer-facing artifacts." in completed.stdout
    for file_name in GENERATED_FILE_NAMES:
        assert (tmp_path / file_name).is_file()


def test_runner_cli_refuses_implicit_example_mutation() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--input-dir",
            str(EXAMPLE_DIR),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "refusing to write checked-in generated examples" in completed.stderr
