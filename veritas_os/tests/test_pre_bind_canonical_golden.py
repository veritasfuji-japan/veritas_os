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
