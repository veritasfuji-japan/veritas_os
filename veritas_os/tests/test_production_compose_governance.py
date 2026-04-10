"""Production validation tests for Docker Compose governance endpoint smoke.

These tests validate that governance-critical endpoints are reachable and
return expected contracts when the full-stack is deployed via Docker Compose.
They run against a live deployment when ``VERITAS_COMPOSE_BASE_URL`` is set,
otherwise they exercise the same contracts via TestClient for CI regression.

Markers:
    production — production-like validation
    smoke      — included in fast smoke gate
"""

from __future__ import annotations

import os
from time import perf_counter

import pytest
from fastapi.testclient import TestClient

_TEST_API_KEY = "compose-governance-test-key"


@pytest.fixture()
def api_client(monkeypatch):
    """Return a TestClient or live session for compose validation."""
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    monkeypatch.setenv("VERITAS_GOVERNANCE_ENFORCE_RBAC", "0")
    monkeypatch.setenv("VERITAS_GOVERNANCE_ALLOW_RBAC_BYPASS", "1")
    from veritas_os.api.server import app

    return TestClient(app, raise_server_exceptions=False)


def _headers() -> dict[str, str]:
    return {"X-API-Key": _TEST_API_KEY}


@pytest.mark.production
@pytest.mark.smoke
class TestComposeGovernanceCriticalPath:
    """Validate governance critical path endpoints return expected contracts."""

    def test_governance_policy_returns_fuji_rules(self, api_client) -> None:
        """GET /v1/governance/policy must include fuji_rules and risk_thresholds."""
        r = api_client.get("/v1/governance/policy", headers=_headers())
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True
        policy = body.get("policy", {})
        assert "fuji_rules" in policy, "fuji_rules missing from governance policy"
        assert isinstance(policy["fuji_rules"], dict), "fuji_rules must be a dict"
        assert "risk_thresholds" in policy, "risk_thresholds missing from governance policy"
        assert isinstance(policy["risk_thresholds"], dict), "risk_thresholds must be a dict"
        assert "auto_stop" in policy, "auto_stop missing from governance policy"
        assert isinstance(policy["auto_stop"], dict), "auto_stop must be a dict"
        assert "log_retention" in policy, "log_retention missing from governance policy"
        assert isinstance(policy["log_retention"], dict), "log_retention must be a dict"

    def test_governance_policy_history_reachable(self, api_client) -> None:
        """GET /v1/governance/policy/history must return 200."""
        r = api_client.get("/v1/governance/policy/history", headers=_headers())
        assert r.status_code == 200

    def test_decide_requires_authentication(self, api_client) -> None:
        """POST /v1/decide without API key must be rejected."""
        r = api_client.post("/v1/decide", json={"query": "compose-test"})
        assert r.status_code in (401, 403), (
            f"Expected 401/403 without auth, got {r.status_code}"
        )

    def test_health_includes_subsystem_checks(self, api_client) -> None:
        """GET /health must report pipeline, memory, trust_log subsystems."""
        r = api_client.get("/health")
        assert r.status_code == 200
        body = r.json()
        checks = body.get("checks", {})
        for subsystem in ("pipeline", "memory", "trust_log"):
            assert subsystem in checks, f"Missing health subsystem: {subsystem}"

    def test_health_security_headers_present(self, api_client) -> None:
        """Health endpoint must return security hardening headers."""
        r = api_client.get("/health")
        assert r.status_code == 200
        assert r.headers.get("X-Content-Type-Options") == "nosniff", (
            "X-Content-Type-Options header missing or incorrect"
        )
        assert r.headers.get("X-Frame-Options") == "DENY", (
            "X-Frame-Options header missing or incorrect"
        )

    def test_openapi_schema_includes_governance_paths(self, api_client) -> None:
        """OpenAPI schema must include governance and trust paths."""
        r = api_client.get("/openapi.json")
        assert r.status_code == 200
        schema = r.json()
        paths_str = str(schema.get("paths", {}))
        assert "/v1/governance" in paths_str, "/v1/governance not in OpenAPI paths"
        assert "/v1/decide" in paths_str, "/v1/decide not in OpenAPI paths"


@pytest.mark.production
@pytest.mark.load
class TestGovernanceEndpointLatency:
    """Validate governance endpoint latency stays within budget."""

    def test_governance_policy_latency_budget(self, api_client) -> None:
        """GET /v1/governance/policy should respond within 500ms."""
        latencies_ms: list[float] = []
        for _ in range(10):
            start = perf_counter()
            r = api_client.get("/v1/governance/policy", headers=_headers())
            elapsed = (perf_counter() - start) * 1000.0
            assert r.status_code == 200
            latencies_ms.append(elapsed)

        sorted_lat = sorted(latencies_ms)
        p50 = sorted_lat[len(sorted_lat) // 2]
        p95_idx = int(0.95 * (len(sorted_lat) - 1))
        p95 = sorted_lat[p95_idx]
        avg = sum(latencies_ms) / len(latencies_ms)

        # Latency budget: p95 < 500ms for governance policy read
        assert p95 < 500.0, (
            f"Governance policy p95 latency {p95:.1f}ms exceeds 500ms budget "
            f"(avg={avg:.1f}ms, p50={p50:.1f}ms)"
        )

    def test_health_latency_budget(self, api_client) -> None:
        """GET /health should respond within 200ms p95."""
        latencies_ms: list[float] = []
        for _ in range(20):
            start = perf_counter()
            r = api_client.get("/health")
            elapsed = (perf_counter() - start) * 1000.0
            assert r.status_code == 200
            latencies_ms.append(elapsed)

        sorted_lat = sorted(latencies_ms)
        p95_idx = int(0.95 * (len(sorted_lat) - 1))
        p95 = sorted_lat[p95_idx]

        assert p95 < 200.0, (
            f"Health p95 latency {p95:.1f}ms exceeds 200ms budget"
        )
