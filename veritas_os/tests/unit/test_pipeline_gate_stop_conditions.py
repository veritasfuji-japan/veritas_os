# -*- coding: utf-8 -*-
"""Regression tests for FUJI gate stop-condition hardening."""

from veritas_os.core.pipeline.pipeline_policy import stage_gate_decision
from veritas_os.core.pipeline.pipeline_types import PipelineContext


def _make_context() -> PipelineContext:
    """Create a minimal pipeline context usable by stage_gate_decision."""
    return PipelineContext(
        request_id="gate-stop-conditions",
        query="test",
        fuji_dict={"status": "allow", "risk": 0.2},
        decision_status="allow",
        context={},
        response_extras={"metrics": {"stage_latency": {}}},
    )


def test_stage_gate_decision_holds_when_required_evidence_is_missing() -> None:
    """Required evidence gaps should fail closed to hold, not allow."""
    ctx = _make_context()
    ctx.context = {
        "required_evidence": ["risk_assessment", "approval_ticket"],
        "satisfied_evidence": ["risk_assessment"],
    }

    stage_gate_decision(ctx)

    assert ctx.decision_status == "hold"
    assert ctx.rejection_reason is not None
    assert "required_evidence_missing" in ctx.rejection_reason
    assert ctx.context.get("human_review_required") is True


def test_stage_gate_decision_rejects_irreversible_action_without_audit_trail() -> None:
    """Irreversible action without audit evidence should be rejected."""
    ctx = _make_context()
    ctx.context = {
        "irreversible_action": True,
        "audit_trail_complete": False,
    }

    stage_gate_decision(ctx)

    assert ctx.decision_status == "rejected"
    assert ctx.rejection_reason == "FUJI gate: irreversible_action_without_audit_trail"
    assert ctx.chosen == {}
    assert ctx.alternatives == []

