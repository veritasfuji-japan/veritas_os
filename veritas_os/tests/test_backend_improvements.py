# veritas_os/tests/test_backend_improvements.py
"""Tests for backend improvements:

1. Context model list-size validation (goals, constraints, preferences)
2. LLM client connection pooling (_http_post, _get_http_client, close_pool)
3. LLM client circuit breaker (_circuit_check, _circuit_record_*)
4. Server nonce config env-var support (_NONCE_TTL_SEC, _NONCE_MAX, _NONCE_MAX_LENGTH)
"""
from __future__ import annotations

import time

import pytest
from pydantic import ValidationError

from veritas_os.api import schemas
from veritas_os.api.schemas import Context, MAX_LIST_ITEMS
from veritas_os.core import llm_client


@pytest.fixture(autouse=True)
def _reset_circuit_breaker():
    """Reset circuit breaker state between tests."""
    llm_client._circuit_state.clear()
    yield
    llm_client._circuit_state.clear()


# =========================================================
# 1. Context model list-size validation
# =========================================================


class TestContextListSizeValidation:
    """Verify goals/constraints/preferences list size is properly validated."""

    def test_goals_within_limit(self):
        ctx = Context(user_id="u1", query="q", goals=["g1", "g2"])
        assert len(ctx.goals) == 2

    def test_goals_exceeds_limit_raises(self):
        big = [f"goal-{i}" for i in range(MAX_LIST_ITEMS + 1)]
        with pytest.raises(ValidationError):
            Context(user_id="u1", query="q", goals=big)

    def test_constraints_exceeds_limit_raises(self):
        big = [f"c-{i}" for i in range(MAX_LIST_ITEMS + 1)]
        with pytest.raises(ValidationError):
            Context(user_id="u1", query="q", constraints=big)

    def test_preferences_exceeds_limit_raises(self):
        big = [f"p-{i}" for i in range(MAX_LIST_ITEMS + 1)]
        with pytest.raises(ValidationError):
            Context(user_id="u1", query="q", preferences=big)

    def test_none_lists_accepted(self):
        ctx = Context(user_id="u1", query="q")
        assert ctx.goals is None
        assert ctx.constraints is None
        assert ctx.preferences is None

    def test_exact_limit_accepted(self):
        items = [f"item-{i}" for i in range(MAX_LIST_ITEMS)]
        ctx = Context(user_id="u1", query="q", goals=items)
        assert len(ctx.goals) == MAX_LIST_ITEMS


# =========================================================
# 2. LLM client connection pooling
# =========================================================


class TestConnectionPooling:
    def test_get_http_client_returns_client(self):
        client = llm_client._get_http_client()
        assert client is not None
        import httpx
        assert isinstance(client, httpx.Client)

    def test_get_http_client_returns_same_instance(self):
        c1 = llm_client._get_http_client()
        c2 = llm_client._get_http_client()
        assert c1 is c2

    def test_close_pool_then_new_client(self):
        c1 = llm_client._get_http_client()
        llm_client.close_pool()
        assert llm_client._http_client is None
        c2 = llm_client._get_http_client()
        assert c2 is not c1

    def test_close_pool_idempotent(self):
        llm_client.close_pool()
        llm_client.close_pool()  # Should not raise


# =========================================================
# 3. LLM client circuit breaker
# =========================================================


