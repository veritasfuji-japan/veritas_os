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


def test_structurally_refused_transition_cannot_be_actionable_after_bind(
    monkeypatch,
) -> None:
    ctx = PipelineContext(request_id="req-1", query="q")

    monkeypatch.setattr(
        pipeline_response,
        "assemble_governance_public_fields",
        lambda _snapshot: {
            "lineage_promotability": {
                "promotability_status": "non_promotable",
                "reason_code": "NON_PROMOTABLE_LINEAGE",
            }
        },
    )
    monkeypatch.setattr(
        pipeline_response,
        "_derive_business_fields",
        lambda _ctx: {
            "actionability_status": "actionable_after_bind",
            "requires_bind_before_execution": True,
            "execution_intent_id": "ei-1",
            "bound_execution_intent_id": "ei-1",
            "bind_receipt_id": "br-1",
            "bind_receipt": {"bind_receipt_id": "br-1"},
        },
    )

    layers = pipeline_response._build_response_layers(  # noqa: SLF001
        ctx,
        load_persona_fn=lambda: {},
        plan={},
    )
    core = layers["core"]
    assert core["transition_refusal"]["transition_status"] == "structurally_refused"
    assert core["execution_intent_id"] is None
    assert core["bind_receipt_id"] is None
    assert core["bind_receipt"] is None
    assert core["actionability_status"] != "actionable_after_bind"
    assert core["actionability_status"] == "formation_transition_refused"
    assert core["requires_bind_before_execution"] is False
    assert core["actionability_block_reason"] == "FORMATION_TRANSITION_REFUSED"
    assert (
        core["actionability_refusal_type"]
        == "pre_bind_formation_transition_refusal"
    )
    assert core["business_decision"] == "HOLD"
    assert core["next_action"] == "RECONSTRUCT_FROM_ELIGIBLE_FORMATION_LINEAGE"
    assert core["human_review_required"] is True
    assert (
        core["action_selection"]["selected"]["action"]
        == "RECONSTRUCT_FROM_ELIGIBLE_FORMATION_LINEAGE"
    )


def test_raw_committed_bind_payload_cannot_override_structural_refusal(
    monkeypatch,
) -> None:
    ctx = PipelineContext(request_id="req-1", query="q")
    ctx.raw = {
        "bind_outcome": "COMMITTED",
        "execution_intent_id": "ei-1",
        "bind_receipt_id": "br-1",
        "bind_receipt": {"bind_receipt_id": "br-1"},
    }

    monkeypatch.setattr(
        pipeline_response,
        "assemble_governance_public_fields",
        lambda _snapshot: {
            "lineage_promotability": {
                "promotability_status": "non_promotable",
                "reason_code": "NON_PROMOTABLE_LINEAGE",
            }
        },
    )

    layers = pipeline_response._build_response_layers(  # noqa: SLF001
        ctx,
        load_persona_fn=lambda: {},
        plan={},
    )
    core = layers["core"]
    assert core["actionability_status"] == "formation_transition_refused"
    assert core["execution_intent_id"] is None
    assert core["bind_receipt_id"] is None
    assert core["bind_receipt"] is None
    assert core["bound_execution_intent_id"] is None
    assert core["transition_refusal"]["reason_code"] == "NON_PROMOTABLE_LINEAGE"


def test_promotable_lineage_keeps_existing_actionability_behavior(monkeypatch) -> None:
    ctx = PipelineContext(request_id="req-1", query="q")
    monkeypatch.setattr(
        pipeline_response,
        "assemble_governance_public_fields",
        lambda _snapshot: {
            "lineage_promotability": {"promotability_status": "promotable"}
        },
    )
    monkeypatch.setattr(
        pipeline_response,
        "_derive_business_fields",
        lambda _ctx: {
            "actionability_status": "actionable_after_bind",
            "requires_bind_before_execution": False,
            "business_decision": "APPROVE",
            "next_action": "EXECUTE_WITH_STANDARD_MONITORING",
            "human_review_required": False,
            "action_selection": {
                "evaluation_axes": ["expected_value"],
                "selected": {"action": "EXECUTE_WITH_STANDARD_MONITORING"},
                "candidates_considered": 1,
            },
        },
    )

    layers = pipeline_response._build_response_layers(  # noqa: SLF001
        ctx,
        load_persona_fn=lambda: {},
        plan={},
    )
    core = layers["core"]
    assert core["transition_refusal"] is None
    assert core["actionability_status"] == "actionable_after_bind"
    assert core["requires_bind_before_execution"] is False
    assert core["business_decision"] == "APPROVE"
    assert core["next_action"] == "EXECUTE_WITH_STANDARD_MONITORING"
    assert core["human_review_required"] is False
    assert (
        core["action_selection"]["selected"]["action"]
        == "EXECUTE_WITH_STANDARD_MONITORING"
    )


def test_structural_refusal_overrides_execute_selected_action(monkeypatch) -> None:
    ctx = PipelineContext(request_id="req-1", query="q")
    monkeypatch.setattr(
        pipeline_response,
        "assemble_governance_public_fields",
        lambda _snapshot: {
            "lineage_promotability": {"promotability_status": "non_promotable"}
        },
    )
    monkeypatch.setattr(
        pipeline_response,
        "_derive_business_fields",
        lambda _ctx: {
            "business_decision": "APPROVE",
            "next_action": "EXECUTE_WITH_STANDARD_MONITORING",
            "human_review_required": False,
            "action_selection": {
                "evaluation_axes": ["expected_value"],
                "selected": {"action": "EXECUTE_WITH_STANDARD_MONITORING"},
                "candidates_considered": 1,
            },
        },
    )
    layers = pipeline_response._build_response_layers(  # noqa: SLF001
        ctx,
        load_persona_fn=lambda: {},
        plan={},
    )
    core = layers["core"]
    assert core["business_decision"] == "HOLD"
    assert core["next_action"] == "RECONSTRUCT_FROM_ELIGIBLE_FORMATION_LINEAGE"
    assert (
        core["action_selection"]["selected"]["action"]
        == "RECONSTRUCT_FROM_ELIGIBLE_FORMATION_LINEAGE"
    )
    assert (
        core["action_selection"]["selected"]["action"]
        != "EXECUTE_WITH_STANDARD_MONITORING"
    )


def test_structural_refusal_includes_formation_transition_refused_reason(
    monkeypatch,
) -> None:
    ctx = PipelineContext(request_id="req-1", query="q")
    monkeypatch.setattr(
        pipeline_response,
        "assemble_governance_public_fields",
        lambda _snapshot: {
            "lineage_promotability": {"promotability_status": "non_promotable"}
        },
    )
    layers = pipeline_response._build_response_layers(  # noqa: SLF001
        ctx,
        load_persona_fn=lambda: {},
        plan={},
    )
    core = layers["core"]
    refusal_reason = str(core.get("refusal_reason") or "")
    rationale = str(core.get("rationale") or "")
    assert (
        "FORMATION_TRANSITION_REFUSED" in refusal_reason
        or "FORMATION_TRANSITION_REFUSED" in rationale
    )
