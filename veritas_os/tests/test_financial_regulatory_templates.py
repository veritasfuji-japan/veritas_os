# -*- coding: utf-8 -*-
"""Regression coverage for financial/regulatory governance template fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Literal

from pydantic import BaseModel, Field

from veritas_os.api.schemas import DecideResponse
from veritas_os.core.pipeline.pipeline_response import assemble_response
from veritas_os.core.pipeline.pipeline_types import PipelineContext

FIXTURE_PATH = Path("veritas_os/sample_data/governance/financial_regulatory_templates.json")


class ExpectedGovernanceBehavior(BaseModel):
    """Expected governance behavior for one regulated-domain template."""

    gate_decision: Literal[
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
    ]
    business_decision: Literal[
        "APPROVE",
        "DENY",
        "HOLD",
        "REVIEW_REQUIRED",
        "POLICY_DEFINITION_REQUIRED",
        "EVIDENCE_REQUIRED",
    ]
    required_evidence: List[str] = Field(min_length=1)
    human_review_required: bool
    rationale_expectations: List[str] = Field(min_length=2)


class FinancialGovernanceTemplate(BaseModel):
    """Canonical fixture shape used by financial/governance regression tests."""

    template_id: str
    industry: str
    decision_domain: str
    title: str
    question: str
    expected_governance_behavior: ExpectedGovernanceBehavior


def _load_templates() -> List[FinancialGovernanceTemplate]:
    """Load and parse the canonical financial governance fixture file."""
    raw_data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return [FinancialGovernanceTemplate.model_validate(item) for item in raw_data]


def test_financial_templates_fixture_loads() -> None:
    """Fixture file should be loadable for dev/demo and tests."""
    templates = _load_templates()

    assert len(templates) >= 7
    assert all(template.question.strip() for template in templates)


def test_financial_templates_include_mandatory_domains() -> None:
    """Template pack must cover the required financial/regulatory domains."""
    templates = _load_templates()
    template_ids = {item.template_id for item in templates}

    assert "credit_missing_bureau_data_no_auto_approval" in template_ids
    assert "fraud_realtime_block_vs_stepup_auth" in template_ids
    assert "aml_kyc_high_risk_country_wire_manual_review" in template_ids
    assert "sanctions_partial_name_match_hold" in template_ids
    assert "suitability_leveraged_product_retail_client" in template_ids
    assert "high_risk_transaction_pending_release" in template_ids
    assert "approval_boundary_undefined_stop" in template_ids


def test_financial_templates_are_compatible_with_decide_response_schema() -> None:
    """Expected template outputs should map to the public DecideResponse schema."""
    templates = _load_templates()

    for template in templates:
        expected = template.expected_governance_behavior
        payload = DecideResponse.model_validate(
            {
                "request_id": f"fixture-{template.template_id}",
                "query": template.question,
                "gate_decision": expected.gate_decision,
                "business_decision": expected.business_decision,
                "next_action": "COLLECT_REQUIRED_EVIDENCE",
                "required_evidence": expected.required_evidence,
                "human_review_required": expected.human_review_required,
                "rationale": " | ".join(expected.rationale_expectations),
            }
        )

        assert payload.gate_decision == expected.gate_decision
        assert payload.business_decision == expected.business_decision
        assert payload.required_evidence == expected.required_evidence
        assert payload.human_review_required is expected.human_review_required


def test_regression_approval_boundary_undefined_requires_human_review() -> None:
    """Approval boundary undefined case should fail closed to review-required."""
    ctx = PipelineContext(
        request_id="financial-template-regression",
        query="承認境界が未定義の複合案件を継続できるか",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context={
            "required_evidence": ["approval_matrix", "policy_owner_confirmation"],
            "satisfied_evidence": ["approval_matrix", "policy_owner_confirmation"],
            "approval_boundary_defined": False,
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
