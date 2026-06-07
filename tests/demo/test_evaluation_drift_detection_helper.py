"""Tests for the offline Evaluation Drift Detection helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.demo import generate_evaluation_drift_detection as helper
from scripts.demo import validate_evaluation_governance_sample_bundle as validator

EXAMPLE_DIR = Path(
    "docs/en/demo/examples/evaluation-drift-detection-helper-v1"
)
ATTRIBUTION_PATH = EXAMPLE_DIR / "outcome-delta-attribution.example.json"
SCHEMA_PATH = Path(
    "docs/en/demo/schemas/evaluation-drift-detection-v1.schema.json"
)
SCRIPT_PATH = Path("scripts/demo/generate_evaluation_drift_detection.py")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_generated_detection(detection: dict[str, object]) -> None:
    schema = _load_json(SCHEMA_PATH)
    validator._validate_payload(detection, schema)


def _cause_types(detection: dict[str, object]) -> set[str]:
    causes = detection["drift_causes"]
    assert isinstance(causes, list)
    return {cause["cause_type"] for cause in causes}


def test_generate_evaluation_drift_detection_from_example() -> None:
    attribution = _load_json(ATTRIBUTION_PATH)

    detection = helper.generate_evaluation_drift_detection(attribution)

    assert detection["schema_version"] == "evaluation-drift-detection-v1"
    assert detection["drift_detected"] is True
    assert detection["drift_status"] == "suspected"
    assert detection["evaluator_consistency_status"] == "unknown"
    assert detection["explanation_status"] == "partially_explained"
    assert detection["recommended_governance_action"] == (
        "requalify_evaluator"
    )
    cause_types = _cause_types(detection)
    assert "evaluator_version_changed" in cause_types
    assert "rule_version_changed" in cause_types
    _validate_generated_detection(detection)


def test_helper_cli_writes_schema_shaped_output(tmp_path: Path) -> None:
    output_path = tmp_path / "evaluation-drift-detection.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--attribution",
            str(ATTRIBUTION_PATH),
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "Generated Evaluation Drift Detection v1" in completed.stdout
    detection = _load_json(output_path)
    assert detection["schema_version"] == "evaluation-drift-detection-v1"
    _validate_generated_detection(detection)


def test_helper_cli_prints_json_to_stdout_when_output_omitted() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--attribution",
            str(ATTRIBUTION_PATH),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    detection = json.loads(completed.stdout)
    assert detection["schema_version"] == "evaluation-drift-detection-v1"
    _validate_generated_detection(detection)


def test_no_outcome_change_without_drift_like_cause_recommends_none() -> None:
    attribution = _load_json(ATTRIBUTION_PATH)
    attribution["current_outcome"] = attribution["prior_outcome"]
    attribution["outcome_changed"] = False
    attribution["delta_causes"] = [
        {
            "cause_type": "governed_state_changed",
            "severity": "info",
            "prior_value_ref": "no_compared_delta_detected",
            "current_value_ref": "no_compared_delta_detected",
            "evidence_refs": ["synthetic-receipt-ref"],
            "explanation": "No compared receipt fields changed.",
        }
    ]
    attribution["recommended_governance_action"] = "none"
    attribution["unresolved_delta"] = {
        "present": False,
        "reason": "No unexplained evaluation drift was detected.",
        "requires_review": False,
    }
    attribution_without_hash = dict(attribution)
    attribution_without_hash.pop("attribution_hash")
    attribution["attribution_hash"] = helper._sha256_json(
        attribution_without_hash
    )

    detection = helper.generate_evaluation_drift_detection(attribution)

    assert detection["drift_detected"] is False
    assert detection["drift_status"] == "not_detected"
    assert detection["recommended_governance_action"] == "none"
    _validate_generated_detection(detection)
