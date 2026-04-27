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


def _extract_bind_summary_property_keys_from_yaml() -> list[str]:
    """Extract BindSummary property keys from raw YAML to detect duplicate keys."""
    repo_root = Path(__file__).resolve().parents[2]
    spec_path = repo_root / "openapi.yaml"
    lines = spec_path.read_text(encoding="utf-8").splitlines()

    in_bind_summary = False
    in_properties = False
    keys: list[str] = []

    for raw_line in lines:
        if raw_line.startswith("    BindSummary:"):
            in_bind_summary = True
            in_properties = False
            continue
        if in_bind_summary and raw_line.startswith("    ") and not raw_line.startswith("      "):
            break
        if not in_bind_summary:
            continue
        if raw_line.startswith("      properties:"):
            in_properties = True
            continue
        if in_properties and raw_line.startswith("      ") and not raw_line.startswith("        "):
            break
        if (
            not in_properties
            or not raw_line.startswith("        ")
            or raw_line.startswith("          ")
        ):
            continue

        stripped = raw_line.strip()
        if stripped.endswith(":") and not stripped.startswith("- "):
            keys.append(stripped[:-1])

    return keys


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
    assert decide_schema["actionability_status"]["enum"] == [
        "reviewable_only",
        "bind_required_before_execution",
        "actionable_after_bind",
        "blocked",
        "human_review_required",
    ]
    assert decide_schema["requires_bind_before_execution"]["type"] == "boolean"
    assert decide_schema["bound_execution_intent_id"]["nullable"] is True
    assert decide_schema["unbound_execution_warning"]["nullable"] is True
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


def test_openapi_system_resume_response_includes_bind_fields() -> None:
    """System resume mutation route should document bind lineage fields."""
    spec = _load_openapi_spec()
    schema = (
        spec["paths"]["/v1/system/resume"]["post"]["responses"]["200"]["content"]
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
    assert "Reference/locator" in wat_props["observable_digest_ref"]["description"]


def test_openapi_wat_shadow_requests_define_observable_digest_ref_contract() -> None:
    """WAT shadow request schemas should expose locator-first digest linkage."""
    spec = _load_openapi_spec()
    issue_props = spec["components"]["schemas"]["WatIssueShadowRequest"]["properties"]
    validate_props = spec["components"]["schemas"]["WatValidateShadowRequest"]["properties"]

    assert "observable_digest_ref" in issue_props
    assert "locator/reference" in issue_props["observable_digest_ref"]["description"]
    assert "Legacy transitional field" in issue_props["observable_digest"]["description"]

    assert "observable_digest_ref" in validate_props
    assert "locator/reference" in validate_props["observable_digest_ref"]["description"]
    assert "Legacy transitional field" in validate_props["observable_digest"]["description"]


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
    assert "always require explicit confirmation" in revocation_props["revocation_confirmation_required"]["description"]
    assert "Schema-only v1 placeholder" in revocation_props["auto_escalate_confirmed_revocations"]["description"]

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


def test_openapi_bind_summary_surface_nullable_and_duplicate_free() -> None:
    """BindSummary must preserve optional target fields without YAML key shadowing."""
    spec = _load_openapi_spec()
    bind_summary_props = spec["components"]["schemas"]["BindSummary"]["properties"]
    expected_optional_target_fields = {
        "target_path",
        "target_type",
        "target_path_type",
        "target_label",
        "operator_surface",
        "relevant_ui_href",
    }

    for field in expected_optional_target_fields:
        schema = bind_summary_props[field]
        assert "anyOf" in schema
        assert any(branch.get("type") == "null" for branch in schema["anyOf"])

    raw_property_keys = _extract_bind_summary_property_keys_from_yaml()
    assert len(raw_property_keys) == len(set(raw_property_keys))
    assert expected_optional_target_fields.issubset(set(raw_property_keys))
