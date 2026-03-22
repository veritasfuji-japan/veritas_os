# veritas_os/tests/test_api_backend_improvements.py
"""Tests for backend improvements: response time headers, rate limit headers,
enhanced health endpoint, graceful shutdown, and request ID in errors."""
from __future__ import annotations

import os
import time

_TEST_API_KEY = "test-backend-improvements-key"
os.environ["VERITAS_API_KEY"] = _TEST_API_KEY
_AUTH_HEADERS = {"X-API-Key": _TEST_API_KEY}

import pytest
from fastapi.testclient import TestClient

import veritas_os.api.server as server

client = TestClient(server.app)


@pytest.fixture(autouse=True)
def _reset_server_state(monkeypatch):
    """Reset rate limit buckets and shutdown flag before each test."""
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    server._rate_bucket.clear()
    with server._inflight_lock:
        server._shutting_down = False
        server._inflight_count = 0
    yield
    server._rate_bucket.clear()
    with server._inflight_lock:
        server._shutting_down = False
        server._inflight_count = 0


# -------------------------------------------------
# 1. X-Response-Time header
# -------------------------------------------------


class TestResponseTimeHeader:
    def test_response_time_present_on_health(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert "X-Response-Time" in r.headers
        # Should be a valid "NNNms" format
        val = r.headers["X-Response-Time"]
        assert val.endswith("ms")
        ms = float(val.replace("ms", ""))
        assert ms >= 0

    def test_response_time_present_on_authenticated_endpoint(self):
        r = client.get("/v1/status", headers=_AUTH_HEADERS)
        assert r.status_code == 200
        assert "X-Response-Time" in r.headers


# -------------------------------------------------
# 2. X-RateLimit-* headers
# -------------------------------------------------


class TestRateLimitHeaders:
    def test_rate_limit_headers_on_trust_logs(self):
        """Authenticated rate-limited endpoints should return X-RateLimit-* headers."""
        r = client.get("/v1/trust/logs", headers=_AUTH_HEADERS)
        assert r.status_code == 200
        assert "X-RateLimit-Limit" in r.headers
        assert "X-RateLimit-Remaining" in r.headers
        assert "X-RateLimit-Reset" in r.headers

        limit = int(r.headers["X-RateLimit-Limit"])
        remaining = int(r.headers["X-RateLimit-Remaining"])
        reset = int(r.headers["X-RateLimit-Reset"])

        assert limit == server._RATE_LIMIT
        assert remaining == server._RATE_LIMIT - 1
        assert reset > 0

    def test_rate_limit_remaining_decreases(self):
        """Remaining should decrease with each request."""
        r1 = client.get("/v1/trust/logs", headers=_AUTH_HEADERS)
        r2 = client.get("/v1/trust/logs", headers=_AUTH_HEADERS)
        rem1 = int(r1.headers["X-RateLimit-Remaining"])
        rem2 = int(r2.headers["X-RateLimit-Remaining"])
        assert rem2 == rem1 - 1

    def test_no_rate_limit_headers_on_unauthenticated(self):
        """Unauthenticated endpoints like /health should NOT have rate limit headers."""
        r = client.get("/health")
        assert r.status_code == 200
        assert "X-RateLimit-Limit" not in r.headers


# -------------------------------------------------
# 3. Enhanced health endpoint
# -------------------------------------------------


class TestEnhancedHealth:
    def test_health_includes_checks(self):
        """Health endpoint should include dependency checks."""
        r = client.get("/v1/health")
        assert r.status_code == 200
        data = r.json()
        assert "uptime" in data
        assert "status" in data
        assert data["status"] in ("ok", "degraded", "unavailable")
        assert "checks" in data
        checks = data["checks"]
        assert "pipeline" in checks
        assert "memory" in checks
        assert "auth_store" in checks
        assert "runtime_features" in data
        assert "auth_store" in data
        assert "sanitize" in data["runtime_features"]
        assert "atomic_io" in data["runtime_features"]
        # Values should be either "ok", "degraded", or "unavailable"
        assert checks["pipeline"] in ("ok", "unavailable")
        assert checks["memory"] in ("ok", "degraded", "unavailable")
        assert checks["auth_store"] in ("ok", "degraded")
        assert data["runtime_features"]["sanitize"] in ("ok", "degraded")
        assert data["runtime_features"]["atomic_io"] in ("ok", "degraded")

    def test_health_exposes_memory_degradation_details(self, monkeypatch):
        """Non-fatal MemoryStore load issues should surface in /health."""

        class FakeMemoryStore:
            def health_snapshot(self):
                return {
                    "status": "degraded",
                    "last_error": {
                        "stage": "targeted_payload_load",
                        "kind": "episodic",
                        "detail": "JSONDecodeError",
                        "recorded_at": "2026-03-21T00:00:00Z",
                    },
                    "error_counts": {"targeted_payload_load:episodic": 2},
                }

        monkeypatch.setattr(server, "get_memory_store", lambda: FakeMemoryStore())

        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert data["status"] == "degraded"
        assert data["checks"]["memory"] == "degraded"
        assert data["memory_health"]["last_error"]["detail"] == "JSONDecodeError"

    def test_health_ok_reflects_deps(self, monkeypatch):
        """ok field should reflect dependency availability."""
        # Force pipeline unavailable
        monkeypatch.setattr(
            server,
            "_pipeline_state",
            server._LazyState(obj=None, err="forced", attempted=True),
        )
        r = client.get("/health")
        data = r.json()
        assert data["checks"]["pipeline"] == "unavailable"

    def test_health_status_is_unavailable_when_pipeline_is_missing(self, monkeypatch):
        """Top-level health status should distinguish unavailable dependencies."""
        monkeypatch.setattr(server, "get_decision_pipeline", lambda: None)

        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert data["status"] == "unavailable"
        assert data["checks"]["pipeline"] == "unavailable"

    def test_health_runtime_features_show_sanitize_degradation(self, monkeypatch):
        """Health endpoint should expose runtime security degradation."""
        monkeypatch.setattr(server, "_HAS_SANITIZE", False)
        monkeypatch.setattr(server, "_HAS_ATOMIC_IO", False)

        r = client.get("/health")

        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert data["status"] == "degraded"
        assert data["runtime_features"]["sanitize"] == "degraded"
        assert data["runtime_features"]["atomic_io"] == "degraded"

    def test_health_shows_auth_store_degradation(self, monkeypatch):
        """Health endpoint should expose auth-store security degradation."""
        monkeypatch.setattr(
            server,
            "auth_store_health_snapshot",
            lambda: {
                "status": "degraded",
                "requested_mode": "redis",
                "effective_mode": "memory",
                "failure_mode": "closed",
                "distributed_safe": False,
                "reasons": ["redis_store_unavailable"],
            },
        )

        r = client.get("/health")

        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert data["status"] == "degraded"
        assert data["checks"]["auth_store"] == "degraded"
        assert data["auth_store"]["requested_mode"] == "redis"
        assert data["auth_store"]["effective_mode"] == "memory"


# -------------------------------------------------
# 4. Graceful shutdown
# -------------------------------------------------


    def test_metrics_exposes_auth_store_degradation(self, monkeypatch):
        """Metrics endpoint should expose auth-store posture for audit visibility."""
        monkeypatch.setattr(
            server,
            "auth_store_health_snapshot",
            lambda: {
                "status": "degraded",
                "requested_mode": "redis",
                "effective_mode": "memory",
                "failure_mode": "closed",
                "distributed_safe": False,
                "reasons": ["redis_store_unavailable"],
            },
        )

        r = client.get("/v1/metrics", headers=_AUTH_HEADERS)

        assert r.status_code == 200
        data = r.json()
        assert data["auth_store_mode"] == "redis"
        assert data["auth_store_effective_mode"] == "memory"
        assert data["auth_store_status"] == "degraded"
        assert data["auth_store_failure_mode"] == "closed"
        assert data["auth_store_reasons"] == ["redis_store_unavailable"]


class TestGracefulShutdown:
    def test_shutdown_returns_503(self):
        """When shutting down, requests should get 503 with Retry-After."""
        with server._inflight_lock:
            server._shutting_down = True

        r = client.get("/health")
        assert r.status_code == 503
        data = r.json()
        assert data["ok"] is False
        assert "shutting down" in data["error"].lower()
        assert r.headers.get("Retry-After") == "5"

    def test_inflight_snapshot(self):
        """_inflight_snapshot should return current state."""
        snap = server._inflight_snapshot()
        assert "inflight" in snap
        assert "shutting_down" in snap
        assert snap["shutting_down"] is False
        assert snap["inflight"] == 0


# -------------------------------------------------
# 5. Request ID in error responses
# -------------------------------------------------


class TestRequestIdInErrors:
    def test_validation_error_includes_request_id(self):
        """422 validation errors should include request_id for traceability."""
        r = client.post(
            "/v1/decide",
            headers=_AUTH_HEADERS,
            json={"query": "test", "min_evidence": -999},  # Invalid range
        )
        assert r.status_code == 422
        data = r.json()
        assert "request_id" in data
        # request_id should be a non-empty string
        assert isinstance(data["request_id"], str)
        assert len(data["request_id"]) > 0
