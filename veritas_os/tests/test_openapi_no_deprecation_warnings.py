"""OpenAPI compatibility tests for Pydantic/FastAPI deprecation handling."""

from __future__ import annotations

import warnings

from fastapi.testclient import TestClient

from veritas_os.api.server import app


def test_openapi_generation_has_no_deprecation_warnings() -> None:
    """Ensure /openapi.json is generated under DeprecationWarning-as-error mode."""
    client = TestClient(app)
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        response = client.get("/openapi.json")

    assert response.status_code == 200
    payload = response.json()
    assert "openapi" in payload
    assert "paths" in payload
    assert "/v1/decide" in payload["paths"]
