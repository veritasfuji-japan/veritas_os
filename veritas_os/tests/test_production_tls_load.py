"""Production validation tests for TLS headers and lightweight load behavior.

These tests strengthen production validation coverage by checking:
- TLS-oriented response hardening headers
- Burst request behavior under concurrent access
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

import pytest
import requests
from fastapi.testclient import TestClient


_TEST_API_KEY = "production-load-test-key"


@pytest.fixture()
def api_client(monkeypatch):
    """Return a TestClient for production marker tests."""
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    monkeypatch.setenv("VERITAS_GOVERNANCE_ENFORCE_RBAC", "0")
    monkeypatch.setenv("VERITAS_GOVERNANCE_ALLOW_RBAC_BYPASS", "1")
    from veritas_os.api.server import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.production
@pytest.mark.tls
class TestProductionTlsHeaders:
    """Validate API security headers required for TLS deployment posture."""

    def test_strict_transport_security_header_present(self, api_client) -> None:
        """API responses should include HSTS to enforce HTTPS on clients."""
        response = api_client.get("/health")
        assert response.status_code == 200
        assert (
            response.headers.get("Strict-Transport-Security")
            == "max-age=31536000; includeSubDomains"
        )

    def test_core_security_headers_present(self, api_client) -> None:
        """Baseline anti-injection headers should be consistently applied."""
        response = api_client.get("/health")
        assert response.status_code == 200
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert "default-src 'none'" in response.headers.get(
            "Content-Security-Policy", ""
        )


@pytest.mark.production
@pytest.mark.load
class TestProductionLoadSmoke:
    """Run a lightweight concurrent request burst against health endpoint."""

    def test_health_endpoint_handles_burst_requests(self, api_client) -> None:
        """Health endpoint should stay responsive during concurrent bursts."""

        def _single_request() -> int:
            return api_client.get("/health").status_code

        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(lambda _: _single_request(), range(32)))

        assert len(statuses) == 32
        assert all(status == 200 for status in statuses)


@pytest.mark.production
@pytest.mark.external
class TestStagingExternalTlsLoad:
    """Validate TLS posture and lightweight latency budget on staging."""

    @pytest.fixture()
    def staging_base_url(self) -> str:
        """Return staging URL from env and skip when not configured."""
        url = os.environ.get("VERITAS_STAGING_BASE_URL", "").strip()
        if not url:
            pytest.skip("VERITAS_STAGING_BASE_URL is required for @external tests")
        if not url.startswith("https://"):
            pytest.skip("VERITAS_STAGING_BASE_URL must start with https://")
        return url.rstrip("/")

    @pytest.mark.tls
    def test_staging_health_enforces_tls_headers(self, staging_base_url: str) -> None:
        """Staging health endpoint should expose TLS hardening headers."""
        response = requests.get(
            f"{staging_base_url}/health",
            timeout=5,
            verify=True,
        )
        assert response.status_code == 200
        assert (
            response.headers.get("Strict-Transport-Security")
            == "max-age=31536000; includeSubDomains"
        )
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"

    @pytest.mark.load
    def test_staging_health_lightweight_burst_slo(
        self, staging_base_url: str
    ) -> None:
        """Staging health should handle short burst with basic p95 threshold."""

        def _single_request_latency_ms() -> float:
            start = perf_counter()
            response = requests.get(
                f"{staging_base_url}/health",
                timeout=5,
                verify=True,
            )
            assert response.status_code == 200
            return (perf_counter() - start) * 1000.0

        with ThreadPoolExecutor(max_workers=8) as pool:
            latencies_ms = list(
                pool.map(lambda _: _single_request_latency_ms(), range(32))
            )

        assert len(latencies_ms) == 32
        sorted_latencies = sorted(latencies_ms)
        p95_index = int(0.95 * (len(sorted_latencies) - 1))
        p95_ms = sorted_latencies[p95_index]
        assert p95_ms < 800.0
