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
    assert "next_action_reason=" in payload["rationale"]
    assert payload["action_selection"]["selected"]["action"] == payload["next_action"]


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
    assert payload["action_selection"]["selected"]["action"] == "DO_NOT_EXECUTE"


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
    assert payload["next_action"] == "DO_NOT_EXECUTE"
    assert payload["next_action"] != "EXECUTE_WITH_STANDARD_MONITORING"


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
    assert payload["next_action"] == "DO_NOT_EXECUTE"


def test_next_action_is_selected_from_ranked_candidates() -> None:
    """next_action は候補比較の上位案から選ばれる。"""
    ctx = PipelineContext(
        request_id="req-8",
        query="通常実行できるか",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context={"dev_mode": True},
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    candidates = payload["action_candidates"]
    assert len(candidates) >= 2
    assert candidates[0]["score"] >= candidates[1]["score"]
    assert payload["next_action"] == candidates[0]["action"]
    assert payload["action_selection"]["evaluation_axes"] == [
        "expected_value",
        "risk_reduction",
        "cost",
        "dependency",
        "urgency",
    ]


def test_question_first_structured_answer_is_returned_before_next_action() -> None:
    """境界条件/必要証拠の質問には構造化回答を返してから次アクションを示す。"""
    ctx = PipelineContext(
        request_id="req-9",
        query="最低条件と境界条件と必要証拠は何？",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context={
            "required_evidence": ["risk_assessment", "approval_ticket"],
            "satisfied_evidence": ["risk_assessment"],
            "approval_boundary_defined": False,
            "dev_mode": True,
        },
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    assert "structured_answer" in payload
    structured = payload["structured_answer"]
    assert structured["minimum_conditions"]["missing_evidence_count"] == 1
    assert "approval_boundary_unknown" in structured["boundary_conditions"]["stop_reasons"]
    assert payload["next_action"] == payload["action_candidates"][0]["action"]


def test_non_dev_mode_hides_action_candidates() -> None:
    """action_candidates は非devモードでは公開しない。"""
    ctx = PipelineContext(
        request_id="req-10",
        query="test",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context={},
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    assert payload["action_candidates"] == []


def test_missing_required_evidence_never_returns_approve() -> None:
    """required_evidence 欠損時は APPROVE を返さない。"""
    ctx = PipelineContext(
        request_id="req-11",
        query="実行してよいか？",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context={
            "required_evidence": ["approval_ticket", "audit_log_ref"],
            "satisfied_evidence": ["approval_ticket"],
        },
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    assert payload["gate_decision"] == "hold"
    assert payload["business_decision"] == "EVIDENCE_REQUIRED"
    assert payload["business_decision"] != "APPROVE"


def test_required_evidence_alias_is_not_misclassified_as_missing() -> None:
    """Alias/canonical 表記ゆれで required_evidence_missing を誤検知しない。"""
    ctx = PipelineContext(
        request_id="req-11b",
        query="証拠は足りているか？",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context={
            "required_evidence": ["source_of_funds_document"],
            "satisfied_evidence": ["source_of_funds_record"],
        },
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    assert payload["missing_evidence"] == []
    assert payload["business_decision"] == "APPROVE"


def test_high_risk_ambiguity_forces_human_review() -> None:
    """高リスク曖昧案件は human_review_required=true を強制する。"""
    ctx = PipelineContext(
        request_id="req-12",
        query="重大影響だが確証がない案件を通すべきか",
        fuji_dict={"decision_status": "allow", "status": "allow", "risk": 0.92},
        decision_status="allow",
        rejection_reason=None,
        context={
            "ambiguity_detected": True,
            "risk_score": 0.91,
            "required_evidence": ["decision_rationale"],
            "satisfied_evidence": ["decision_rationale"],
        },
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    assert payload["gate_decision"] == "human_review_required"
    assert payload["business_decision"] == "REVIEW_REQUIRED"
    assert payload["human_review_required"] is True


def test_irreversible_action_without_audit_trail_is_blocked() -> None:
    """不可逆アクションかつ監査証跡不足は BLOCK に倒す。"""
    ctx = PipelineContext(
        request_id="req-13",
        query="監査なしで不可逆実行してよいか",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context={
            "irreversible_action": True,
            "audit_trail_complete": False,
        },
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    assert payload["gate_decision"] == "block"
    assert payload["business_decision"] == "DENY"
    assert payload["next_action"] == "DO_NOT_EXECUTE"


def test_sanctions_partial_match_never_proceeds() -> None:
    """Sanctions partial match case must not return proceed."""
    ctx = PipelineContext(
        request_id="req-14",
        query="制裁リスト部分一致。送金を進めてよいか",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context={
            "required_evidence": [
                "beneficiary_date_of_birth",
                "beneficiary_address",
                "sanctions_screening_trace",
            ],
            "satisfied_evidence": ["sanctions_trace"],
            "high_risk_ambiguity": True,
            "risk_score": 0.66,
            "human_review_required": True,
        },
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    assert payload["gate_decision"] != "proceed"
    assert payload["business_decision"] == "EVIDENCE_REQUIRED"


def test_source_of_funds_missing_never_approves() -> None:
    """Missing source-of-funds evidence must not return APPROVE."""
    ctx = PipelineContext(
        request_id="req-15",
        query="高額送金の source of funds が未提出。承認できるか",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context={
            "required_evidence": ["kyc_profile", "source_of_funds_document"],
            "satisfied_evidence": ["kyc_profile"],
        },
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    assert payload["required_evidence"] == ["kyc_profile", "source_of_funds_record"]
    assert payload["missing_evidence"] == ["source_of_funds_record"]
    assert payload["business_decision"] != "APPROVE"
