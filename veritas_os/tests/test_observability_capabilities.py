"""Tests for read-only observability capabilities endpoint."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from veritas_os.api import server
from veritas_os.api import routes_observability


def _headers() -> dict[str, str]:
    return {"X-API-Key": "test-observability-key"}


def test_observability_capabilities_ok_true(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", "test-observability-key")
    monkeypatch.setenv("VERITAS_API_KEYS_JSON", '{"test-observability-key":"auditor"}')

    client = TestClient(server.app)
    response = client.get("/v1/observability/capabilities", headers=_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["observability"]["docs"]["governance_trace_span_chain_en"]


def test_opentelemetry_importable_false_does_not_crash(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", "test-observability-key")
    monkeypatch.setenv("VERITAS_API_KEYS_JSON", '{"test-observability-key":"auditor"}')
    monkeypatch.setattr(routes_observability.tracing, "otel_trace", None)

    client = TestClient(server.app)
    response = client.get("/v1/observability/capabilities", headers=_headers())

    assert response.status_code == 200
    assert response.json()["observability"]["tracing"]["opentelemetry_importable"] is False


def test_exporter_configured_false_without_env(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", "test-observability-key")
    monkeypatch.setenv("VERITAS_API_KEYS_JSON", '{"test-observability-key":"auditor"}')
    for name in ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_SERVICE_NAME", "OTEL_TRACES_EXPORTER"):
        monkeypatch.delenv(name, raising=False)

    client = TestClient(server.app)
    response = client.get("/v1/observability/capabilities", headers=_headers())

    assert response.status_code == 200
    assert response.json()["observability"]["tracing"]["exporter_configured"] is False


def test_exporter_configured_true_with_env(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", "test-observability-key")
    monkeypatch.setenv("VERITAS_API_KEYS_JSON", '{"test-observability-key":"auditor"}')
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://collector.internal.example")

    client = TestClient(server.app)
    response = client.get("/v1/observability/capabilities", headers=_headers())

    assert response.status_code == 200
    assert response.json()["observability"]["tracing"]["exporter_configured"] is True


def test_endpoint_never_leaks_raw_sensitive_env_values(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", "test-observability-key")
    monkeypatch.setenv("VERITAS_API_KEYS_JSON", '{"test-observability-key":"auditor"}')
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
    monkeypatch.setenv("VERITAS_API_KEY", "test-observability-key")
    monkeypatch.setenv("VERITAS_API_KEYS_JSON", '{"test-observability-key":"auditor"}')
    called = []

    def _fail_append(_entry):
        called.append(True)

    monkeypatch.setattr(server, "append_trust_log", _fail_append)

    client = TestClient(server.app)
    response = client.get("/v1/observability/capabilities", headers=_headers())

    assert response.status_code == 200
    assert called == []
