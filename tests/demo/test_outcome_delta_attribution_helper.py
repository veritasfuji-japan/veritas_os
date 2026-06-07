"""Tests for the offline Outcome Delta Attribution helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.demo import generate_outcome_delta_attribution as helper
from scripts.demo import validate_evaluation_governance_sample_bundle as validator

EXAMPLE_DIR = Path(
    "docs/en/demo/examples/outcome-delta-attribution-helper-v1"
)
PRIOR_RECEIPT_PATH = EXAMPLE_DIR / "prior-evaluation-receipt.example.json"
CURRENT_RECEIPT_PATH = EXAMPLE_DIR / "current-evaluation-receipt.example.json"
SCHEMA_PATH = Path(
    "docs/en/demo/schemas/outcome-delta-attribution-v1.schema.json"
)
SCRIPT_PATH = Path("scripts/demo/generate_outcome_delta_attribution.py")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_generated_attribution(attribution: dict[str, object]) -> None:
    schema = _load_json(SCHEMA_PATH)
    validator._validate_payload(attribution, schema)


def test_generate_outcome_delta_attribution_from_examples() -> None:
    prior = _load_json(PRIOR_RECEIPT_PATH)
    current = _load_json(CURRENT_RECEIPT_PATH)

    attribution = helper.generate_outcome_delta_attribution(prior, current)

    assert attribution["prior_outcome"] == "allow"
    assert attribution["current_outcome"] == "escalate"
    assert attribution["outcome_changed"] is True
    cause_types = {
        cause["cause_type"] for cause in attribution["delta_causes"]
    }
    assert "evaluator_version_changed" in cause_types
    assert "rule_version_changed" in cause_types
    assert "authority_state_changed" in cause_types
    assert "qualifier_freshness_changed" in cause_types
    assert "consequence_class_changed" in cause_types
    _validate_generated_attribution(attribution)


def test_helper_cli_writes_schema_shaped_output(tmp_path: Path) -> None:
    output_path = tmp_path / "outcome-delta-attribution.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--prior",
            str(PRIOR_RECEIPT_PATH),
            "--current",
            str(CURRENT_RECEIPT_PATH),
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "Generated Outcome Delta Attribution v1" in completed.stdout
    attribution = _load_json(output_path)
    assert attribution["schema_version"] == "outcome-delta-attribution-v1"
    _validate_generated_attribution(attribution)


def test_helper_cli_prints_json_to_stdout_when_output_omitted() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--prior",
            str(PRIOR_RECEIPT_PATH),
            "--current",
            str(CURRENT_RECEIPT_PATH),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    attribution = json.loads(completed.stdout)
    assert attribution["schema_version"] == "outcome-delta-attribution-v1"


def test_identical_receipts_recommend_no_governance_action() -> None:
    prior = _load_json(PRIOR_RECEIPT_PATH)

    attribution = helper.generate_outcome_delta_attribution(prior, dict(prior))

    assert attribution["outcome_changed"] is False
    assert attribution["recommended_governance_action"] == "none"
    assert attribution["unresolved_delta"] == {
        "present": False,
        "reason": "No unexplained evaluation drift was detected.",
        "requires_review": False,
    }
    _validate_generated_attribution(attribution)
