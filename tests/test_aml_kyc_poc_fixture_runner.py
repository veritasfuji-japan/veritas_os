"""Focused tests for deterministic AML/KYC PoC fixture runner."""

from __future__ import annotations

import json
from pathlib import Path

from veritas_os.scripts.aml_kyc_poc_fixture_runner import evaluate_fixture, load_scenario

SCENARIO_PATH = Path(
    "veritas_os/sample_data/governance/aml_kyc_poc_pack/"
    "scenario_high_risk_manual_review.json"
)
EXPECTED_PATH = Path(
    "veritas_os/sample_data/governance/aml_kyc_poc_pack/"
    "expected_high_risk_manual_review_output.json"
)


def test_aml_kyc_poc_fixture_matches_expected_output() -> None:
    """Scenario evaluation must remain deterministic against expected output."""
    scenario = load_scenario(SCENARIO_PATH)
    actual = evaluate_fixture(scenario)
    expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))

    assert actual == expected


def test_aml_kyc_poc_fixture_keeps_bind_closed_for_high_risk_flags() -> None:
    """High-risk fixture should remain non-admissible at bind boundary."""
    scenario = load_scenario(SCENARIO_PATH)
    actual = evaluate_fixture(scenario)

    assert actual["governance_outcome"]["gate_decision"] == "human_review_required"
    assert actual["bind_result"]["admissible"] is False
    assert actual["compliance_view"]["control_plane"] == "bind-boundary"
