from pydantic import ValidationError

from veritas_os.api.schemas import DecideResponse
from veritas_os.core.decision_semantics import (
    CANONICAL_GATE_DECISION_VALUES,
    COMPATIBLE_GATE_DECISION_VALUES,
    FORBIDDEN_GATE_BUSINESS_COMBINATIONS,
    LEGACY_GATE_DECISION_ALIASES,
    build_required_evidence_profile,
    canonicalize_public_gate_decision,
)
from veritas_os.core.pipeline.pipeline_response import assemble_response
from veritas_os.core.pipeline.pipeline_types import PipelineContext


def test_canonical_contract_source_of_truth_values_are_stable() -> None:
    """Canonical and compatibility gate values should be centralized and explicit."""
    assert CANONICAL_GATE_DECISION_VALUES == (
        "proceed",
        "hold",
        "block",
        "human_review_required",
    )
    assert LEGACY_GATE_DECISION_ALIASES == (
        "allow",
        "deny",
        "modify",
        "rejected",
        "abstain",
    )
    assert COMPATIBLE_GATE_DECISION_VALUES == (
        "proceed",
        "hold",
        "block",
        "human_review_required",
        "allow",
        "deny",
        "modify",
        "rejected",
        "abstain",
        "unknown",
    )


def test_legacy_aliases_are_compatibility_only_inputs() -> None:
    """Legacy aliases must normalize to canonical values for public semantics."""
    expected_map = {
        "allow": "proceed",
        "deny": "block",
        "modify": "hold",
        "rejected": "block",
        "abstain": "hold",
    }
    assert set(expected_map) == set(LEGACY_GATE_DECISION_ALIASES)
    for raw, expected in expected_map.items():
        assert canonicalize_public_gate_decision(raw) == expected


def test_gate_decision_alias_is_canonicalized_in_schema() -> None:
    """Legacy gate aliases should normalize to canonical public semantics."""
    cases = {
        "allow": "proceed",
        "deny": "block",
        "rejected": "block",
        "modify": "hold",
        "abstain": "hold",
    }
    for raw, canonical in cases.items():
        payload = DecideResponse.model_validate(
            {
                "gate_decision": raw,
                "business_decision": "DENY" if canonical == "block" else "HOLD",
                "human_review_required": False,
            }
        )
        assert payload.gate_decision == canonical


def test_forbidden_gate_business_combination_is_rejected() -> None:
    """Invalid gate/business combinations must be blocked at validation."""
    try:
        DecideResponse.model_validate(
            {
                "gate_decision": "proceed",
                "business_decision": "DENY",
            }
        )
    except ValidationError as exc:
        assert "forbidden gate/business combination" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("ValidationError was expected")


def test_forbidden_pair_table_is_centralized_and_enforced() -> None:
    """Forbidden gate/business pairs should stay defined in one canonical table."""
    assert FORBIDDEN_GATE_BUSINESS_COMBINATIONS == frozenset(
        {
            ("block", "APPROVE"),
            ("hold", "APPROVE"),
            ("proceed", "DENY"),
        }
    )


def test_review_required_requires_human_review_required_true() -> None:
    """REVIEW_REQUIRED requires explicit human_review_required=true."""
    try:
        DecideResponse.model_validate(
            {
                "gate_decision": "human_review_required",
                "business_decision": "REVIEW_REQUIRED",
                "human_review_required": False,
            }
        )
    except ValidationError as exc:
        message = str(exc)
        assert (
            "business_decision=REVIEW_REQUIRED" in message
            or "gate_decision=human_review_required" in message
        )
    else:  # pragma: no cover
        raise AssertionError("ValidationError was expected")


def test_gate_human_review_required_requires_boolean_true() -> None:
    """gate_decision=human_review_required cannot be combined with false flag."""
    try:
        DecideResponse.model_validate(
            {
                "gate_decision": "human_review_required",
                "business_decision": "HOLD",
                "human_review_required": False,
            }
        )
    except ValidationError as exc:
        message = str(exc)
        assert "gate_decision=human_review_required" in message
    else:  # pragma: no cover
        raise AssertionError("ValidationError was expected")


