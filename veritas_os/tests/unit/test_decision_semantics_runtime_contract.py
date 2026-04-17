from pydantic import ValidationError

from veritas_os.api.schemas import DecideResponse
from veritas_os.core.pipeline.pipeline_response import assemble_response
from veritas_os.core.pipeline.pipeline_types import PipelineContext


def test_gate_decision_alias_is_canonicalized_in_schema() -> None:
    """legacy gate aliases should normalize to canonical public semantics."""
    payload = DecideResponse.model_validate(
        {
            "gate_decision": "deny",
            "business_decision": "DENY",
            "human_review_required": False,
        }
    )

    assert payload.gate_decision == "block"


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


def test_review_required_requires_human_review_true() -> None:
    """REVIEW_REQUIRED must not coexist with human_review_required=false."""
    try:
        DecideResponse.model_validate(
            {
                "gate_decision": "human_review_required",
                "business_decision": "REVIEW_REQUIRED",
                "human_review_required": False,
            }
        )
    except ValidationError as exc:
        assert "requires human_review_required=true" in str(exc)
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
