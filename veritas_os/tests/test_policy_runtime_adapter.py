from __future__ import annotations

from pathlib import Path

from veritas_os.policy.compiler import compile_policy_to_bundle
from veritas_os.policy.evaluator import evaluate_runtime_policies
from veritas_os.policy.runtime_adapter import adapt_compiled_payload, load_runtime_bundle

EXAMPLES_DIR = Path("policies/examples")


def _compile_bundle(tmp_path: Path, policy_file: str):
    return compile_policy_to_bundle(
        EXAMPLES_DIR / policy_file,
        tmp_path,
        compiled_at="2026-03-28T00:00:00Z",
    )


def test_high_risk_route_requires_human_review(tmp_path: Path) -> None:
    result = _compile_bundle(tmp_path, "high_risk_route_requires_human_review.yaml")
    runtime_bundle = load_runtime_bundle(result.bundle_dir)

    context = {
        "domain": "governance",
        "route": "/api/decide",
        "actor": "planner",
        "risk": {"level": "critical"},
        "runtime": {"auto_execute": False},
        "evidence": {"available": ["risk_assessment", "impact_assessment"]},
        "approvals": {"approved_by": ["governance_officer", "safety_reviewer"]},
    }
    decision = evaluate_runtime_policies(runtime_bundle, context).to_dict()

    assert decision["final_outcome"] == "require_human_review"
    assert "policy.high_risk_route.human_review" in decision["triggered_policies"]


def test_missing_evidence_surfaces_halt_and_evidence_gap(tmp_path: Path) -> None:
    result = _compile_bundle(tmp_path, "missing_mandatory_evidence_halt.yaml")
    runtime_bundle = load_runtime_bundle(result.bundle_dir)

    context = {
        "domain": "governance",
        "route": "/api/decide",
        "actor": "planner",
        "decision": {"criticality": "critical"},
        "evidence": {"available": ["source_citation"], "missing_count": 2},
        "approvals": {"approved_by": ["audit_reviewer"]},
    }
    decision = evaluate_runtime_policies(runtime_bundle, context).to_dict()

    assert decision["final_outcome"] == "halt"
    assert decision["evidence_gaps"][0]["missing_evidence"] == [
        "approval_ticket",
        "impact_assessment",
    ]


def test_prohibited_external_tool_use_is_denied(tmp_path: Path) -> None:
    result = _compile_bundle(tmp_path, "external_tool_usage_denied.yaml")
    runtime_bundle = load_runtime_bundle(result.bundle_dir)

    context = {
        "domain": "security",
        "route": "/api/tools",
        "actor": "kernel",
        "tool": {"external": True, "name": "unapproved_webhook"},
        "data": {"classification": "restricted"},
        "evidence": {"available": ["data_classification_label"]},
        "approvals": {"approved_by": ["security_officer"]},
    }
    decision = evaluate_runtime_policies(runtime_bundle, context).to_dict()

    assert decision["final_outcome"] == "deny"
    assert "emit_security_alert" in decision["obligations"]


def test_explanation_metadata_unmet_approvals_and_obligations_are_surfaced(
    tmp_path: Path,
) -> None:
    result = _compile_bundle(tmp_path, "high_risk_route_requires_human_review.yaml")
    runtime_bundle = load_runtime_bundle(result.bundle_dir)

    context = {
        "domain": "governance",
        "route": "/api/decide",
        "actor": "planner",
        "risk": {"level": "high"},
        "runtime": {"auto_execute": False},
        "evidence": {"available": ["risk_assessment", "impact_assessment"]},
        "approvals": {"approved_by": ["governance_officer"]},
    }
    decision = evaluate_runtime_policies(runtime_bundle, context).to_dict()

    assert decision["explanations"][0]["summary"]
    assert not decision["approval_requirements"][0]["minimum_approval_met"]
    assert "attach_review_ticket" in decision["obligations"]


