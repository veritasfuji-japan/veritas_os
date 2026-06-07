"""Tests for the offline Legitimacy Impact Review helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.demo import generate_legitimacy_impact_review as helper
from scripts.demo import validate_evaluation_governance_sample_bundle as validator

EXAMPLE_DIR = Path(
    "docs/en/demo/examples/legitimacy-impact-review-helper-v1"
)
MANIFEST_CHANGE_PATH = EXAMPLE_DIR / "manifest-change-receipt.example.json"
TRAJECTORY_MONITOR_PATH = (
    EXAMPLE_DIR / "trajectory-admissibility-monitor.example.json"
)
SCHEMA_PATH = Path(
    "docs/en/demo/schemas/legitimacy-impact-review-v1.schema.json"
)
SCRIPT_PATH = Path("scripts/demo/generate_legitimacy_impact_review.py")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_generated_review(review: dict[str, object]) -> None:
    schema = _load_json(SCHEMA_PATH)
    validator._validate_payload(review, schema)


def test_generate_legitimacy_impact_review_from_examples() -> None:
    manifest_change = _load_json(MANIFEST_CHANGE_PATH)
    trajectory_monitor = _load_json(TRAJECTORY_MONITOR_PATH)

    review = helper.generate_legitimacy_impact_review(
        manifest_change,
        trajectory_monitor,
    )

    assert review["schema_version"] == "legitimacy-impact-review-v1"
    assert review["legitimacy_impact_detected"] is True
    assert {
        "authority_scope_expansion",
        "human_oversight_weakened",
        "escalation_requirement_reduced",
        "high_risk_admissibility_expanded",
    } <= set(review["impact_categories"])
    assert review["authority_impact"]["authority_scope_expanded"] is True
    assert review["oversight_impact"]["human_oversight_weakened"] is True
    assert (
        review["escalation_impact"]["escalation_requirement_reduced"]
        is True
    )
    assert (
        review["high_risk_admissibility_impact"][
            "high_risk_scope_expanded"
        ]
        is True
    )
    _validate_generated_review(review)


def test_helper_cli_writes_schema_shaped_output(tmp_path: Path) -> None:
    output_path = tmp_path / "legitimacy-impact-review.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--manifest-change",
            str(MANIFEST_CHANGE_PATH),
            "--trajectory-monitor",
            str(TRAJECTORY_MONITOR_PATH),
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "Generated Legitimacy Impact Review v1" in completed.stdout
    review = _load_json(output_path)
    assert review["schema_version"] == "legitimacy-impact-review-v1"
    _validate_generated_review(review)


def test_helper_cli_prints_json_to_stdout_when_output_omitted() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--manifest-change",
            str(MANIFEST_CHANGE_PATH),
            "--trajectory-monitor",
            str(TRAJECTORY_MONITOR_PATH),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    review = json.loads(completed.stdout)
    assert review["schema_version"] == "legitimacy-impact-review-v1"


def test_manifest_without_impact_signals_recommends_no_action() -> None:
    manifest_change = dict(_load_json(MANIFEST_CHANGE_PATH))
    manifest_change.update(
        {
            "receipt_id": "legitimacy-helper-manifest-change-no-impact-001",
            "changed_manifest_type": "other_governance_manifest",
            "changed_manifest_id": "other-governance-manifest-example-001",
            "change_reason": "Synthetic metadata-only manifest update.",
            "impact_scope": ["metadata_only_demo"],
            "legitimacy_impact_flags": [],
        }
    )

    review = helper.generate_legitimacy_impact_review(manifest_change)

    assert review["legitimacy_impact_detected"] is False
    assert review["review_status"] == "not_required"
    assert review["recommended_governance_action"] == "none"
    _validate_generated_review(review)
