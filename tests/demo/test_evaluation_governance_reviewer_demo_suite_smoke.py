"""CI-safe smoke test for the Evaluation Governance reviewer demo suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.demo.run_evaluation_governance_reviewer_demo_suite import (
    run_reviewer_demo_suite,
)

INPUT_DIR = Path(
    "docs/en/demo/examples/evaluation-governance-offline-chain-v1"
)
EXPECTED_OUTPUT_FILES = (
    "outcome-delta-attribution-1.generated.example.json",
    "outcome-delta-attribution-2.generated.example.json",
    "evaluation-drift-detection-1.generated.example.json",
    "evaluation-drift-detection-2.generated.example.json",
    "trajectory-admissibility-monitor.generated.example.json",
    "legitimacy-impact-review.generated.example.json",
    "chain-manifest.generated.example.json",
    "reviewer-evidence-packet.generated.example.json",
    "demo-summary.generated.example.json",
    "reviewer-demo-report.md",
)
EXPECTED_ARTIFACT_TYPES = {
    "evaluation_receipt",
    "manifest_change_receipt",
    "outcome_delta_attribution",
    "evaluation_drift_detection",
    "trajectory_admissibility_monitor",
    "legitimacy_impact_review",
}
EXPECTED_NON_GOALS = {
    "does_not_call_v1_decide",
    "does_not_establish_legitimacy",
    "does_not_certify_compliance",
}


def _load_json(path: Path) -> dict[str, Any]:
    """Load a generated JSON object from the smoke-test output directory."""
    return json.loads(path.read_text(encoding="utf-8"))


def test_reviewer_demo_suite_smoke_with_local_hashes(
    tmp_path: Path,
) -> None:
    """Run the full non-runtime reviewer demo suite in a temp directory."""
    result = run_reviewer_demo_suite(
        input_dir=INPUT_DIR,
        output_dir=tmp_path,
        verify_local_hashes=True,
        artifact_base_dir=INPUT_DIR,
    )

    assert result.output_dir == tmp_path.resolve()
    assert result.report_path == tmp_path / "reviewer-demo-report.md"
    assert result.validation_result.local_hash_checks_passed > 0
    assert result.validation_result.local_hash_failures == ()

    for file_name in EXPECTED_OUTPUT_FILES:
        assert (tmp_path / file_name).is_file()

    report = result.report_path.read_text(encoding="utf-8")
    assert "Evaluation Governance Reviewer Demo Report" in report
    assert "Validation status: PASS" in report
    assert "Local hash consistency: PASS" in report
    assert "does not establish legitimacy" in report
    assert "does not certify regulatory compliance" in report

    evidence_packet = _load_json(
        tmp_path / "reviewer-evidence-packet.generated.example.json"
    )
    artifacts = evidence_packet["evaluation_governance_artifacts"]
    artifact_types = {artifact["artifact_type"] for artifact in artifacts}
    assert EXPECTED_ARTIFACT_TYPES <= artifact_types

    demo_summary = _load_json(tmp_path / "demo-summary.generated.example.json")
    assert demo_summary["non_runtime"] is True
    assert demo_summary["non_enforcing"] is True
    assert EXPECTED_NON_GOALS <= set(demo_summary["non_goals"])