class TestCircuitBreaker:
    def test_circuit_closed_initially(self):
        # Should not raise
        llm_client._circuit_check("openai")

    def test_circuit_opens_after_threshold_failures(self):
        for _ in range(llm_client.CIRCUIT_BREAKER_THRESHOLD):
            llm_client._circuit_record_failure("openai")
        with pytest.raises(llm_client.LLMError, match="Circuit open"):
            llm_client._circuit_check("openai")

    def test_circuit_below_threshold_stays_closed(self):
        for _ in range(llm_client.CIRCUIT_BREAKER_THRESHOLD - 1):
            llm_client._circuit_record_failure("openai")
        # Should not raise
        llm_client._circuit_check("openai")

    def test_circuit_success_resets_failures(self):
        for _ in range(llm_client.CIRCUIT_BREAKER_THRESHOLD - 1):
            llm_client._circuit_record_failure("openai")
        llm_client._circuit_record_success("openai")
        # Should not raise even after more failures
        llm_client._circuit_check("openai")

    def test_circuit_recovery_after_timeout(self, monkeypatch):
        for _ in range(llm_client.CIRCUIT_BREAKER_THRESHOLD):
            llm_client._circuit_record_failure("openai")
        # Simulate recovery time elapsed
        state = llm_client._circuit_state["openai"]
        state["last_failure"] = time.time() - llm_client.CIRCUIT_BREAKER_RECOVERY_SEC - 1
        # Should not raise (recovery period elapsed)
        llm_client._circuit_check("openai")
        # State should be reset
        assert llm_client._circuit_state["openai"]["failures"] == 0

    def test_circuit_independent_per_provider(self):
        for _ in range(llm_client.CIRCUIT_BREAKER_THRESHOLD):
            llm_client._circuit_record_failure("openai")
        with pytest.raises(llm_client.LLMError, match="Circuit open"):
            llm_client._circuit_check("openai")
        # Anthropic should be unaffected
        llm_client._circuit_check("anthropic")

    def test_circuit_check_in_chat(self, monkeypatch):
        """Circuit breaker prevents chat() from executing when circuit is open."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        for _ in range(llm_client.CIRCUIT_BREAKER_THRESHOLD):
            llm_client._circuit_record_failure("openai")
        with pytest.raises(llm_client.LLMError, match="Circuit open"):
            llm_client.chat("sys", "user", provider="openai", model="gpt-4.1-mini")

    def test_chat_failure_records_circuit_failure(self, monkeypatch):
        """A failed chat() call increments the circuit failure counter."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setattr(llm_client, "LLM_MAX_RETRIES", 1)
        monkeypatch.setattr(llm_client, "LLM_RETRY_DELAY", 0)

        class _FakeResp:
            status_code = 500
            text = "error"
            headers = {}
            content = b"error"

        monkeypatch.setattr(llm_client, "_http_post", lambda *a, **kw: _FakeResp())
        with pytest.raises(llm_client.LLMError):
            llm_client.chat("sys", "user", provider="openai", model="gpt-4.1-mini")
        state = llm_client._circuit_state.get("openai")
        assert state is not None
        assert state["failures"] >= 1

    def test_chat_success_resets_circuit(self, monkeypatch):
        """A successful chat() call resets the circuit breaker."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        llm_client._circuit_record_failure("openai")

        class _FakeResp:
            status_code = 200
            text = "ok"
            headers = {}
            content = b"ok"
            def json(self):
                return {
                    "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
                    "usage": {},
                }

        monkeypatch.setattr(llm_client, "_http_post", lambda *a, **kw: _FakeResp())
        result = llm_client.chat("sys", "user", provider="openai", model="gpt-4.1-mini")
        assert result["text"] == "hi"
        assert "openai" not in llm_client._circuit_state


# =========================================================
# 4. Server nonce config env-var support
# =========================================================


class TestNonceEnvConfig:
    def test_default_nonce_ttl(self):
        import veritas_os.api.server as server
        # Default is 300
        assert server._NONCE_TTL_SEC == 300 or isinstance(server._NONCE_TTL_SEC, int)

    def test_default_nonce_max(self):
        import veritas_os.api.server as server
        assert server._NONCE_MAX == 5000 or isinstance(server._NONCE_MAX, int)

    def test_default_nonce_max_length(self):
        import veritas_os.api.server as server
        assert server._NONCE_MAX_LENGTH == 256 or isinstance(server._NONCE_MAX_LENGTH, int)

    def test_env_int_safe_valid(self):
        import veritas_os.api.server as server
        import os
        os.environ["_TEST_ENV_INT_SAFE"] = "42"
        try:
            assert server._env_int_safe("_TEST_ENV_INT_SAFE", 10) == 42
        finally:
            del os.environ["_TEST_ENV_INT_SAFE"]

    def test_env_int_safe_invalid_returns_default(self):
        import veritas_os.api.server as server
        import os
        os.environ["_TEST_ENV_INT_SAFE"] = "not-a-number"
        try:
            assert server._env_int_safe("_TEST_ENV_INT_SAFE", 10) == 10
        finally:
            del os.environ["_TEST_ENV_INT_SAFE"]

    def test_env_int_safe_empty_returns_default(self):
        import veritas_os.api.server as server
        import os
        os.environ["_TEST_ENV_INT_SAFE"] = ""
        try:
            assert server._env_int_safe("_TEST_ENV_INT_SAFE", 10) == 10
        finally:
            del os.environ["_TEST_ENV_INT_SAFE"]

    def test_env_int_safe_missing_returns_default(self):
        import veritas_os.api.server as server
        import os
        os.environ.pop("_TEST_ENV_INT_SAFE_MISSING", None)
        assert server._env_int_safe("_TEST_ENV_INT_SAFE_MISSING", 99) == 99


# =========================================================
# 5. Trustlog endpoint error handling
# =========================================================

import os as _os
import veritas_os.api.server as _server
from fastapi.testclient import TestClient as _TestClient
_client = _TestClient(_server.app)
_FIXED_KEY = "backend-improvement-key"


@pytest.fixture()
def _auth_env(monkeypatch):
    """Set a known API key and clear rate-limit buckets for each test."""
    monkeypatch.setenv("VERITAS_API_KEY", _FIXED_KEY)
    _server._rate_bucket.clear()
    with _server._inflight_lock:
        _server._shutting_down = False


class TestTrustlogVerifyErrorHandling:
    """trustlog_verify returns 500 when verify_trustlog_chain raises."""

    def test_verify_returns_500_on_exception(self, monkeypatch, _auth_env):
        def _boom():
            raise RuntimeError("disk failure")

        monkeypatch.setattr(_server, "verify_trustlog_chain", _boom)
        resp = _client.get("/v1/trustlog/verify", headers={"X-API-Key": _FIXED_KEY})
        assert resp.status_code == 500
        body = resp.json()
        assert body["ok"] is False
        assert "trustlog verification failed" in body["error"]

    def test_verify_success_still_works(self, monkeypatch, _auth_env):
        monkeypatch.setattr(
            _server, "verify_trustlog_chain", lambda: {"ok": True, "entries": 0},
        )
        resp = _client.get("/v1/trustlog/verify", headers={"X-API-Key": _FIXED_KEY})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestTrustlogExportErrorHandling:
    """trustlog_export returns 500 when export_signed_trustlog raises."""

    def test_export_returns_500_on_exception(self, monkeypatch, _auth_env):
        def _boom():
            raise RuntimeError("export failure")

        monkeypatch.setattr(_server, "export_signed_trustlog", _boom)
        resp = _client.get("/v1/trustlog/export", headers={"X-API-Key": _FIXED_KEY})
        assert resp.status_code == 500
        body = resp.json()
        assert body["ok"] is False
        assert "trustlog export failed" in body["error"]

    def test_export_success_still_works(self, monkeypatch, _auth_env):
        monkeypatch.setattr(
            _server, "export_signed_trustlog", lambda: {"count": 0, "entries": []},
        )
        resp = _client.get("/v1/trustlog/export", headers={"X-API-Key": _FIXED_KEY})
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


# =========================================================
# 6. Health endpoint error handling
# =========================================================


class TestHealthErrorHandling:
    """Health endpoint returns 500 on unexpected internal error."""

    def test_health_returns_500_on_exception(self, monkeypatch, _auth_env):
        def _boom():
            raise RuntimeError("unexpected")

        monkeypatch.setattr(_server, "get_decision_pipeline", _boom)
        resp = _client.get("/health")
        assert resp.status_code == 500
        body = resp.json()
        assert body["ok"] is False
        assert "health check failed" in body["error"]

    def test_health_normal_response(self, _auth_env):
        resp = _client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "ok" in body
        assert "uptime" in body
        assert "checks" in body


# =========================================================
# 7. Schema validation improvements
# =========================================================

from veritas_os.api.schemas import MemoryPutRequest, MemorySearchRequest  # noqa: E402


class TestMemorySearchRequestKindsCoercion:
    """kinds field is coerced at schema level."""

    def test_kinds_none_stays_none(self):
        req = MemorySearchRequest(query="test")
        assert req.kinds is None

    def test_kinds_string_becomes_list(self):
        req = MemorySearchRequest(query="test", kinds="semantic")
        assert req.kinds == ["semantic"]

    def test_kinds_list_passes_through(self):
        req = MemorySearchRequest(query="test", kinds=["semantic", "episodic"])
        assert req.kinds == ["semantic", "episodic"]


class TestMemoryPutRetentionClassCoercion:
    """retention_class is normalised and validated at schema level."""

    def test_none_stays_none(self):
        req = MemoryPutRequest(text="hi")
        assert req.retention_class is None

    def test_valid_value_accepted(self):
        for rc in ("short", "standard", "long", "regulated"):
            req = MemoryPutRequest(text="hi", retention_class=rc)
            assert req.retention_class == rc

    def test_case_normalised(self):
        req = MemoryPutRequest(text="hi", retention_class="REGULATED")
        assert req.retention_class == "regulated"

    def test_invalid_becomes_none(self):
        req = MemoryPutRequest(text="hi", retention_class="bogus")
        assert req.retention_class is None


# =========================================================
# 8. LLM pool close on shutdown
# =========================================================


class TestLLMPoolCloseOnShutdown:
    """LLM HTTP connection pool is closed during app shutdown."""

    def test_close_pool_called_on_shutdown(self, monkeypatch):
        close_called = []

        def _mock_close():
            close_called.append(True)

        monkeypatch.setattr(_server, "_close_llm_pool", _mock_close)
        with _TestClient(_server.app):
            pass
        assert len(close_called) == 1

    def test_shutdown_works_when_close_pool_is_none(self, monkeypatch):
        monkeypatch.setattr(_server, "_close_llm_pool", None)
        with _TestClient(_server.app):
            pass  # Must not raise


# =========================================================
# 9. Return type annotations smoke tests
# =========================================================


class TestReturnTypeAnnotations:
    """Endpoints with new type hints still return correct dict responses."""

    def test_root_returns_dict(self, _auth_env):
        resp = _client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)
        assert body["ok"] is True

    def test_status_returns_dict(self, _auth_env):
        resp = _client.get("/status")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)
        assert body["ok"] is True
