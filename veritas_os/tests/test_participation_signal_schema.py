"""Schema tests for additive pre-bind participation signals."""

from __future__ import annotations

from veritas_os.api.schemas import DecideResponse
from veritas_os.api.schemas import ParticipationSignal
from veritas_os.core.pipeline.pipeline_response import assemble_response
from veritas_os.core.pipeline.pipeline_types import PipelineContext


def test_participation_signal_serialization_roundtrip() -> None:
    """ParticipationSignal should serialize/deserialize with canonical vocabulary."""
    signal = ParticipationSignal(
        interpretation_space_narrowing="narrowing",
        counterfactual_availability="high",
        intervention_headroom="medium",
        structural_openness="partially_open",
        participation_admissibility="review_required",
        evidence_refs=["ev-1"],
    )
    payload = signal.model_dump()
    restored = ParticipationSignal.model_validate(payload)

    assert restored.signal_family == "participation_signal"
    assert restored.interpretation_space_narrowing == "narrowing"
    assert restored.counterfactual_availability == "high"
    assert restored.evidence_refs == ["ev-1"]


def test_participation_signal_is_optional_and_additive_on_decide_response() -> None:
    """Existing DecideResponse contract remains valid without participation signal."""
    legacy = DecideResponse(request_id="req-legacy")
    assert legacy.participation_signal is None
    assert legacy.bind_summary is None

    enriched = DecideResponse(
        request_id="req-enriched",
        participation_signal={
            "interpretation_space_narrowing": "constrained",
            "counterfactual_availability": "low",
            "intervention_headroom": "low",
            "structural_openness": "fragile",
            "participation_admissibility": "review_required",
        },
    )
    assert enriched.participation_signal is not None
    assert enriched.participation_signal.signal_family == "participation_signal"


def test_participation_signal_schema_name_integrity() -> None:
    """Schema should keep explicit first-class naming and not generic signal labels."""
    signal = ParticipationSignal()
    dumped = signal.model_dump()
    assert "participation_signal_id" in dumped
    assert dumped["signal_family"] == "participation_signal"
    assert "interpretation_space_narrowing" in dumped
    assert "counterfactual_availability" in dumped
    assert "intervention_headroom" in dumped
    assert "structural_openness" in dumped


def test_pipeline_response_accepts_optional_participation_signal_hook() -> None:
    """Response assembly should pass through additive participation signal hook."""
    ctx = PipelineContext(
        request_id="req-hook",
        query="test",
        response_extras={
            "participation_signal": {
                "interpretation_space_narrowing": "open",
                "counterfactual_availability": "medium",
                "intervention_headroom": "medium",
                "structural_openness": "open",
                "participation_admissibility": "admissible",
            }
        },
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    assert "participation_signal" in payload
    assert payload["participation_signal"]["participation_admissibility"] == "admissible"


def test_bind_contract_fields_remain_unchanged_with_participation_signal() -> None:
    """Additive participation signal must not mutate existing bind contract fields."""
    resp = DecideResponse(
        request_id="req-bind-compat",
        bind_outcome="BLOCKED",
        bind_reason_code="CONSTRAINT_MISMATCH",
        bind_failure_reason="constraint mismatch",
        participation_signal={"participation_admissibility": "unknown"},
    )
    assert resp.bind_outcome == "BLOCKED"
    assert resp.bind_reason_code == "CONSTRAINT_MISMATCH"
    assert resp.bind_failure_reason == "constraint mismatch"
