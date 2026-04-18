"""Sample-question regression coverage for the public decision schema."""

from __future__ import annotations

import pytest

from veritas_os.core.pipeline.pipeline_response import assemble_response
from veritas_os.core.pipeline.pipeline_types import PipelineContext

pytestmark = pytest.mark.integration


SAMPLE_QUESTIONS = [
    "最低条件は何か",
    "人手審査境界は何か",
    "必要証拠は何か",
    "通しすぎと止めすぎを比較してください",
    "ルールを形式化してください",
    "FujiGate / Value Core の分離を説明してください",
    "出力を gate_decision / business_decision / next_action / required_evidence / human_review_required で返してください",
]


@pytest.mark.parametrize("query", SAMPLE_QUESTIONS)
def test_sample_questions_return_public_decision_schema(query: str) -> None:
    """Sample prompts must always produce the public decision contract fields."""
    ctx = PipelineContext(
        request_id=f"sample-{abs(hash(query))}",
        query=query,
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

    assert payload["gate_decision"] in {
        "proceed",
        "hold",
        "human_review_required",
        "block",
    }
    assert payload["business_decision"] in {
        "APPROVE",
        "DENY",
        "HOLD",
        "REVIEW_REQUIRED",
        "POLICY_DEFINITION_REQUIRED",
        "EVIDENCE_REQUIRED",
    }
    assert isinstance(payload["next_action"], str)
    assert isinstance(payload["required_evidence"], list)
    assert isinstance(payload["human_review_required"], bool)


def test_allow_is_not_used_as_public_business_decision() -> None:
    """Regression guard: allow is gate-level only, never business-level output."""
    ctx = PipelineContext(
        request_id="sample-allow-guard",
        query="出力を構造化してください",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    assert payload["gate_decision"] == "proceed"
    assert payload["business_decision"] != "allow"
    assert payload["next_action"] != payload["business_decision"]
