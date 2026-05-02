"""Tests for pre-bind execution-intent transition refusal behavior."""

from __future__ import annotations

from veritas_os.core.lineage_transition_refusal import (
    evaluate_execution_intent_transition,
)
from veritas_os.core.pipeline import pipeline_response
from veritas_os.core.pipeline.pipeline_types import PipelineContext


def test_non_promotable_lineage_refuses_transition() -> None:
    result = evaluate_execution_intent_transition(
        lineage_promotability={
            "promotability_status": "non_promotable",
            "reason_code": "NON_PROMOTABLE_LINEAGE",
            "invariant_id": (
                "BIND_ELIGIBLE_ARTIFACT_CANNOT_EMERGE_FROM_NON_PROMOTABLE_LINEAGE"
            ),
        }
    )
    assert result["transition_status"] == "structurally_refused"
    assert result["reason_code"] == "NON_PROMOTABLE_LINEAGE"
    assert result["execution_intent_created"] is False
    assert result["bind_receipt_created"] is False


def test_promotable_lineage_allows_transition() -> None:
    result = evaluate_execution_intent_transition(
        lineage_promotability={"promotability_status": "promotable"}
    )
    assert result["transition_status"] == "allowed"
    assert result["reason_code"] is None


def test_missing_lineage_promotability_remains_allowed() -> None:
    result = evaluate_execution_intent_transition(lineage_promotability=None)
    assert result["transition_status"] == "allowed"
    assert result["reason_code"] is None


def test_pipeline_response_refuses_non_promotable_execution_intent_transition(
    monkeypatch,
) -> None:
    ctx = PipelineContext(request_id="req-1", query="q")
    ctx.raw = {"execution_intent_id": "ei-1", "bind_receipt_id": "br-1"}

    monkeypatch.setattr(
        pipeline_response,
        "assemble_governance_public_fields",
        lambda _snapshot: {
            "lineage_promotability": {"promotability_status": "non_promotable"}
        },
    )
    monkeypatch.setattr(pipeline_response, "_derive_business_fields", lambda _ctx: {
        "execution_intent_id": "ei-1",
        "bound_execution_intent_id": "ei-1",
        "bind_receipt_id": "br-1",
        "bind_receipt": {"bind_receipt_id": "br-1"},
    })
    layers = pipeline_response._build_response_layers(  # noqa: SLF001
        ctx,
        load_persona_fn=lambda: {},
        plan={},
    )
    core = layers["core"]
    assert core["transition_refusal"]["transition_status"] == "structurally_refused"
    assert core["execution_intent_id"] is None
    assert core["bind_receipt_id"] is None