def test_proceed_requires_human_review_false() -> None:
    """Proceed gate should not carry human-review required=true."""
    try:
        DecideResponse.model_validate(
            {
                "gate_decision": "proceed",
                "business_decision": "APPROVE",
                "human_review_required": True,
            }
        )
    except ValidationError as exc:
        assert "gate_decision=proceed" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("ValidationError was expected")


def test_stop_reason_priority_prefers_block_over_required_evidence() -> None:
    """Block-priority stop reasons must override evidence-hold reasons."""
    ctx = PipelineContext(
        request_id="req-stop-priority",
        query="test",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        context={
            "rollback_supported": False,
            "required_evidence": ["approval_ticket"],
            "satisfied_evidence": [],
        },
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    assert payload["gate_decision"] == "block"
    assert payload["business_decision"] == "EVIDENCE_REQUIRED"
    assert "rollback_not_supported" in payload["rationale"]


def test_required_evidence_taxonomy_aliases_are_normalized() -> None:
    """Taxonomy aliases should be treated equivalent for missing detection."""
    ctx = PipelineContext(
        request_id="req-taxonomy",
        query="test",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        context={
            "required_evidence": ["bureau_report", "approval_boundary_matrix"],
            "satisfied_evidence": ["credit_bureau_report"],
        },
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    assert payload["required_evidence"] == ["credit_bureau_report", "approval_matrix"]
    assert payload["missing_evidence"] == ["approval_matrix"]


def test_public_response_prefers_canonical_gate_decision() -> None:
    """Public response should expose canonical gate_decision instead of legacy allow."""
    ctx = PipelineContext(
        request_id="req-gate-canonical-output",
        query="test canonical gate",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        context={},
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    assert payload["gate_decision"] == "proceed"


def test_public_response_avoids_unknown_in_normal_runtime_path() -> None:
    """Unknown FUJI status should still resolve into canonical public gate decision."""
    ctx = PipelineContext(
        request_id="req-gate-unknown-normalized",
        query="test unknown gate",
        fuji_dict={"decision_status": "totally_unknown_status", "status": "totally_unknown_status"},
        decision_status="totally_unknown_status",
        context={},
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    assert payload["gate_decision"] == "proceed"


def test_backward_compat_decision_status_stays_legacy_field() -> None:
    """decision_status remains distinct from public gate semantics."""
    payload = DecideResponse.model_validate(
        {
            "decision_status": "allow",
            "gate_decision": "allow",
            "business_decision": "APPROVE",
            "human_review_required": False,
        }
    )

    assert payload.decision_status == "allow"
    assert payload.gate_decision == "proceed"


def test_aml_kyc_evidence_profile_classifies_requirement_levels() -> None:
    """AML/KYC profile should classify required/escalation-sensitive keys."""
    entries = build_required_evidence_profile(
        ["kyc_profile", "sanctions_trace", "custom_free_text"],
        decision_domain="aml_kyc",
    )
    by_key = {entry["key"]: entry for entry in entries}

    assert by_key["kyc_profile"]["requirement_level"] == "required"
    assert by_key["sanctions_screening_trace"]["requirement_level"] in {
        "required",
        "escalation_sensitive",
    }
    assert by_key["custom_free_text"]["requirement_level"] == "unclassified"


def test_aml_kyc_profile_required_keys_are_enforced_in_runtime() -> None:
    """AML/KYC profile keys should be added to required_evidence at runtime."""
    ctx = PipelineContext(
        request_id="req-aml-profile-hardening",
        query="aml profile hardening",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        context={
            "decision_domain": "aml_kyc",
            "required_evidence": ["kyc_profile"],
            "satisfied_evidence": ["kyc_profile"],
        },
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    assert "source_of_funds_record" in payload["required_evidence"]
    assert "source_of_funds_record" in payload["missing_evidence"]
    assert payload["business_decision"] == "EVIDENCE_REQUIRED"


def test_unknown_required_evidence_generates_warning_and_telemetry() -> None:
    """Unknown evidence keys should remain soft-warning with telemetry counters."""
    ctx = PipelineContext(
        request_id="req-unknown-evidence",
        query="unknown evidence",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        context={
            "category": "aml_kyc",
            "template_id": "tmpl-unknown-1",
            "required_evidence": ["kyc_profile", "unknown_custom_doc"],
            "satisfied_evidence": ["kyc_profile"],
        },
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    telemetry = payload["required_evidence_telemetry"]
    assert telemetry["unknown_required_evidence_key_total"] >= 1
    assert telemetry["mode"] == "warn"
    assert "unknown_required_evidence_keys_detected" in payload.get("warnings", [])


def test_alias_normalization_counter_is_recorded() -> None:
    """Alias normalization telemetry should increase when aliases are provided."""
    ctx = PipelineContext(
        request_id="req-alias-telemetry",
        query="alias telemetry",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        context={
            "category": "aml_kyc",
            "required_evidence": ["sanctions_trace", "pep_check"],
            "satisfied_evidence": [],
        },
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    telemetry = payload["required_evidence_telemetry"]
    assert telemetry["required_evidence_alias_normalized_total"] >= 2


def test_strict_mode_unknown_key_moves_to_human_review_path() -> None:
    """Strict mode should treat unknown keys as stronger hold/review signals."""
    ctx = PipelineContext(
        request_id="req-strict-unknown",
        query="strict unknown key",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        context={
            "category": "aml_kyc",
            "required_evidence_mode": "strict",
            "required_evidence": ["kyc_profile", "unknown_custom_doc"],
            "satisfied_evidence": ["kyc_profile"],
        },
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    assert payload["required_evidence_mode"] == "strict"
    assert payload["gate_decision"] in {"hold", "human_review_required"}
    assert payload["human_review_required"] is True
    assert "unknown_required_evidence_key_strict" in payload[
        "required_evidence_assessment"
    ]["internal_reasons"]


def test_aml_kyc_escalation_sensitive_missing_requires_human_review() -> None:
    """Missing escalation-sensitive evidence must force human review flow."""
    ctx = PipelineContext(
        request_id="req-escalation-sensitive",
        query="escalation sensitive missing",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        context={
            "decision_domain": "aml_kyc",
            "required_evidence": ["kyc_profile", "sanctions_screening_trace"],
            "satisfied_evidence": ["kyc_profile"],
        },
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    assert payload["human_review_required"] is True
    assert "sanctions_screening_trace" in payload["required_evidence_assessment"][
        "escalation_sensitive_missing_keys"
    ]


def test_approval_matrix_missing_is_reported_as_escalation_sensitive() -> None:
    """approval_matrix missing should appear in escalation-sensitive diagnostics."""
    ctx = PipelineContext(
        request_id="req-approval-missing",
        query="approval matrix missing",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        context={
            "decision_domain": "aml_kyc",
            "required_evidence": ["kyc_profile", "approval_boundary_matrix"],
            "satisfied_evidence": ["kyc_profile"],
        },
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    assert "approval_matrix" in payload["required_evidence_assessment"][
        "escalation_sensitive_missing_keys"
    ]


def test_non_beachhead_aml_kyc_template_keeps_declared_required_evidence() -> None:
    """Warn mode should not force full AML/KYC profile on non-beachhead templates."""
    ctx = PipelineContext(
        request_id="req-aml-boundary-template",
        query="approval boundary undefined",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        context={
            "decision_domain": "aml_kyc",
            "template_id": "approval_boundary_undefined_stop",
            "approval_boundary_defined": False,
            "required_evidence": ["approval_matrix", "policy_definition_record"],
            "satisfied_evidence": ["approval_matrix", "policy_definition_record"],
        },
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    assert payload["required_evidence"] == ["approval_matrix", "policy_definition_record"]
    assert payload["missing_evidence"] == []
    assert payload["gate_decision"] == "human_review_required"


def test_question_first_response_prioritizes_structure_not_investigate_decision() -> None:
    """Question-first flow must keep business_decision structured and next_action for follow-up."""
    ctx = PipelineContext(
        request_id="req-question-first-aml",
        query="AML/KYC の必要証拠は何か。まず調査すべきか？",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        context={
            "decision_domain": "aml_kyc",
            "required_evidence": ["kyc_profile"],
            "satisfied_evidence": [],
        },
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    assert payload["business_decision"] in {"EVIDENCE_REQUIRED", "HOLD"}
    assert payload["next_action"] != "INVESTIGATE_FIRST"
    assert "structured_answer" in payload
