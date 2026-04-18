# -*- coding: utf-8 -*-
"""Regression coverage for financial/regulatory governance template fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Literal

from pydantic import BaseModel, Field

from veritas_os.api.schemas import DecideResponse
from veritas_os.core.pipeline.pipeline_response import assemble_response
from veritas_os.core.pipeline.pipeline_types import PipelineContext
from veritas_os.tests.helpers.semantics import assert_expected_semantics

FIXTURE_PATH = Path("veritas_os/sample_data/governance/financial_regulatory_templates.json")
TAXONOMY_PATH = Path("veritas_os/sample_data/governance/required_evidence_taxonomy_v0.json")


class ExpectedSemantics(BaseModel):
    """Expected decision semantics for one regulated-domain template."""

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
    next_action: str = Field(min_length=1)
    required_evidence: List[str] = Field(min_length=1)
    missing_evidence: List[str] = Field(default_factory=list)
    human_review_required: bool
    rationale_summary: str = Field(min_length=1)
    rationale_expectations: List[str] = Field(min_length=2)


class FinancialGovernanceTemplate(BaseModel):
    """Canonical fixture shape used by financial/governance regression tests."""

    template_id: str
    industry: str
    decision_domain: str
    title: str
    question: str
    context: Dict[str, object]
    expected_semantics: ExpectedSemantics


class FinancialGovernanceTemplatePack(BaseModel):
    """Canonical industry-pack shape for financial governance templates."""

    pack_id: str
    pack_type: Literal["industry_governance_templates"]
    industry: str
    version: str
    taxonomy_policy: Dict[str, str]
    beachhead: Dict[str, str]
    templates: List[FinancialGovernanceTemplate] = Field(min_length=1)


class TaxonomyItem(BaseModel):
    """Machine-readable required evidence taxonomy item."""

    canonical_key: str
    display_label: str
    aliases: List[str]
    category: str
    description: str
    notes: str


class RequiredEvidenceTaxonomy(BaseModel):
    """Required evidence taxonomy definition payload."""

    version: str
    scope: str
    allow_free_string: bool
    items: List[TaxonomyItem]
    profiles: Dict[str, Dict[str, object]] = Field(default_factory=dict)


def _load_template_pack() -> FinancialGovernanceTemplatePack:
    """Load and parse the canonical financial governance template pack file."""
    raw_data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return FinancialGovernanceTemplatePack.model_validate(raw_data)


def _load_taxonomy() -> RequiredEvidenceTaxonomy:
    """Load required evidence taxonomy fixture."""
    payload = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    return RequiredEvidenceTaxonomy.model_validate(payload)


def test_financial_templates_fixture_loads() -> None:
    """Fixture file should be loadable for dev/demo and tests."""
    pack = _load_template_pack()
    templates = pack.templates

    assert len(templates) >= 7
    assert all(template.question.strip() for template in templates)
    assert pack.beachhead["decision_domain"] == "aml_kyc"
    assert pack.beachhead["template_id"] == "aml_kyc_high_risk_country_wire_manual_review"


def test_financial_templates_include_mandatory_domains() -> None:
    """Template pack must cover the required financial/regulatory domains."""
    templates = _load_template_pack().templates
    template_ids = {item.template_id for item in templates}

    assert "credit_missing_bureau_data_no_auto_approval" in template_ids
    assert "fraud_realtime_block_vs_stepup_auth" in template_ids
    assert "aml_kyc_high_risk_country_wire_manual_review" in template_ids
    assert "sanctions_partial_name_match_hold" in template_ids
    assert "suitability_leveraged_product_retail_client" in template_ids
    assert "high_risk_transaction_pending_release" in template_ids
    assert "approval_boundary_undefined_stop" in template_ids


def test_financial_template_shape_includes_context_and_expected_fields() -> None:
    """Template fixtures must define context + explicit expected output fields."""
    templates = _load_template_pack().templates

    for template in templates:
        assert isinstance(template.context.get("required_evidence"), list)
        assert isinstance(template.context.get("satisfied_evidence"), list)
        expected = template.expected_semantics
        assert expected.required_evidence == template.context["required_evidence"]
        assert set(expected.missing_evidence) == (
            set(expected.required_evidence) - set(template.context["satisfied_evidence"])
        )


def test_financial_templates_are_compatible_with_decide_response_schema() -> None:
    """Expected template outputs should map to the public DecideResponse schema."""
    templates = _load_template_pack().templates

    for template in templates:
        expected = template.expected_semantics
        payload = DecideResponse.model_validate(
            {
                "request_id": f"fixture-{template.template_id}",
                "query": template.question,
                "gate_decision": expected.gate_decision,
                "business_decision": expected.business_decision,
                "next_action": expected.next_action,
                "required_evidence": expected.required_evidence,
                "missing_evidence": expected.missing_evidence,
                "human_review_required": expected.human_review_required,
                "rationale": expected.rationale_summary,
            }
        )

        assert payload.gate_decision == expected.gate_decision
        assert payload.business_decision == expected.business_decision
        assert payload.required_evidence == expected.required_evidence
        assert payload.human_review_required is expected.human_review_required


def test_regression_approval_boundary_undefined_requires_human_review() -> None:
    """Approval boundary undefined case should fail closed to review-required."""
    template_map = {item.template_id: item for item in _load_template_pack().templates}
    template = template_map["approval_boundary_undefined_stop"]
    ctx = PipelineContext(
        request_id="financial-template-regression",
        query="承認境界が未定義の複合案件を継続できるか",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context=template.context,
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    assert payload["gate_decision"] == "human_review_required"
    assert payload["business_decision"] == "REVIEW_REQUIRED"
    assert payload["human_review_required"] is True


def test_regression_representative_financial_templates_governance_alignment() -> None:
    """Representative templates should map to stable gate/business decisions."""
    template_ids = [
        "credit_missing_bureau_data_no_auto_approval",
        "aml_kyc_high_risk_country_wire_manual_review",
        "high_risk_transaction_pending_release",
    ]
    templates = {item.template_id: item for item in _load_template_pack().templates}

    for template_id in template_ids:
        template = templates[template_id]
        expected = template.expected_semantics
        ctx = PipelineContext(
            request_id=f"financial-template-{template_id}",
            query=template.question,
            fuji_dict={"decision_status": "allow", "status": "allow"},
            decision_status="allow",
            rejection_reason=None,
            context=template.context,
        )

        payload = assemble_response(
            ctx,
            load_persona_fn=lambda: {},
            plan={"steps": [], "source": "test"},
        )
        assert_expected_semantics(
            payload,
            expected.model_dump(),
        )


def test_regression_sanctions_partial_match_does_not_proceed() -> None:
    """Sanctions partial-name match must not pass through proceed path."""
    templates = {item.template_id: item for item in _load_template_pack().templates}
    template = templates["sanctions_partial_name_match_hold"]
    ctx = PipelineContext(
        request_id="financial-template-sanctions-partial",
        query=template.question,
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context=template.context,
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    assert payload["gate_decision"] != "proceed"
    assert payload["business_decision"] in {"HOLD", "EVIDENCE_REQUIRED", "REVIEW_REQUIRED"}


def test_regression_source_of_funds_missing_does_not_approve() -> None:
    """Missing source-of-funds evidence should fail closed to non-APPROVE."""
    template_map = {item.template_id: item for item in _load_template_pack().templates}
    template = template_map["aml_kyc_high_risk_country_wire_manual_review"]
    ctx = PipelineContext(
        request_id="financial-template-sof-missing",
        query="高リスク国送金だが source of funds が未提出。自動承認できるか？",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context={
            **template.context,
            "satisfied_evidence": [
                "kyc_profile",
                "pep_screening_result",
                "transaction_purpose_statement",
            ],
        },
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    assert "source_of_funds_record" in payload["missing_evidence"]
    assert payload["business_decision"] != "APPROVE"


def test_regression_high_risk_ambiguity_forces_human_review_required() -> None:
    """High risk ambiguity should force human_review_required escalation."""
    template_map = {item.template_id: item for item in _load_template_pack().templates}
    template = template_map["aml_kyc_high_risk_country_wire_manual_review"]
    ctx = PipelineContext(
        request_id="financial-template-high-risk-ambiguity",
        query=template.question,
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context={**template.context, "high_risk_ambiguity": True, "risk_score": 0.92},
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    assert payload["human_review_required"] is True
    assert payload["gate_decision"] == "human_review_required"


def test_regression_secure_prod_controls_missing_blocks_execution() -> None:
    """Secure/prod controls missing should force block in secure environment."""
    ctx = PipelineContext(
        request_id="financial-template-secure-controls",
        query="secure controls missing",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context={
            "decision_domain": "aml_kyc",
            "environment": "secure",
            "production_controls_ready": False,
            "required_evidence": ["kyc_profile"],
            "satisfied_evidence": ["kyc_profile"],
        },
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    assert payload["gate_decision"] == "block"
    assert payload["business_decision"] != "APPROVE"


def test_financial_templates_expected_semantics_has_required_fields() -> None:
    """Expected semantics should include next_action and rationale expectations."""
    templates = _load_template_pack().templates

    for template in templates:
        expected = template.expected_semantics
        assert expected.next_action.strip()
        assert expected.rationale_summary.strip()
        assert len(expected.rationale_expectations) >= 2


def test_required_evidence_taxonomy_has_unique_canonical_keys_and_aliases() -> None:
    """Taxonomy canonical keys and aliases should stay collision-free."""
    taxonomy = _load_taxonomy()
    canonical_keys = [item.canonical_key for item in taxonomy.items]

    assert taxonomy.version == "v0"
    assert taxonomy.allow_free_string is True
    assert len(canonical_keys) >= 11
    assert len(canonical_keys) == len(set(canonical_keys))

    alias_to_canonical: dict[str, str] = {}
    for item in taxonomy.items:
        for alias in item.aliases:
            assert alias != item.canonical_key
            existing = alias_to_canonical.get(alias)
            assert existing in {None, item.canonical_key}
            alias_to_canonical[alias] = item.canonical_key


def test_aml_kyc_profile_shape_validation() -> None:
    """AML/KYC profile should be machine-readable and taxonomy-aligned."""
    taxonomy = _load_taxonomy()
    canonical_keys = {item.canonical_key for item in taxonomy.items}
    aml_profile = taxonomy.profiles.get("aml_kyc")

    assert aml_profile is not None
    assert aml_profile.get("profile_id") == "aml_kyc_beachhead_v1"
    required_keys = set(aml_profile.get("required", []))
    escalation_keys = set(aml_profile.get("escalation_sensitive", []))
    assert required_keys
    assert required_keys <= canonical_keys
    assert escalation_keys <= canonical_keys
    assert "source_of_funds_record" in required_keys
    assert "sanctions_screening_trace" in required_keys


def test_regression_financial_question_first_response_includes_structure() -> None:
    """Financial template query should return question-first structured answer."""
    template_map = {item.template_id: item for item in _load_template_pack().templates}
    template = template_map["credit_missing_bureau_data_no_auto_approval"]
    ctx = PipelineContext(
        request_id="financial-template-question-first",
        query="最低条件と必要証拠は何ですか？",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context={**template.context, "debug": True},
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    structured = payload["structured_answer"]
    assert structured["minimum_conditions"]["required_evidence_count"] == 3
    assert structured["minimum_conditions"]["missing_evidence_count"] == 1
    assert payload["next_action"] == "COLLECT_REQUIRED_EVIDENCE"


def test_regression_high_risk_ambiguity_requires_human_review() -> None:
    """High-risk ambiguity must force human review boundary."""
    template_map = {item.template_id: item for item in _load_template_pack().templates}
    template = template_map["aml_kyc_high_risk_country_wire_manual_review"]
    ctx = PipelineContext(
        request_id="financial-template-high-risk-ambiguity",
        query=template.question,
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context=template.context,
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    assert payload["human_review_required"] is True
    assert payload["business_decision"] == "REVIEW_REQUIRED"


def test_regression_secure_prod_controls_missing_blocks_case() -> None:
    """Secure/prod controls missing should trigger block in secure posture path."""
    template_map = {item.template_id: item for item in _load_template_pack().templates}
    template = template_map["high_risk_transaction_pending_release"]
    ctx = PipelineContext(
        request_id="financial-template-secure-controls",
        query=template.question,
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context=template.context,
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    assert payload["gate_decision"] == "block"
    assert payload["business_decision"] == "DENY"


def test_regression_question_first_aml_kyc_returns_controls_and_next_action_hint() -> None:
    """AML/KYC question-first response should prioritize evidence/review fields."""
    template_map = {item.template_id: item for item in _load_template_pack().templates}
    template = template_map["aml_kyc_high_risk_country_wire_manual_review"]
    ctx = PipelineContext(
        request_id="financial-template-question-first-aml",
        query="制裁一致時に何を止めるべきか、source_of_funds がないとき何を保留すべきか？",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context={
            **template.context,
            "satisfied_evidence": [
                "kyc_profile",
                "pep_screening_result",
                "approval_matrix",
            ],
        },
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    structured = payload["structured_answer"]
    assert "source_of_funds_record" in payload["missing_evidence"]
    assert payload["business_decision"] in {"EVIDENCE_REQUIRED", "HOLD", "REVIEW_REQUIRED"}
    assert structured["source_of_funds_controls"]["source_of_funds_missing"] is True
    assert "next_action_hint" in structured


def test_regression_dev_mode_action_ranking_trace_is_visible() -> None:
    """Dev/debug path should expose action ranking trace for diagnostics."""
    template_map = {item.template_id: item for item in _load_template_pack().templates}
    template = template_map["aml_kyc_high_risk_country_wire_manual_review"]
    ctx = PipelineContext(
        request_id="financial-template-ranking-trace",
        query=template.question,
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        rejection_reason=None,
        context={**template.context, "dev_mode": True},
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    ranking_trace = payload["action_selection"]["ranking_trace"]
    assert ranking_trace["weights"]["expected_value"] == 0.35
    assert ranking_trace["ordered_actions"][0]["action"] == payload["next_action"]
    assert "high_risk_ambiguity" in ranking_trace["stop_reasons"]
