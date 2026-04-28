"""Tests for additive pre-bind structural participation detection."""

from __future__ import annotations

from veritas_os.api.schemas import DecideResponse
from veritas_os.core.participation_detection import (
    evaluate_pre_bind_structural_detection,
)
from veritas_os.core.pipeline.pipeline_response import assemble_response
from veritas_os.core.pipeline.pipeline_types import PipelineContext


def test_classifies_informative_state() -> None:
    """Low structural signal levels should stay informative."""
    detection = evaluate_pre_bind_structural_detection(
        {
            "interpretation_space_narrowing": "open",
            "counterfactual_availability": "high",
            "intervention_headroom": "high",
            "structural_openness": "open",
        }
    )

    assert detection["pre_bind_detection_summary"]["participation_state"] == "informative"


def test_classifies_participatory_state() -> None:
    """Moderate structural signal pressure should classify as participatory."""
    detection = evaluate_pre_bind_structural_detection(
        {
            "interpretation_space_narrowing": "narrowing",
            "counterfactual_availability": "medium",
            "intervention_headroom": "medium",
            "structural_openness": "partially_open",
        }
    )

    assert detection["pre_bind_detection_summary"]["participation_state"] == "participatory"


def test_classifies_decision_shaping_state() -> None:
    """Multi-signal severe constraint should classify as decision_shaping."""
    detection = evaluate_pre_bind_structural_detection(
        {
            "interpretation_space_narrowing": "closed",
            "counterfactual_availability": "none",
            "intervention_headroom": "low",
            "structural_openness": "closed",
        }
    )

    assert (
        detection["pre_bind_detection_summary"]["participation_state"]
        == "decision_shaping"
    )


def test_ambiguous_case_avoids_over_detection() -> None:
    """Mixed but not severe structural signals should not jump to decision shaping."""
    detection = evaluate_pre_bind_structural_detection(
        {
            "interpretation_space_narrowing": "constrained",
            "counterfactual_availability": "medium",
            "intervention_headroom": "medium",
            "structural_openness": "partially_open",
        }
    )

    assert detection["pre_bind_detection_summary"]["participation_state"] == "participatory"


def test_high_frequency_metadata_does_not_trigger_decision_shaping() -> None:
    """Non-structural interaction frequency metadata must not drive state elevation."""
    detection = evaluate_pre_bind_structural_detection(
        {
            "interpretation_space_narrowing": "open",
            "counterfactual_availability": "high",
            "intervention_headroom": "high",
            "structural_openness": "open",
            "interaction_turn_count": 999,
            "message_rate_per_minute": 120,
        }
    )

    assert detection["pre_bind_detection_summary"]["participation_state"] == "informative"


def test_low_signal_case_remains_informative() -> None:
    """Default-like structural signal profile should remain informative."""
    detection = evaluate_pre_bind_structural_detection({})

    assert detection["pre_bind_detection_summary"]["participation_state"] == "informative"


def test_pipeline_response_includes_optional_pre_bind_detection_fields() -> None:
    """Response surface should include additive pre-bind summary/detail when signal exists."""
    ctx = PipelineContext(
        request_id="req-prebind",
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
    assert payload["pre_bind_detection_summary"]["participation_state"] == "participatory"
    assert "pre_bind_detection_detail" in payload


def test_pre_bind_detection_fields_are_optional_for_legacy_clients() -> None:
    """Legacy DecideResponse payloads should validate without new additive fields."""
    legacy = DecideResponse(request_id="req-legacy-detection")
    assert legacy.pre_bind_detection_summary is None
    assert legacy.pre_bind_detection_detail is None


def test_bind_contract_remains_unchanged_when_detection_fields_exist() -> None:
    """Bind outcome fields must remain stable when additive detection fields are present."""
    response = DecideResponse(
        request_id="req-bind-compat-detection",
        bind_outcome="ESCALATED",
        bind_reason_code="AUTHORITY_INSUFFICIENT",
        bind_failure_reason="authority evidence missing",
        pre_bind_detection_summary={
            "participation_state": "participatory",
            "primary_contributing_signals": ["structural_openness"],
            "concise_rationale": "impact emerging",
        },
        pre_bind_detection_detail={
            "normalized_signal_levels": {
                "interpretation_space_narrowing": "narrowing",
                "counterfactual_availability": "medium",
                "intervention_headroom": "medium",
                "structural_openness": "partially_open",
            },
            "signal_severity": {
                "interpretation_space_narrowing": 1,
                "counterfactual_availability": 1,
                "intervention_headroom": 1,
                "structural_openness": 1,
            },
            "aggregate_index": 0.3333,
            "high_signal_count": 0,
            "moderate_signal_count": 4,
        },
    )

    assert response.bind_outcome == "ESCALATED"
    assert response.bind_reason_code == "AUTHORITY_INSUFFICIENT"
    assert response.bind_failure_reason == "authority evidence missing"


def test_detection_summary_schema_naming_is_stable() -> None:
    """Detection schema naming should remain explicit and documented."""
    response = DecideResponse(
        request_id="req-schema-name",
        pre_bind_detection_summary={
            "participation_state": "informative",
            "primary_contributing_signals": [],
            "concise_rationale": "informative",
        },
    )

    dumped = response.model_dump(exclude_none=True)
    assert "pre_bind_detection_summary" in dumped
    assert dumped["pre_bind_detection_summary"]["detection_family"] == (
        "pre_bind_structural_detection"
    )
