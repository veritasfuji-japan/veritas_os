"""Production-like smoke tests for VERITAS OS deployment verification.

These tests validate that the FastAPI application boots correctly, core
endpoints respond, and the docker-compose service topology is coherent.
They run against the in-process ``TestClient`` by default and can also
target a live deployment when ``VERITAS_SMOKE_BASE_URL`` is set.

Markers:
    smoke       — lightweight deployment verification
    production  — production-like validation (excluded from default CI)
"""

from __future__ import annotations

import logging
import os
import subprocess
import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_TEST_API_KEY = "smoke-test-key"
_ROOT = Path(__file__).resolve().parents[2]  # repo root


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def api_client(monkeypatch):
    """Return a TestClient wired to the VERITAS app with a test API key."""
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    # Disable governance RBAC for smoke testing
    monkeypatch.setenv("VERITAS_GOVERNANCE_ENFORCE_RBAC", "0")
    monkeypatch.setenv("VERITAS_GOVERNANCE_ALLOW_RBAC_BYPASS", "1")
    from veritas_os.api.server import app

    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Smoke tests (always safe to run — no external deps)
# ---------------------------------------------------------------------------


@pytest.mark.smoke
class TestHealthEndpoint:
    """Verify /health returns the documented contract."""

    def test_health_ok(self, api_client):
        r = api_client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert "ok" in body
        assert "status" in body
        assert "checks" in body

    def test_health_v1_alias(self, api_client):
        r = api_client.get("/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] in ("ok", "degraded", "unavailable")

    def test_response_time_header(self, api_client):
        r = api_client.get("/health")
        assert "X-Response-Time" in r.headers

    def test_health_checks_sections(self, api_client):
        body = api_client.get("/health").json()
        checks = body.get("checks", {})
        # Core subsystems must be reported
        for key in ("pipeline", "memory", "trust_log"):
            assert key in checks, f"Missing health check: {key}"


@pytest.mark.smoke
class TestOpenAPISchema:
    """Ensure OpenAPI schema is generated and well-formed."""

    def test_openapi_json(self, api_client):
        r = api_client.get("/openapi.json")
        assert r.status_code == 200
        schema = r.json()
        assert schema.get("openapi", "").startswith("3.")
        assert "/v1/decide" in str(schema.get("paths", {}))

    def test_docs_available(self, api_client):
        r = api_client.get("/docs")
        assert r.status_code == 200


@pytest.mark.smoke
class TestDecideEndpointContract:
    """Validate /v1/decide API contract (mock pipeline, real HTTP)."""

    def test_decide_requires_api_key(self, api_client):
        r = api_client.post("/v1/decide", json={"query": "test"})
        assert r.status_code in (401, 403)

    def test_decide_with_valid_key(self, api_client):
        r = api_client.post(
            "/v1/decide",
            headers={"X-API-Key": _TEST_API_KEY},
            json={"query": "What is 2+2?", "context": {"user_id": "smoke"}},
        )
        # Pipeline may not be initialised — 200 or 503 both acceptable
        assert r.status_code in (200, 503)
        body = r.json()
        # Either success or structured error
        assert "ok" in body or "chosen" in body or "error" in body


@pytest.mark.smoke
class TestGovernanceEndpointContract:
    """Validate /v1/governance endpoints respond correctly."""

    def test_governance_get_policy(self, api_client):
        r = api_client.get(
            "/v1/governance/policy",
            headers={"X-API-Key": _TEST_API_KEY},
        )
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True
        policy = body.get("policy", {})
        assert "fuji_rules" in policy
        assert "risk_thresholds" in policy

    def test_governance_policy_history(self, api_client):
        r = api_client.get(
            "/v1/governance/policy/history",
            headers={"X-API-Key": _TEST_API_KEY},
        )
        assert r.status_code == 200


@pytest.mark.smoke
class TestDockerComposeValid:
    """Validate docker-compose.yml is syntactically valid."""

    def test_compose_file_exists(self):
        compose = _ROOT / "docker-compose.yml"
        assert compose.exists(), "docker-compose.yml missing from repo root"

    def test_compose_defines_services(self):
        import yaml

        compose = _ROOT / "docker-compose.yml"
        cfg = yaml.safe_load(compose.read_text())
        services = cfg.get("services", {})
        assert "backend" in services
        assert "frontend" in services

    def test_backend_healthcheck_defined(self):
        import yaml

        compose = _ROOT / "docker-compose.yml"
        cfg = yaml.safe_load(compose.read_text())
        backend = cfg["services"]["backend"]
        assert "healthcheck" in backend

    def test_frontend_depends_on_backend(self):
        import yaml

        compose = _ROOT / "docker-compose.yml"
        cfg = yaml.safe_load(compose.read_text())
        frontend = cfg["services"]["frontend"]
        deps = frontend.get("depends_on", {})
        assert "backend" in deps


@pytest.mark.smoke
class TestDockerfileValid:
    """Validate Dockerfile is present and uses multi-stage build."""

    def test_dockerfile_exists(self):
        assert (_ROOT / "Dockerfile").exists()

    def test_dockerfile_has_healthcheck(self):
        content = (_ROOT / "Dockerfile").read_text()
        assert "HEALTHCHECK" in content or "healthcheck" in content.lower()


@pytest.mark.smoke
class TestStorageBackendVisibility:
    """Verify /health and /status expose storage_backends field."""

    def test_health_reports_storage_backends(self, api_client):
        r = api_client.get("/health")
        assert r.status_code == 200
        body = r.json()
        backends = body.get("storage_backends")
        assert backends is not None, "Missing storage_backends in /health"
        assert "memory" in backends
        assert "trustlog" in backends

    def test_status_reports_storage_backends(self, api_client):
        r = api_client.get("/status")
        assert r.status_code == 200
        body = r.json()
        backends = body.get("storage_backends")
        assert backends is not None, "Missing storage_backends in /status"
        assert "memory" in backends
        assert "trustlog" in backends


@pytest.mark.smoke
class TestComposePostgresqlBackend:
    """Verify docker-compose.yml configures PostgreSQL as default backend."""

    def test_compose_backend_env_vars(self):
        import yaml

        compose = _ROOT / "docker-compose.yml"
        cfg = yaml.safe_load(compose.read_text())
        backend_env = cfg["services"]["backend"]["environment"]
        # Backend must explicitly set memory + trustlog to postgresql
        mem = backend_env.get("VERITAS_MEMORY_BACKEND", "")
        tlog = backend_env.get("VERITAS_TRUSTLOG_BACKEND", "")
        assert "postgresql" in mem, (
            f"VERITAS_MEMORY_BACKEND should default to postgresql, got {mem!r}"
        )
        assert "postgresql" in tlog, (
            f"VERITAS_TRUSTLOG_BACKEND should default to postgresql, got {tlog!r}"
        )

    def test_compose_database_url_set(self):
        import yaml

        compose = _ROOT / "docker-compose.yml"
        cfg = yaml.safe_load(compose.read_text())
        backend_env = cfg["services"]["backend"]["environment"]
        db_url = backend_env.get("VERITAS_DATABASE_URL", "")
        assert "postgres" in db_url, (
            f"VERITAS_DATABASE_URL should point to postgres, got {db_url!r}"
        )

    def test_compose_backend_depends_on_postgres(self):
        import yaml

        compose = _ROOT / "docker-compose.yml"
        cfg = yaml.safe_load(compose.read_text())
        deps = cfg["services"]["backend"].get("depends_on", {})
        assert "postgres" in deps, "backend must depend on postgres service"


@pytest.mark.smoke
class TestBackendSelectionWithEnv:
    """Verify backend selection reflects environment variables."""

    def test_postgresql_backend_reported_in_health(self, monkeypatch):
        monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
        monkeypatch.setenv("VERITAS_GOVERNANCE_ENFORCE_RBAC", "0")
        monkeypatch.setenv("VERITAS_GOVERNANCE_ALLOW_RBAC_BYPASS", "1")
        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "postgresql")
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
        monkeypatch.setenv("VERITAS_DATABASE_URL", "postgresql://x:x@localhost/x")
        from veritas_os.api.server import app

        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/health")
        assert r.status_code == 200
        backends = r.json().get("storage_backends", {})
        assert backends.get("memory") == "postgresql"
        assert backends.get("trustlog") == "postgresql"

    def test_json_backend_reported_in_health(self, monkeypatch):
        monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
        monkeypatch.setenv("VERITAS_GOVERNANCE_ENFORCE_RBAC", "0")
        monkeypatch.setenv("VERITAS_GOVERNANCE_ALLOW_RBAC_BYPASS", "1")
        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "json")
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "jsonl")
        monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)
        from veritas_os.api.server import app

        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/health")
        assert r.status_code == 200
        backends = r.json().get("storage_backends", {})
        assert backends.get("memory") == "json"
        assert backends.get("trustlog") == "jsonl"


