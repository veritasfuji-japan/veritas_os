"""Production validation tests for TLS headers and lightweight load behavior.

These tests strengthen production validation coverage by checking:
- TLS-oriented response hardening headers
- Burst request behavior under concurrent access
- Latency budget enforcement with percentile summaries
- Certificate configuration hooks for deployment validation
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

import pytest
import requests
from fastapi.testclient import TestClient


logger = logging.getLogger(__name__)

_TEST_API_KEY = "production-load-test-key"


def _latency_summary(latencies_ms: list[float]) -> dict[str, float]:
    """Compute latency percentile summary from a list of measurements."""
    sorted_lat = sorted(latencies_ms)
    n = len(sorted_lat)
    return {
        "count": n,
        "min_ms": sorted_lat[0] if n else 0,
        "p50_ms": sorted_lat[n // 2] if n else 0,
        "p90_ms": sorted_lat[int(0.90 * (n - 1))] if n else 0,
        "p95_ms": sorted_lat[int(0.95 * (n - 1))] if n else 0,
        "p99_ms": sorted_lat[int(0.99 * (n - 1))] if n else 0,
        "max_ms": sorted_lat[-1] if n else 0,
        "avg_ms": sum(latencies_ms) / n if n else 0,
    }


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

    def test_response_time_header_present(self, api_client) -> None:
        """X-Response-Time must be present for observability."""
        response = api_client.get("/health")
        assert response.status_code == 200
        assert "X-Response-Time" in response.headers, (
            "X-Response-Time header missing — observability degraded"
        )

    def test_security_headers_on_error_responses(self, api_client) -> None:
        """Security headers must be present even on 404 error responses."""
        response = api_client.get("/nonexistent-path-for-tls-test")
        # Security headers should be present regardless of status code
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"


@pytest.mark.production
@pytest.mark.load
class TestProductionLoadSmoke:
    """Run a lightweight concurrent request burst against health endpoint."""

    def test_health_endpoint_handles_burst_requests(self, api_client) -> None:
        """Health endpoint should stay responsive during concurrent bursts.

        Pass/fail criteria:
            - All 32 requests must return HTTP 200
            - p95 latency must be < 500ms
            - Error rate must be 0%
        """
        latencies_ms: list[float] = []
        errors = 0

        def _single_request() -> int:
            start = perf_counter()
            status = api_client.get("/health").status_code
            latencies_ms.append((perf_counter() - start) * 1000.0)
            return status

        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(lambda _: _single_request(), range(32)))

        errors = sum(1 for s in statuses if s != 200)
        summary = _latency_summary(latencies_ms)

        # Log summary for visibility in CI output
        logger.info(
            "Load burst summary: count=%d avg=%.1fms p50=%.1fms "
            "p95=%.1fms p99=%.1fms max=%.1fms errors=%d",
            summary["count"],
            summary["avg_ms"],
            summary["p50_ms"],
            summary["p95_ms"],
            summary["p99_ms"],
            summary["max_ms"],
            errors,
        )

        assert len(statuses) == 32
        assert errors == 0, f"Expected 0 errors, got {errors}"
        assert summary["p95_ms"] < 500.0, (
            f"p95 latency {summary['p95_ms']:.1f}ms exceeds 500ms budget"
        )

    def test_governance_endpoint_burst_load(self, api_client) -> None:
        """Governance policy endpoint should handle concurrent reads.

        Pass/fail criteria:
            - All 16 requests must return HTTP 200
            - p95 latency must be < 1000ms
        """
        latencies_ms: list[float] = []
        headers = {"X-API-Key": _TEST_API_KEY}

        def _single_request() -> int:
            start = perf_counter()
            status = api_client.get(
                "/v1/governance/policy", headers=headers
            ).status_code
            latencies_ms.append((perf_counter() - start) * 1000.0)
            return status

        with ThreadPoolExecutor(max_workers=4) as pool:
            statuses = list(pool.map(lambda _: _single_request(), range(16)))

        errors = sum(1 for s in statuses if s != 200)
        summary = _latency_summary(latencies_ms)

        logger.info(
            "Governance burst summary: count=%d avg=%.1fms p50=%.1fms "
            "p95=%.1fms max=%.1fms errors=%d",
            summary["count"],
            summary["avg_ms"],
            summary["p50_ms"],
            summary["p95_ms"],
            summary["max_ms"],
            errors,
        )

        assert errors == 0, f"Expected 0 errors, got {errors}"
        assert summary["p95_ms"] < 1000.0, (
            f"Governance p95 latency {summary['p95_ms']:.1f}ms exceeds 1000ms"
        )


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

    @pytest.mark.tls
    def test_staging_tls_cert_not_expiring(self, staging_base_url: str) -> None:
        """Staging TLS certificate should have > 30 days validity remaining."""
        import ssl
        import socket
        from datetime import datetime, timezone

        host = staging_base_url.replace("https://", "").split("/")[0].split(":")[0]
        port = 443

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_default_certs()
        with socket.create_connection((host, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                not_after = cert.get("notAfter", "")
                # Parse SSL date format: 'Mon DD HH:MM:SS YYYY GMT'
                expiry = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                expiry = expiry.replace(tzinfo=timezone.utc)
                days_left = (expiry - datetime.now(timezone.utc)).days
                assert days_left > 30, (
                    f"TLS cert expires in {days_left} days (< 30 day threshold)"
                )
                logger.info("Staging TLS cert valid for %d more days", days_left)

    @pytest.mark.load
    def test_staging_health_lightweight_burst_slo(
        self, staging_base_url: str
    ) -> None:
        """Staging health should handle short burst with p95 < 800ms.

        Pass/fail criteria:
            - 32 concurrent HTTPS requests to /health
            - All must return HTTP 200
            - p95 latency must be < 800ms
        """
        results: list[tuple[float, bool]] = []

        def _single_request() -> tuple[float, bool]:
            start = perf_counter()
            try:
                response = requests.get(
                    f"{staging_base_url}/health",
                    timeout=5,
                    verify=True,
                )
                elapsed = (perf_counter() - start) * 1000.0
                return elapsed, response.status_code == 200
            except requests.RequestException:
                elapsed = (perf_counter() - start) * 1000.0
                return elapsed, False

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(
                pool.map(lambda _: _single_request(), range(32))
            )

        errors = sum(1 for _, ok in results if not ok)
        latencies_ms = [lat for lat, ok in results if ok]

        summary = _latency_summary(latencies_ms) if latencies_ms else {}

        logger.info(
            "Staging burst summary: count=%d avg=%.1fms p50=%.1fms "
            "p95=%.1fms p99=%.1fms max=%.1fms errors=%d",
            summary.get("count", 0),
            summary.get("avg_ms", 0),
            summary.get("p50_ms", 0),
            summary.get("p95_ms", 0),
            summary.get("p99_ms", 0),
            summary.get("max_ms", 0),
            errors,
        )

        assert len(results) == 32
        assert errors == 0, f"Expected 0 errors, got {errors}"
        p95_ms = summary.get("p95_ms", 0)
        assert p95_ms < 800.0, (
            f"Staging p95 latency {p95_ms:.1f}ms exceeds 800ms SLO"
        )
