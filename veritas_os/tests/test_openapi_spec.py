"""OpenAPI specification regression tests.

This module validates that ``openapi.yaml`` remains parseable and aligned with
critical API routes implemented by ``veritas_os.api.server``.
"""

from __future__ import annotations

from pathlib import Path

import yaml


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
