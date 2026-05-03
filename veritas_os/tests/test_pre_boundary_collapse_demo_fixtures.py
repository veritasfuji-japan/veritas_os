"""Validation tests for pre-boundary collapse demo scenario fixtures."""

from __future__ import annotations

import json
from pathlib import Path

FIXTURE_DIR = Path("veritas_os/tests/fixtures/pre_bind/pre_boundary_collapse")
EXPECTED_PHASE_FILES = [
    "pre_boundary_collapse_phase_1_open.json",
    "pre_boundary_collapse_phase_2_iterative_shaping.json",
    "pre_boundary_collapse_phase_3_collapse.json",
    "pre_boundary_collapse_phase_4_bind.json",
]
ALLOWED_PARTICIPATION_STATES = {"informative", "participatory", "decision_shaping"}
ALLOWED_PRESERVATION_STATES = {"open", "degrading", "collapsed"}
REQUIRED_TOP_LEVEL_KEYS = {
    "phase_id",
    "phase_label",
    "options",
    "option_exposure",
    "reinforcement_asymmetry",
    "effective_optionality",
    "participation_signal",
    "expected_participation_state",
    "expected_preservation_state",
    "intervention_viability",
    "expected_bind_outcome",
    "concise_rationale",
    "lineage_evidence",
}
REQUIRED_LINEAGE_KEYS = {
    "framing_iteration_log",
    "option_exposure_trace",
    "counterfactual_probes",
    "intervention_record",
    "bind_context_snapshot",
}


def _load_fixture(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_pre_boundary_collapse_fixture_files_are_present() -> None:
    """The representative demo must include all four required phase fixtures."""
    actual_names = sorted(path.name for path in FIXTURE_DIR.glob("*.json"))

    assert actual_names == EXPECTED_PHASE_FILES


def test_pre_boundary_collapse_fixture_payload_shape_is_valid() -> None:
    """Each phase fixture must include the required canonical walkthrough fields."""
    for fixture_name in EXPECTED_PHASE_FILES:
        fixture = _load_fixture(FIXTURE_DIR / fixture_name)

        assert REQUIRED_TOP_LEVEL_KEYS.issubset(fixture.keys())
        assert fixture["options"] == ["A", "B", "C", "D"]
        assert sorted(fixture["option_exposure"].keys()) == ["A", "B", "C", "D"]


def test_pre_boundary_collapse_expected_state_vocabulary_is_consistent() -> None:
    """Expected state labels must stay aligned with VERITAS shared vocabulary."""
    for fixture_name in EXPECTED_PHASE_FILES:
        fixture = _load_fixture(FIXTURE_DIR / fixture_name)

        assert fixture["expected_participation_state"] in ALLOWED_PARTICIPATION_STATES
        assert fixture["expected_preservation_state"] in ALLOWED_PRESERVATION_STATES


def test_pre_boundary_collapse_lineage_evidence_contains_minimum_items() -> None:
    """Lineage evidence must include minimum reviewable artifacts for each phase."""
    for fixture_name in EXPECTED_PHASE_FILES:
        fixture = _load_fixture(FIXTURE_DIR / fixture_name)
        lineage_evidence = fixture["lineage_evidence"]

        assert REQUIRED_LINEAGE_KEYS.issubset(lineage_evidence.keys())
        assert all(lineage_evidence[key] for key in REQUIRED_LINEAGE_KEYS)