def test_allow_and_escalate_outcomes_are_supported() -> None:
    allow_bundle = adapt_compiled_payload(
        canonical_ir={
            "schema_version": "1.0",
            "policy_id": "policy.runtime.allow",
            "version": "1",
            "title": "Allow when safe",
            "description": "Allow in safe scenario.",
            "effective_date": None,
            "scope": {
                "domains": ["governance"],
                "routes": ["/api/decide"],
                "actors": ["planner"],
            },
            "conditions": [{"field": "risk.level", "operator": "eq", "value": "low"}],
            "requirements": {
                "required_evidence": [],
                "required_reviewers": [],
                "minimum_approval_count": 0,
            },
            "constraints": [],
            "outcome": {"decision": "allow", "reason": "Low risk."},
            "obligations": [],
            "test_vectors": [],
            "source_refs": [],
            "metadata": {},
        },
        manifest={"schema_version": "0.1"},
    )
    escalate_bundle = adapt_compiled_payload(
        canonical_ir={
            "schema_version": "1.0",
            "policy_id": "policy.runtime.escalate",
            "version": "1",
            "title": "Escalate anomaly",
            "description": "Escalate on anomaly.",
            "effective_date": None,
            "scope": {
                "domains": ["governance"],
                "routes": ["/api/decide"],
                "actors": ["planner"],
            },
            "conditions": [{"field": "risk.level", "operator": "eq", "value": "medium"}],
            "requirements": {
                "required_evidence": [],
                "required_reviewers": [],
                "minimum_approval_count": 0,
            },
            "constraints": [],
            "outcome": {"decision": "escalate", "reason": "Anomaly detected."},
            "obligations": ["notify_governance_channel"],
            "test_vectors": [],
            "source_refs": [],
            "metadata": {},
        },
        manifest={"schema_version": "0.1"},
    )

    allow_decision = evaluate_runtime_policies(
        allow_bundle,
        {
            "domain": "governance",
            "route": "/api/decide",
            "actor": "planner",
            "risk": {"level": "low"},
        },
    ).to_dict()
    escalate_decision = evaluate_runtime_policies(
        escalate_bundle,
        {
            "domain": "governance",
            "route": "/api/decide",
            "actor": "planner",
            "risk": {"level": "medium"},
        },
    ).to_dict()

    assert allow_decision["final_outcome"] == "allow"
    assert escalate_decision["final_outcome"] == "escalate"


def test_regex_condition_respects_runtime_guardrails() -> None:
    regex_bundle = adapt_compiled_payload(
        canonical_ir={
            "schema_version": "1.0",
            "policy_id": "policy.runtime.regex_guardrails",
            "version": "1",
            "title": "Regex guardrail",
            "description": "Use regex condition.",
            "effective_date": None,
            "scope": {
                "domains": ["governance"],
                "routes": ["/api/decide"],
                "actors": ["planner"],
            },
            "conditions": [
                {"field": "request.text", "operator": "regex", "value": "safe"}
            ],
            "requirements": {
                "required_evidence": [],
                "required_reviewers": [],
                "minimum_approval_count": 0,
            },
            "constraints": [],
            "outcome": {"decision": "escalate", "reason": "Regex matched."},
            "obligations": [],
            "test_vectors": [],
            "source_refs": [],
            "metadata": {},
        },
        manifest={"schema_version": "0.1"},
    )

    allowed_decision = evaluate_runtime_policies(
        regex_bundle,
        {
            "domain": "governance",
            "route": "/api/decide",
            "actor": "planner",
            "request": {"text": "safe input"},
        },
    ).to_dict()
    oversized_input_decision = evaluate_runtime_policies(
        regex_bundle,
        {
            "domain": "governance",
            "route": "/api/decide",
            "actor": "planner",
            "request": {"text": "a" * 1025},
        },
    ).to_dict()

    assert allowed_decision["final_outcome"] == "escalate"
    assert oversized_input_decision["final_outcome"] == "allow"


def test_regex_condition_rejects_nested_quantifier_pattern() -> None:
    regex_bundle = adapt_compiled_payload(
        canonical_ir={
            "schema_version": "1.0",
            "policy_id": "policy.runtime.regex_nested_quantifier_guardrails",
            "version": "1",
            "title": "Regex nested quantifier guardrail",
            "description": "Reject potentially expensive regex patterns.",
            "effective_date": None,
            "scope": {
                "domains": ["governance"],
                "routes": ["/api/decide"],
                "actors": ["planner"],
            },
            "conditions": [
                {"field": "request.text", "operator": "regex", "value": "(a+)+$"}
            ],
            "requirements": {
                "required_evidence": [],
                "required_reviewers": [],
                "minimum_approval_count": 0,
            },
            "constraints": [],
            "outcome": {"decision": "escalate", "reason": "Regex matched."},
            "obligations": [],
            "test_vectors": [],
            "source_refs": [],
            "metadata": {},
        },
        manifest={"schema_version": "0.1"},
    )

    guarded_decision = evaluate_runtime_policies(
        regex_bundle,
        {
            "domain": "governance",
            "route": "/api/decide",
            "actor": "planner",
            "request": {"text": "a" * 200},
        },
    ).to_dict()

    assert guarded_decision["final_outcome"] == "allow"
