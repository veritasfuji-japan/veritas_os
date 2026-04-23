"""OpenAPI specification regression tests.

This module validates that ``openapi.yaml`` remains parseable and aligned with
critical API routes implemented by ``veritas_os.api.server``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from veritas_os.api import server as srv


def _load_openapi_spec() -> dict:
    """Load and parse the repository OpenAPI YAML document."""
    repo_root = Path(__file__).resolve().parents[2]
    spec_path = repo_root / "openapi.yaml"
    with spec_path.open("r", encoding="utf-8") as file_obj:
        return yaml.safe_load(file_obj)


def test_openapi_yaml_is_parseable() -> None:
    """The OpenAPI document must be valid YAML."""
    spec = _load_openapi_spec()

    assert isinstance(spec, dict)
    assert spec.get("openapi") == "3.1.0"


def test_openapi_paths_match_runtime_contract() -> None:
    """Critical path/method definitions should reflect the FastAPI runtime."""
    spec = _load_openapi_spec()
    paths = spec.get("paths", {})

    assert "get" in paths["/health"]
    assert "post" in paths["/v1/memory/get"]
    assert "get" in paths["/v1/trust/{request_id}"]


def test_health_endpoint_has_no_auth_requirement() -> None:
    """Health checks should be accessible without API key authentication."""
    spec = _load_openapi_spec()
    operation = spec["paths"]["/health"]["get"]

    assert operation.get("security") == []


def test_openapi_includes_runtime_audit_and_governance_routes() -> None:
    """OpenAPI should include critical runtime routes used for governance/audit."""
    spec = _load_openapi_spec()
    paths = spec.get("paths", {})
    runtime_paths = {route.path for route in srv.app.routes}

    critical = {
        "/v1/governance/policy",
        "/v1/governance/policy/history",
        "/v1/governance/decisions/export",
        "/v1/governance/bind-receipts",
        "/v1/governance/bind-receipts/{bind_receipt_id}",
        "/v1/governance/policy-bundles/promote",
        "/v1/trustlog/verify",
        "/v1/trust/{request_id}/prov",
    }

    for path in critical:
        assert path in runtime_paths
        assert path in paths


def test_openapi_decide_response_decision_semantics_contract() -> None:
    """DecideResponse schema should expose hardened canonical decision fields."""
    spec = _load_openapi_spec()
    decide_schema = spec["components"]["schemas"]["DecideResponse"]["properties"]

    gate_enum = decide_schema["gate_decision"]["enum"]
    assert gate_enum[:4] == [
        "proceed",
        "hold",
        "block",
        "human_review_required",
    ]
    assert "allow" in gate_enum
    assert decide_schema["gate_decision"]["examples"] == [
        "proceed",
        "hold",
        "human_review_required",
        "block",
    ]
    assert "not business approval" in decide_schema["gate_decision"]["description"]
    assert decide_schema["human_review_required"]["type"] == "boolean"
    assert (
        "REVIEW_REQUIRED must be paired with gate_decision=human_review_required"
        in decide_schema["human_review_required"]["description"]
    )
    assert decide_schema["business_decision"]["enum"] == [
        "APPROVE",
        "DENY",
        "HOLD",
        "REVIEW_REQUIRED",
        "POLICY_DEFINITION_REQUIRED",
        "EVIDENCE_REQUIRED",
    ]
    assert decide_schema["next_action"]["type"] == "string"
    assert "governance_identity" in decide_schema


def test_openapi_includes_bind_artifact_schemas() -> None:
    """OpenAPI should expose bind-boundary artifact models and summary fields."""
    spec = _load_openapi_spec()
    schemas = spec["components"]["schemas"]

    assert "ExecutionIntent" in schemas
    assert "BindReceipt" in schemas
    assert "BindSummary" in schemas
    policy_lineage = schemas["ExecutionIntent"]["properties"]["policy_lineage"]
    assert policy_lineage["type"] == "object"
    assert policy_lineage["nullable"] is True
    assert policy_lineage["additionalProperties"] is True

    bind_outcomes = schemas["BindReceipt"]["properties"]["final_outcome"]["enum"]
    assert bind_outcomes == [
        "COMMITTED",
        "BLOCKED",
        "ROLLED_BACK",
        "ESCALATED",
        "APPLY_FAILED",
        "SNAPSHOT_FAILED",
        "PRECONDITION_FAILED",
    ]

    export_item = schemas["GovernanceDecisionExportItem"]["properties"]
    assert "bind_outcome" in export_item
    assert "bind_failure_reason" in export_item
    assert "bind_reason_code" in export_item
    assert "bind_receipt_id" in export_item
    assert "execution_intent_id" in export_item
    assert "authority_check_result" in export_item
    assert "constraint_check_result" in export_item
    assert "drift_check_result" in export_item
    assert "risk_check_result" in export_item
    assert "bind_summary" in export_item


def test_openapi_decide_response_includes_bind_contract_fields() -> None:
    """DecideResponse should expose bind contract fields used by console and audit tooling."""
    spec = _load_openapi_spec()
    decide_schema = spec["components"]["schemas"]["DecideResponse"]["properties"]
    assert "bind_outcome" in decide_schema
    assert "bind_failure_reason" in decide_schema
    assert "bind_reason_code" in decide_schema
    assert "bind_receipt_id" in decide_schema
    assert "execution_intent_id" in decide_schema
    assert "authority_check_result" in decide_schema
    assert "constraint_check_result" in decide_schema
    assert "drift_check_result" in decide_schema
    assert "risk_check_result" in decide_schema
    assert "bind_summary" in decide_schema


def test_openapi_compliance_config_put_response_includes_bind_fields() -> None:
    """Compliance config mutation route should document bind lineage fields."""
    spec = _load_openapi_spec()
    schema = (
        spec["paths"]["/v1/compliance/config"]["put"]["responses"]["200"]["content"]
        ["application/json"]["schema"]
    )
    if "$ref" in schema:
        ref_name = str(schema["$ref"]).split("/")[-1]
        schema = spec["components"]["schemas"][ref_name]
    properties = schema["properties"]
    assert "bind_outcome" in properties
    assert "bind_failure_reason" in properties
    assert "bind_reason_code" in properties
    assert "bind_receipt_id" in properties
    assert "execution_intent_id" in properties
    assert "bind_receipt" in properties
    assert "bind_summary" in properties


def test_openapi_system_halt_response_includes_bind_fields() -> None:
    """System halt mutation route should document bind lineage fields."""
    spec = _load_openapi_spec()
    schema = (
        spec["paths"]["/v1/system/halt"]["post"]["responses"]["200"]["content"]
        ["application/json"]["schema"]
    )
    if "$ref" in schema:
        ref_name = str(schema["$ref"]).split("/")[-1]
        schema = spec["components"]["schemas"][ref_name]
    properties = schema["properties"]
    assert "bind_outcome" in properties
    assert "bind_failure_reason" in properties
    assert "bind_reason_code" in properties
    assert "bind_receipt_id" in properties
    assert "execution_intent_id" in properties
    assert "bind_receipt" in properties
    assert "bind_summary" in properties


def test_openapi_wat_config_includes_retention_boundary_fields() -> None:
    """WAT config schema must expose retention boundary lock-in controls."""
    spec = _load_openapi_spec()
    wat_props = spec["components"]["schemas"]["WatConfig"]["properties"]

    expected = {
        "wat_metadata_retention_ttl_seconds",
        "wat_event_pointer_retention_ttl_seconds",
        "observable_digest_retention_ttl_seconds",
        "observable_digest_access_class",
        "observable_digest_ref",
        "retention_policy_version",
        "retention_enforced_at_write",
    }
    assert expected.issubset(set(wat_props.keys()))
    assert wat_props["observable_digest_access_class"]["enum"] == [
        "restricted",
        "privileged",
    ]


def test_openapi_wat_operator_summary_and_governance_defaults_locked() -> None:
    """WAT summary and governance defaults must stay synchronized with runtime lock-in."""
    spec = _load_openapi_spec()

    wat_summary = spec["components"]["schemas"]["WatOperatorSummary"]
    summary_props = wat_summary["properties"]
    assert summary_props["integrity_severity"]["enum"] == ["healthy", "warning", "critical"]
    assert "affected_lanes" in summary_props
    assert "event_ts" in summary_props
    assert "correlation_id" in summary_props
    assert summary_props["operator_verbosity"]["default"] == "minimal"
    assert "warning_context" in summary_props
    assert "warning_correlation_id" in summary_props

    shadow_props = spec["components"]["schemas"]["ShadowValidationConfig"]["properties"]
    assert shadow_props["partial_validation_default"]["default"] == "non_admissible"
    assert shadow_props["replay_binding_escalation_threshold"]["default"] == 4
    assert shadow_props["partial_validation_requires_confirmation"]["default"] is True

    revocation_props = spec["components"]["schemas"]["RevocationConfig"]["properties"]
    assert revocation_props["mode"]["enum"] == ["bounded_eventual_consistency"]
    assert revocation_props["revocation_confirmation_required"]["default"] is True
    assert revocation_props["auto_escalate_confirmed_revocations"]["default"] is False

    policy_props = spec["components"]["schemas"]["GovernancePolicy"]["properties"]
    assert policy_props["operator_verbosity"]["default"] == "minimal"


def test_openapi_bind_operator_summary_surface_locked() -> None:
    """Bind operator summary must preserve minimal-default contract semantics."""
    spec = _load_openapi_spec()
    bind_summary = spec["components"]["schemas"]["BindOperatorSummary"]
    summary_props = bind_summary["properties"]
    assert "bind_state" in summary_props
    assert "bind_outcome" in summary_props
    assert "bind_reason_code" in summary_props
    assert "bind_receipt_id" in summary_props
    assert "execution_intent_id" in summary_props
    assert summary_props["operator_verbosity"]["default"] == "minimal"

    decide_props = spec["components"]["schemas"]["DecideResponse"]["properties"]
    assert "bind_operator_summary" in decide_props
    assert "bind_operator_detail" in decide_props
