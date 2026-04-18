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
