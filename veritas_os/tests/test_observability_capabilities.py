"""Tests for read-only observability capabilities endpoint."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from veritas_os.api import server
from veritas_os.api import routes_observability


def _headers() -> dict[str, str]:
    return {"X-API-Key": "test-observability-key"}


def _set_api_keys(monkeypatch, role: str = "auditor") -> None:
    """Configure auth via VERITAS_API_KEYS and disable legacy single-key fallback."""
    monkeypatch.delenv("VERITAS_API_KEY", raising=False)
    monkeypatch.delenv("VERITAS_API_KEYS_JSON", raising=False)
    monkeypatch.setenv(
        "VERITAS_API_KEYS",
        f'[{{"key":"test-observability-key","role":"{role}"}}]',
    )


def test_observability_capabilities_ok_true(monkeypatch):
    _set_api_keys(monkeypatch, role="auditor")

    client = TestClient(server.app)
    response = client.get("/v1/observability/capabilities", headers=_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["observability"]["docs"]["governance_trace_span_chain_en"]


def test_opentelemetry_importable_false_does_not_crash(monkeypatch):
    _set_api_keys(monkeypatch, role="auditor")
    monkeypatch.setattr(routes_observability.tracing, "otel_trace", None)

    client = TestClient(server.app)
    response = client.get("/v1/observability/capabilities", headers=_headers())

    assert response.status_code == 200
    assert response.json()["observability"]["tracing"]["opentelemetry_importable"] is False


def test_exporter_configured_false_without_env(monkeypatch):
    _set_api_keys(monkeypatch, role="auditor")
    for name in ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_SERVICE_NAME", "OTEL_TRACES_EXPORTER"):
        monkeypatch.delenv(name, raising=False)

    client = TestClient(server.app)
    response = client.get("/v1/observability/capabilities", headers=_headers())

    assert response.status_code == 200
    assert response.json()["observability"]["tracing"]["exporter_configured"] is False


def test_exporter_configured_true_with_env(monkeypatch):
    _set_api_keys(monkeypatch, role="auditor")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://collector.internal.example")

    client = TestClient(server.app)
    response = client.get("/v1/observability/capabilities", headers=_headers())

    assert response.status_code == 200
    assert response.json()["observability"]["tracing"]["exporter_configured"] is True


def test_endpoint_never_leaks_raw_sensitive_env_values(monkeypatch):
    _set_api_keys(monkeypatch, role="auditor")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://collector.internal.example")
    monkeypatch.setenv("DUMMY_API_TOKEN", "raw-token-value")
    monkeypatch.setenv("DUMMY_SECRET", "raw-secret-value")

    client = TestClient(server.app)
    response = client.get("/v1/observability/capabilities", headers=_headers())

    assert response.status_code == 200
    body_str = json.dumps(response.json())
    assert "https://collector.internal.example" not in body_str
    assert "raw-token-value" not in body_str
    assert "raw-secret-value" not in body_str


def test_endpoint_is_read_only_and_no_audit_append(monkeypatch):
    _set_api_keys(monkeypatch, role="auditor")
    called = []

    def _fail_append(_entry):
        called.append(True)

    monkeypatch.setattr(server, "append_trust_log", _fail_append)

    client = TestClient(server.app)
    response = client.get("/v1/observability/capabilities", headers=_headers())

    assert response.status_code == 200
    assert called == []


def test_non_governance_read_role_gets_403(monkeypatch):
    _set_api_keys(monkeypatch, role="operator")

    client = TestClient(server.app)
    response = client.get("/v1/observability/capabilities", headers=_headers())

    assert response.status_code == 403


def test_log_format_json(monkeypatch):
    _set_api_keys(monkeypatch, role="auditor")
    monkeypatch.setenv("VERITAS_LOG_FORMAT", "json")

    client = TestClient(server.app)
    response = client.get("/v1/observability/capabilities", headers=_headers())

    assert response.status_code == 200
    assert response.json()["observability"]["structured_logging"]["format"] == "json"


def test_log_format_text(monkeypatch):
    _set_api_keys(monkeypatch, role="auditor")
    monkeypatch.setenv("VERITAS_LOG_FORMAT", "text")

    client = TestClient(server.app)
    response = client.get("/v1/observability/capabilities", headers=_headers())

    assert response.status_code == 200
    assert response.json()["observability"]["structured_logging"]["format"] == "text"


def test_log_format_whitespace_returns_text(monkeypatch):
    _set_api_keys(monkeypatch, role="auditor")
    monkeypatch.setenv("VERITAS_LOG_FORMAT", "   ")

    client = TestClient(server.app)
    response = client.get("/v1/observability/capabilities", headers=_headers())

    assert response.status_code == 200
    assert response.json()["observability"]["structured_logging"]["format"] == "text"


def test_log_format_invalid_returns_text(monkeypatch):
    _set_api_keys(monkeypatch, role="auditor")
    monkeypatch.setenv("VERITAS_LOG_FORMAT", "invalid")

    client = TestClient(server.app)
    response = client.get("/v1/observability/capabilities", headers=_headers())

    assert response.status_code == 200
    assert response.json()["observability"]["structured_logging"]["format"] == "text"
