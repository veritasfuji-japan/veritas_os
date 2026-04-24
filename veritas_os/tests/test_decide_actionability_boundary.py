"""Tests for reviewable vs actionable boundary semantics in decide responses."""

from __future__ import annotations

from veritas_os.api.schemas import DecideResponse
from veritas_os.core.pipeline.pipeline_response import assemble_response
from veritas_os.core.pipeline.pipeline_types import PipelineContext


def _build_payload(ctx: PipelineContext) -> dict:
    return assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )


def test_reviewable_decision_is_not_actionable_without_bind_receipt() -> None:
    ctx = PipelineContext(
        request_id="act-1",
        query="can we proceed",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
    )
    payload = _build_payload(ctx)

    assert payload["actionability_status"] == "bind_required_before_execution"
    assert payload["requires_bind_before_execution"] is True
    assert payload["bind_receipt_id"] is None
    assert payload["unbound_execution_warning"] is not None


def test_blocked_decision_is_not_actionable() -> None:
    ctx = PipelineContext(
        request_id="act-2",
        query="blocked",
        fuji_dict={"decision_status": "deny", "status": "deny"},
        decision_status="rejected",
        rejection_reason="policy_violation",
    )
    payload = _build_payload(ctx)

    assert payload["actionability_status"] == "blocked"
    assert payload["requires_bind_before_execution"] is False


def test_human_review_decision_is_not_actionable() -> None:
    ctx = PipelineContext(
        request_id="act-3",
        query="human review",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context={"approval_boundary_defined": False},
    )
    payload = _build_payload(ctx)

    assert payload["actionability_status"] == "human_review_required"
    assert payload["requires_bind_before_execution"] is True


def test_execution_like_next_action_still_requires_bind_when_unbound() -> None:
    ctx = PipelineContext(
        request_id="act-4",
        query="execute",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
    )
    payload = _build_payload(ctx)

    assert payload["next_action"] == "EXECUTE_WITH_STANDARD_MONITORING"
    assert payload["actionability_status"] == "bind_required_before_execution"
    assert payload["requires_bind_before_execution"] is True


def test_decide_response_validation_accepts_new_actionability_fields() -> None:
    payload = {
        "ok": True,
        "request_id": "act-5",
        "chosen": {},
        "actionability_status": "reviewable_only",
        "requires_bind_before_execution": True,
        "bound_execution_intent_id": None,
        "bind_receipt_id": None,
        "unbound_execution_warning": "bind needed",
    }

    parsed = DecideResponse.model_validate(payload)

    assert parsed.actionability_status == "reviewable_only"
    assert parsed.requires_bind_before_execution is True