@pytest.mark.smoke
class TestPostgresqlBackendReadWrite:
    """Verify that Memory/TrustLog read/write operations are exercised.

    These tests use the default (file) backend to prove that backend
    read/write paths are exercisable through the API.  When running
    under ``docker compose`` with PostgreSQL, the same API calls exercise
    the PostgreSQL backend — confirming actual database usage, not just
    environment variable plumbing.
    """

    def test_memory_write_and_read(self, api_client):
        """Write a memory entry via the API and read it back."""
        key = "__smoke_pg_rw_test__"
        payload = {
            "key": key,
            "text": "smoke-test-value",
            "user_id": "smoke",
        }
        # Write via POST /v1/memory/put
        w = api_client.post(
            "/v1/memory/put",
            headers={"X-API-Key": _TEST_API_KEY},
            json=payload,
        )
        if w.status_code == 503:
            pytest.skip("Memory store unavailable — likely no database")
        assert w.status_code in (200, 201, 204), (
            f"Memory write failed ({w.status_code}): {w.text}"
        )
        # Read back via POST /v1/memory/get
        r = api_client.post(
            "/v1/memory/get",
            headers={"X-API-Key": _TEST_API_KEY},
            json={"key": key, "user_id": "smoke"},
        )
        assert r.status_code == 200, (
            f"Memory read failed ({r.status_code}): {r.text}"
        )

    def test_trustlog_list(self, api_client):
        """Verify TrustLog listing endpoint responds.

        A successful list confirms the TrustLog read path is working
        against whichever backend is active.
        """
        r = api_client.get(
            "/v1/trust/logs",
            headers={"X-API-Key": _TEST_API_KEY},
        )
        assert r.status_code == 200, (
            f"TrustLog list failed ({r.status_code}): {r.text}"
        )

    def test_health_backend_matches_configured_env(self, api_client):
        """Confirm /health storage_backends matches the runtime env vars.

        Catches the scenario where compose sets postgresql but the app
        silently falls back to file backends.
        """
        r = api_client.get("/health")
        assert r.status_code == 200
        backends = r.json().get("storage_backends", {})
        expected_memory = os.getenv("VERITAS_MEMORY_BACKEND", "json").strip().lower()
        expected_trustlog = os.getenv("VERITAS_TRUSTLOG_BACKEND", "jsonl").strip().lower()
        assert backends.get("memory") == expected_memory, (
            f"Backend mismatch: /health reports memory={backends.get('memory')!r} "
            f"but VERITAS_MEMORY_BACKEND={expected_memory!r}"
        )
        assert backends.get("trustlog") == expected_trustlog, (
            f"Backend mismatch: /health reports trustlog={backends.get('trustlog')!r} "
            f"but VERITAS_TRUSTLOG_BACKEND={expected_trustlog!r}"
        )


