from veritas_os.core.pipeline.pipeline_response import assemble_response
from veritas_os.core.pipeline.pipeline_types import PipelineContext


def test_assemble_response_includes_public_decision_semantics() -> None:
    """公開レスポンスで判定状態と次アクションを分離して返す。"""
    ctx = PipelineContext(
        request_id="req-1",
        query="test",
        fuji_dict={"decision_status": "allow", "status": "needs_human_review"},
        decision_status="allow",
        rejection_reason=None,
        context={
            "required_evidence": ["risk_assessment", "approval_ticket"],
            "satisfied_evidence": ["risk_assessment"],
        },
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    assert payload["gate_decision"] == "allow"
    assert payload["business_decision"] == "EVIDENCE_REQUIRED"
    assert payload["next_action"] == "COLLECT_REQUIRED_EVIDENCE"
    assert payload["required_evidence"] == ["risk_assessment", "approval_ticket"]
    assert payload["missing_evidence"] == ["approval_ticket"]
    assert payload["human_review_required"] is True


def test_business_decision_is_state_not_action_sentence() -> None:
    """business_decision は案件状態 enum を維持し action 文を含めない。"""
    ctx = PipelineContext(
        request_id="req-2",
        query="test",
        fuji_dict={"decision_status": "deny", "status": "deny"},
        decision_status="rejected",
        rejection_reason="policy_violation",
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    assert payload["business_decision"] == "DENY"
    assert payload["business_decision"] in {
        "APPROVE",
        "DENY",
        "HOLD",
        "REVIEW_REQUIRED",
        "POLICY_DEFINITION_REQUIRED",
        "EVIDENCE_REQUIRED",
    }
    assert payload["next_action"] == "DO_NOT_EXECUTE"
