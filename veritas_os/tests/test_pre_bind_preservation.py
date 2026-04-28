"""Tests for additive pre-bind preservation layer."""

from __future__ import annotations

from veritas_os.api.schemas import DecideResponse
from veritas_os.core.participation_detection import (
    evaluate_pre_bind_structural_detection,
)
from veritas_os.core.pipeline.pipeline_response import assemble_response
from veritas_os.core.pipeline.pipeline_types import PipelineContext
from veritas_os.core.preservation_evaluator import evaluate_pre_bind_preservation


def test_preservation_open_state() -> None:
    """High openness + viable intervention should remain open."""
    result = evaluate_pre_bind_preservation(
        {
            "interpretation_space_narrowing": "open",
            "counterfactual_availability": "high",
            "intervention_headroom": "high",
            "structural_openness": "open",
        }
    )
    assert result["pre_bind_preservation_summary"]["preservation_state"] == "open"


def test_preservation_degrading_state() -> None:
    """Fragile openness with remaining intervention should classify degrading."""
    result = evaluate_pre_bind_preservation(
        {
            "interpretation_space_narrowing": "narrowing",
            "counterfactual_availability": "low",
            "intervention_headroom": "medium",
            "structural_openness": "fragile",
        }
    )
    assert result["pre_bind_preservation_summary"]["preservation_state"] == "degrading"


def test_preservation_collapsed_state() -> None:
    """No headroom and no recovery path should collapse preservation."""
    result = evaluate_pre_bind_preservation(
        {
            "interpretation_space_narrowing": "closed",
            "counterfactual_availability": "none",
            "intervention_headroom": "none",
            "structural_openness": "closed",
        }
    )
    assert result["pre_bind_preservation_summary"]["preservation_state"] == "collapsed"


def test_detection_crossed_but_preservation_open_boundary_case() -> None:
    """Detection participatory can coexist with preservation open."""
    signal = {
        "interpretation_space_narrowing": "open",
        "counterfactual_availability": "medium",
        "intervention_headroom": "medium",
        "structural_openness": "open",
    }
    detection = evaluate_pre_bind_structural_detection(signal)
    preservation = evaluate_pre_bind_preservation(
        signal,
        pre_bind_detection_summary=detection["pre_bind_detection_summary"],
    )
    assert detection["pre_bind_detection_summary"]["participation_state"] == "participatory"
    assert preservation["pre_bind_preservation_summary"]["preservation_state"] == "open"


def test_detection_participatory_can_be_degrading() -> None:
    """Moderate detection pressure can coincide with degrading preservation."""
    signal = {
        "interpretation_space_narrowing": "constrained",
        "counterfactual_availability": "low",
        "intervention_headroom": "medium",
        "structural_openness": "fragile",
    }
    detection = evaluate_pre_bind_structural_detection(signal)
    preservation = evaluate_pre_bind_preservation(
        signal,
        pre_bind_detection_summary=detection["pre_bind_detection_summary"],
    )
    assert detection["pre_bind_detection_summary"]["participation_state"] == "participatory"
    assert (
        preservation["pre_bind_preservation_summary"]["preservation_state"]
        == "degrading"
    )


def test_decision_shaping_can_collapse_preservation() -> None:
    """Decision shaping + poor recovery should classify collapsed preservation."""
    signal = {
        "interpretation_space_narrowing": "closed",
        "counterfactual_availability": "none",
        "intervention_headroom": "low",
        "structural_openness": "closed",
    }
    detection = evaluate_pre_bind_structural_detection(signal)
    preservation = evaluate_pre_bind_preservation(
        signal,
        pre_bind_detection_summary=detection["pre_bind_detection_summary"],
    )
    assert (
        detection["pre_bind_detection_summary"]["participation_state"]
        == "decision_shaping"
    )
    assert (
        preservation["pre_bind_preservation_summary"]["preservation_state"]
        == "collapsed"
    )


def test_high_activity_signals_do_not_force_collapsed_when_viable() -> None:
    """High interaction metadata must not collapse preservation without structural loss."""
    result = evaluate_pre_bind_preservation(
        {
            "interpretation_space_narrowing": "narrowing",
            "counterfactual_availability": "high",
            "intervention_headroom": "medium",
            "structural_openness": "partially_open",
            "interaction_turn_count": 1200,
            "message_rate_per_minute": 250,
        }
    )
    assert result["pre_bind_preservation_summary"]["preservation_state"] != "collapsed"


def test_pipeline_response_includes_optional_preservation_fields() -> None:
    """Response surface should include additive preservation summary/detail."""
    ctx = PipelineContext(
        request_id="req-preserve",
        query="test",
        response_extras={
            "participation_signal": {
                "interpretation_space_narrowing": "constrained",
                "counterfactual_availability": "low",
                "intervention_headroom": "medium",
                "structural_openness": "fragile",
            }
        },
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    assert "pre_bind_preservation_summary" in payload
    assert "pre_bind_preservation_detail" in payload
    assert payload["pre_bind_preservation_summary"]["preservation_family"] == (
        "pre_bind_preservation"
    )


def test_preservation_fields_optional_for_legacy_clients() -> None:
    """Legacy DecideResponse payloads remain valid without preservation fields."""
    legacy = DecideResponse(request_id="req-legacy-preservation")
    assert legacy.pre_bind_preservation_summary is None
    assert legacy.pre_bind_preservation_detail is None


def test_bind_contract_unchanged_with_preservation_fields() -> None:
    """Bind fields remain unchanged when preservation fields are present."""
    response = DecideResponse(
        request_id="req-preserve-bind-compat",
        bind_outcome="COMMITTED",
        bind_reason_code="OK",
        bind_failure_reason=None,
        pre_bind_preservation_summary={
            "preservation_state": "degrading",
            "preservation_outcome": "degrading",
            "intervention_viability": "minimal",
            "openness_floor": "at_risk",
            "counterfactual_recovery_possible": False,
            "main_contributing_conditions": ["structural_openness"],
        },
        pre_bind_preservation_detail={
            "normalized_signal_levels": {
                "interpretation_space_narrowing": "constrained",
                "counterfactual_availability": "low",
                "intervention_headroom": "low",
                "structural_openness": "fragile",
            },
            "intervention_viability": {
                "level": "minimal",
                "meaningful_intervention_possible": True,
            },
            "openness_floor": {
                "status": "at_risk",
                "structural_openness_level": "fragile",
            },
            "counterfactual_recovery_possible": False,
            "detection_context": {"participation_state": "participatory"},
            "main_contributing_conditions": ["structural_openness"],
        },
    )
    assert response.bind_outcome == "COMMITTED"
    assert response.bind_reason_code == "OK"


def test_preservation_summary_schema_naming_stable() -> None:
    """Schema naming should remain explicit and stable."""
    response = DecideResponse(
        request_id="req-preserve-schema",
        pre_bind_preservation_summary={
            "preservation_state": "open",
            "preservation_outcome": "open",
            "intervention_viability": "high",
            "openness_floor": "met",
            "counterfactual_recovery_possible": True,
        },
    )
    dumped = response.model_dump(exclude_none=True)
    assert "pre_bind_preservation_summary" in dumped
    assert dumped["pre_bind_preservation_summary"]["preservation_family"] == (
        "pre_bind_preservation"
    )