@pytest.mark.smoke
class TestBackendMisconfigurationFailFast:
    """Verify fail-fast behaviour on backend misconfiguration."""

    def test_postgresql_without_database_url_raises(self, monkeypatch):
        """App startup must fail when postgresql is requested without URL."""
        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "postgresql")
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
        monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)
        from veritas_os.storage.factory import validate_backend_config

        with pytest.raises(RuntimeError, match="VERITAS_DATABASE_URL"):
            validate_backend_config()

    def test_unknown_backend_raises(self, monkeypatch):
        """Unknown backend name is rejected at startup."""
        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "redis")
        from veritas_os.storage.factory import validate_backend_config

        with pytest.raises(ValueError, match="Unknown VERITAS_MEMORY_BACKEND"):
            validate_backend_config()

    def test_unused_database_url_warns(self, monkeypatch, caplog):
        """Warn when DATABASE_URL is set but no backend uses postgresql.

        This catches the scenario where an operator sets up the database
        but forgets to flip the backend selector.
        """
        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "json")
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "jsonl")
        monkeypatch.setenv("VERITAS_DATABASE_URL", "postgresql://x:x@localhost/x")
        from veritas_os.storage.factory import validate_backend_config

        with caplog.at_level(logging.WARNING, logger="veritas_os.storage.factory"):
            validate_backend_config()
        assert "unused" in caplog.text.lower() or "VERITAS_DATABASE_URL" in caplog.text, (
            "Expected warning about unused VERITAS_DATABASE_URL"
        )

    def test_mixed_backends_warns(self, monkeypatch, caplog):
        """Warn when only one backend is postgresql (mixed setup).

        Mixed backends are supported but usually unintentional.
        """
        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "postgresql")
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "jsonl")
        monkeypatch.setenv("VERITAS_DATABASE_URL", "postgresql://x:x@localhost/x")
        from veritas_os.storage.factory import validate_backend_config

        with caplog.at_level(logging.WARNING, logger="veritas_os.storage.factory"):
            validate_backend_config()
        assert "mixed" in caplog.text.lower() or "Mixed" in caplog.text, (
            "Expected warning about mixed storage backends"
        )
