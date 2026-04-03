from __future__ import annotations

from pathlib import Path

import pytest

from veritas_os.policy.hash import semantic_policy_hash
from veritas_os.policy.normalize import to_canonical_ir
from veritas_os.policy.schema import load_and_validate_policy, validate_source_policy
from veritas_os.policy.models import PolicyValidationError


EXAMPLES_DIR = Path("policies/examples")


def test_valid_example_policy_parses_successfully() -> None:
    policy = load_and_validate_policy(
        EXAMPLES_DIR / "high_risk_route_requires_human_review.yaml"
    )

    assert policy.policy_id == "policy.high_risk_route.human_review"
    assert policy.outcome.decision.value == "require_human_review"


@pytest.mark.parametrize(
    "example_name",
    [
        "high_risk_route_requires_human_review.yaml",
        "external_tool_usage_denied.yaml",
        "missing_mandatory_evidence_halt.yaml",
        "low_risk_route_allow.yaml",
        "anomaly_detection_escalate.yaml",
    ],
)
def test_all_example_policies_validate(example_name: str) -> None:
    policy = load_and_validate_policy(EXAMPLES_DIR / example_name)

    assert policy.schema_version == "1.0"


def test_invalid_policy_fails_with_useful_error() -> None:
    invalid = {
        "schema_version": "1.0",
        "policy_id": "policy.invalid.enum",
        "version": "1",
        "title": "Invalid enum policy",
        "description": "Should fail because outcome enum is invalid.",
        "scope": {
            "domains": ["governance"],
            "routes": ["/api/decide"],
            "actors": ["kernel"],
        },
        "outcome": {
            "decision": "block_all",
            "reason": "invalid",
        },
    }

    with pytest.raises(PolicyValidationError, match="invalid policy"):
        validate_source_policy(invalid)


def test_required_nested_structures_are_enforced() -> None:
    missing_scope = {
        "schema_version": "1.0",
        "policy_id": "policy.invalid.missing_scope",
        "version": "1",
        "title": "Missing scope",
        "description": "This policy should fail.",
        "outcome": {
            "decision": "deny",
            "reason": "invalid",
        },
    }

    with pytest.raises(PolicyValidationError, match="scope"):
        validate_source_policy(missing_scope)


def test_normalization_is_deterministic_for_equivalent_policies() -> None:
    policy_a = validate_source_policy(
        {
            "schema_version": "1.0",
            "policy_id": "policy.same.meaning",
            "version": "1",
            "title": "Same semantics",
            "description": "Ordering differences should normalize.",
            "scope": {
                "domains": ["security", "governance"],
                "routes": ["/api/decide", "/api/tools"],
                "actors": ["kernel", "planner"],
            },
            "conditions": [
                {"field": "risk.level", "operator": "in", "value": ["high", "critical"]},
                {"field": "tool.external", "operator": "eq", "value": True},
            ],
            "requirements": {
                "required_evidence": ["impact_assessment", "risk_assessment"],
                "required_reviewers": ["security_officer", "governance_officer"],
                "minimum_approval_count": 1,
            },
            "constraints": [
                {"field": "runtime.auto_execute", "operator": "eq", "value": False},
            ],
            "outcome": {"decision": "escalate", "reason": "Escalate."},
            "obligations": ["record_trust_log", "notify_governance_channel"],
        }
    )
    policy_b = validate_source_policy(
        {
            "schema_version": "1.0",
            "policy_id": "policy.same.meaning",
            "version": "1",
            "title": "Same semantics",
            "description": "Ordering differences should normalize.",
            "scope": {
                "domains": ["governance", "security", "governance"],
                "routes": ["/api/tools", "/api/decide"],
                "actors": ["planner", "kernel", "planner"],
            },
            "conditions": [
                {"field": "tool.external", "operator": "eq", "value": True},
                {"field": "risk.level", "operator": "in", "value": ["high", "critical"]},
            ],
            "requirements": {
                "required_evidence": ["risk_assessment", "impact_assessment", "risk_assessment"],
                "required_reviewers": ["governance_officer", "security_officer"],
                "minimum_approval_count": 1,
            },
            "constraints": [
                {"field": "runtime.auto_execute", "operator": "eq", "value": False},
            ],
            "outcome": {"decision": "escalate", "reason": "Escalate."},
            "obligations": ["notify_governance_channel", "record_trust_log"],
        }
    )

    assert to_canonical_ir(policy_a) == to_canonical_ir(policy_b)


def test_semantic_hash_is_stable_for_equivalent_policies() -> None:
    policy_a = load_and_validate_policy(
        EXAMPLES_DIR / "external_tool_usage_denied.yaml"
    )
    policy_b = validate_source_policy(
        {
            "schema_version": "1.0",
            "policy_id": "policy.external_tool_usage.denied",
            "version": "2026.03.28",
            "title": "Deny external tool usage under restricted conditions",
            "description": (
                "Disallow external tool invocation when tenant data "
                "classification is restricted."
            ),
            "scope": {
                "domains": ["security", "tooling"],
                "routes": ["/api/decide", "/api/tools"],
                "actors": ["tool_adapter", "kernel"],
            },
            "conditions": [
                {"field": "data.classification", "operator": "in", "value": ["restricted", "secret"]},
                {"field": "tool.external", "operator": "eq", "value": True},
            ],
            "requirements": {
                "required_evidence": ["data_classification_label"],
                "required_reviewers": ["security_officer"],
                "minimum_approval_count": 1,
            },
            "constraints": [
                {
                    "field": "tool.name",
                    "operator": "not_in",
                    "value": ["internal_search", "approved_registry"],
                }
            ],
            "outcome": {
                "decision": "deny",
                "reason": "External tools are prohibited for restricted data handling contexts.",
            },
            "obligations": ["record_denial_reason", "emit_security_alert"],
            "test_vectors": [
                {
                    "name": "external tool denied for restricted data",
                    "input": {
                        "tool": {"external": True},
                        "data": {"classification": "restricted"},
                    },
                    "expected_outcome": "deny",
                }
            ],
        }
    )

    hash_a = semantic_policy_hash(to_canonical_ir(policy_a))
    hash_b = semantic_policy_hash(to_canonical_ir(policy_b))

    assert hash_a == hash_b


# --- Schema loader error handling tests ---


def test_load_policy_file_not_found(tmp_path: Path) -> None:
    """PolicyValidationError for missing file."""
    with pytest.raises(PolicyValidationError, match="not found"):
        load_and_validate_policy(tmp_path / "nonexistent.yaml")


def test_load_policy_empty_file(tmp_path: Path) -> None:
    """PolicyValidationError for empty YAML file."""
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(PolicyValidationError, match="empty"):
        load_and_validate_policy(empty)


def test_load_policy_invalid_yaml(tmp_path: Path) -> None:
    """PolicyValidationError for malformed YAML."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(":\n  - :\n    - {[invalid", encoding="utf-8")
    with pytest.raises(PolicyValidationError, match="invalid YAML"):
        load_and_validate_policy(bad)


def test_load_policy_invalid_json(tmp_path: Path) -> None:
    """PolicyValidationError for malformed JSON."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(PolicyValidationError, match="invalid JSON"):
        load_and_validate_policy(bad)


def test_load_policy_non_mapping_yaml(tmp_path: Path) -> None:
    """PolicyValidationError when YAML decodes to a list."""
    bad = tmp_path / "list.yaml"
    bad.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(PolicyValidationError, match="mapping object"):
        load_and_validate_policy(bad)
