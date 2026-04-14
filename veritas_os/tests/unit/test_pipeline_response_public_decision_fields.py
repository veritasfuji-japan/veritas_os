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

    assert payload["gate_decision"] == "hold"
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


def test_gate_decision_becomes_hold_when_rule_definition_is_missing() -> None:
    """ルール未定義は fail-closed で HOLD 側に倒す。"""
    ctx = PipelineContext(
        request_id="req-3",
        query="test",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason="policy_definition_required: route policy missing",
        context={"rule_defined": False},
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    assert payload["gate_decision"] == "hold"
    assert payload["business_decision"] == "HOLD"
    assert "rule_undefined" in payload["rationale"]


def test_gate_decision_requires_human_review_when_approval_boundary_unknown() -> None:
    """approval boundary が不明な案件は人手審査を必須化する。"""
    ctx = PipelineContext(
        request_id="req-4",
        query="test",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context={"approval_boundary_defined": False},
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    assert payload["gate_decision"] == "human_review_required"
    assert payload["business_decision"] == "REVIEW_REQUIRED"
    assert payload["human_review_required"] is True


def test_gate_decision_blocks_when_rollback_is_not_supported() -> None:
    """rollback 不能変更は BLOCK とする。"""
    ctx = PipelineContext(
        request_id="req-5",
        query="test",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context={"rollback_supported": False},
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    assert payload["gate_decision"] == "block"
    assert payload["business_decision"] == "DENY"
    assert payload["refusal_reason"] is not None
    assert "rollback_not_supported" in payload["refusal_reason"]


def test_refusal_reason_and_missing_evidence_are_exposed() -> None:
    """停止理由と不足証拠が外部レスポンスに残ることを保証する。"""
    ctx = PipelineContext(
        request_id="req-6",
        query="test",
        fuji_dict={"decision_status": "deny", "status": "deny"},
        decision_status="rejected",
        rejection_reason="policy_violation",
        context={
            "required_evidence": ["approval_ticket"],
            "satisfied_evidence": [],
            "audit_trail_complete": False,
        },
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    assert payload["gate_decision"] == "block"
    assert payload["missing_evidence"] == ["approval_ticket"]
    assert payload["refusal_reason"] is not None
    assert "required_evidence_missing" in payload["refusal_reason"]


def test_secure_prod_control_gap_fails_closed_to_block() -> None:
    """secure/prod 制御不足は fail-closed で BLOCK になる。"""
    ctx = PipelineContext(
        request_id="req-7",
        query="test",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context={
            "environment": "prod",
            "production_controls_ready": False,
        },
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    assert payload["gate_decision"] == "block"
    assert payload["business_decision"] == "DENY"
