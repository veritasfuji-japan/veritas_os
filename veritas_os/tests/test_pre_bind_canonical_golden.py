"""Canonical pre-bind fixture/golden regression tests.

These tests keep participation/detection/preservation semantics reproducible
without changing bind-time behavior.
"""

from __future__ import annotations

import json
from pathlib import Path

from veritas_os.api.schemas import DecideResponse
from veritas_os.core.participation_detection import evaluate_pre_bind_structural_detection
from veritas_os.core.preservation_evaluator import evaluate_pre_bind_preservation

FIXTURE_DIR = Path("veritas_os/tests/fixtures/pre_bind")
GOLDEN_DIR = Path("veritas_os/tests/golden/pre_bind")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _evaluate(signal: dict[str, str]) -> dict[str, object]:
    detection = evaluate_pre_bind_structural_detection(signal)
    preservation = evaluate_pre_bind_preservation(
        signal,
        pre_bind_detection_summary=detection["pre_bind_detection_summary"],
    )
    return {
        "pre_bind_detection_summary": detection["pre_bind_detection_summary"],
        "pre_bind_detection_detail": detection["pre_bind_detection_detail"],
        "pre_bind_preservation_summary": preservation["pre_bind_preservation_summary"],
        "pre_bind_preservation_detail": preservation["pre_bind_preservation_detail"],
    }


def test_canonical_pre_bind_cases_match_expected_states() -> None:
    """Canonical cases must map to stable state vocabulary for reviewers."""
    for fixture_path in sorted(FIXTURE_DIR.glob("pre_bind_case_*.json")):
        fixture = _load_json(fixture_path)
        expected = fixture["expected"]
        result = _evaluate(fixture["participation_signal"])

        assert (
            result["pre_bind_detection_summary"]["participation_state"]
            == expected["participation_state"]
        )
        assert (
            result["pre_bind_preservation_summary"]["preservation_state"]
            == expected["preservation_state"]
        )


def test_canonical_pre_bind_golden_snapshots_stay_stable() -> None:
    """Golden snapshots expose drift in detection/preservation semantics."""
    for fixture_path in sorted(FIXTURE_DIR.glob("pre_bind_case_*.json")):
        fixture = _load_json(fixture_path)
        golden_path = GOLDEN_DIR / f"{fixture['case_id']}_golden.json"
        golden = _load_json(golden_path)

        evaluated = {
            "case_id": fixture["case_id"],
            "participation_signal": fixture["participation_signal"],
            **_evaluate(fixture["participation_signal"]),
        }
        assert evaluated == golden




def test_canonical_pre_bind_signals_and_rationales_are_explanatory() -> None:
    """Snapshots must include rationale-linked state explanations, not raw enums only."""
    required_signals = {
        "interpretation_space_narrowing",
        "counterfactual_availability",
        "intervention_headroom",
        "structural_openness",
    }

    for fixture_path in sorted(FIXTURE_DIR.glob("pre_bind_case_*.json")):
        fixture = _load_json(fixture_path)
        signal = fixture["participation_signal"]
        result = _evaluate(signal)

        assert required_signals.issubset(signal.keys())
        assert result["pre_bind_detection_summary"]["concise_rationale"]
        assert result["pre_bind_preservation_summary"]["concise_rationale"]
        assert "primary_contributing_signals" in result["pre_bind_detection_summary"]
        assert "main_contributing_conditions" in result["pre_bind_preservation_summary"]

        if result["pre_bind_detection_summary"]["participation_state"] != "informative":
            assert result["pre_bind_detection_summary"]["primary_contributing_signals"]

        if result["pre_bind_preservation_summary"]["preservation_state"] != "open":
            assert result["pre_bind_preservation_summary"]["main_contributing_conditions"]


def test_canonical_case_naming_and_vocabulary_consistency() -> None:
    """Fixture/golden naming and vocabulary must stay aligned with docs/OpenAPI terms."""
    canonical_case_ids = [
        "pre_bind_case_informative_open",
        "pre_bind_case_participatory_degrading",
        "pre_bind_case_decision_shaping_collapsed",
    ]

    for case_id in canonical_case_ids:
        fixture_path = FIXTURE_DIR / f"{case_id}.json"
        golden_path = GOLDEN_DIR / f"{case_id}_golden.json"

        assert fixture_path.exists()
        assert golden_path.exists()

        fixture = _load_json(fixture_path)
        golden = _load_json(golden_path)

        assert fixture["case_id"] == case_id
        assert golden["case_id"] == case_id
        assert "pre_bind_detection_summary" in golden
        assert "pre_bind_preservation_summary" in golden
def test_additive_fields_remain_optional_for_legacy_clients() -> None:
    """Legacy clients remain valid when additive pre-bind fields are absent."""
    legacy = DecideResponse(request_id="req-pre-bind-legacy")

    assert legacy.pre_bind_detection_summary is None
    assert legacy.pre_bind_detection_detail is None
    assert legacy.pre_bind_preservation_summary is None
    assert legacy.pre_bind_preservation_detail is None


def test_bind_family_fields_unchanged_with_canonical_additive_payloads() -> None:
    """Bind family semantics must remain unchanged with additive pre-bind surfaces."""
    fixture = _load_json(
        FIXTURE_DIR / "pre_bind_case_participatory_degrading.json",
    )
    evaluated = _evaluate(fixture["participation_signal"])

    response = DecideResponse(
        request_id="req-bind-family-regression-pre-bind",
        bind_outcome="ESCALATED",
        bind_reason_code="AUTHORITY_INSUFFICIENT",
        bind_failure_reason="authority evidence missing",
        **evaluated,
    )

    assert response.bind_outcome == "ESCALATED"
    assert response.bind_reason_code == "AUTHORITY_INSUFFICIENT"
    assert response.bind_failure_reason == "authority evidence missing"
