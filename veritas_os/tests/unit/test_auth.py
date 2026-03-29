# -*- coding: utf-8 -*-
"""認証・認可 単体テスト

認証コア / 認可ストア整合性テスト。"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ============================================================
# Source: test_auth_core.py
# ============================================================

# tests for veritas_os/api/auth.py — pure functions and in-memory store
"""Tests for auth utility functions and InMemoryAuthSecurityStore."""

import os
from unittest import mock

import pytest

from veritas_os.api.auth import (
    InMemoryAuthSecurityStore,
    _create_auth_security_store,
    _auth_store_failure_mode,
    _warn_auth_store_fail_open_once,
    auth_store_health_snapshot,
    _check_and_register_nonce,
    _cleanup_auth_fail_bucket_unsafe,
    _derive_api_user_id,
    _env_int_safe,
    _is_placeholder_secret,
    _record_auth_reject_reason,
    _resolve_client_ip,
    _resolve_memory_user_id,
    _snapshot_auth_reject_reason_metrics,
    _auth_fail_bucket,
    _auth_fail_lock,
    _allow_sse_query_api_key,
    _allow_ws_query_api_key,
    _get_api_secret,
    _check_multiworker_auth_store,
)


class TestAuthRejectMetrics:
    def test_record_and_snapshot(self):
        _record_auth_reject_reason("test_reason")
        snap = _snapshot_auth_reject_reason_metrics()
        assert snap.get("test_reason", 0) >= 1


class TestCleanupAuthFailBucket:
    def test_removes_expired(self):
        import time
        now = time.time()
        with _auth_fail_lock:
            _auth_fail_bucket["old_ip"] = (5, now - 500)
            _auth_fail_bucket["fresh_ip"] = (1, now)
            _cleanup_auth_fail_bucket_unsafe(now)
        assert "old_ip" not in _auth_fail_bucket
        assert "fresh_ip" in _auth_fail_bucket
        # Clean up
        with _auth_fail_lock:
            _auth_fail_bucket.pop("fresh_ip", None)


class TestInMemoryAuthSecurityStore:
    def test_register_nonce(self):
        store = InMemoryAuthSecurityStore()
        assert store.register_nonce("unique_nonce_test_123", 300.0) is True
        # Replay should fail
        assert store.register_nonce("unique_nonce_test_123", 300.0) is False

    def test_increment_auth_failure(self):
        store = InMemoryAuthSecurityStore()
        # First attempts should not exceed
        for _ in range(9):
            assert store.increment_auth_failure("192.168.1.1", 10, 60.0) is False
        # 11th should exceed
        store.increment_auth_failure("192.168.1.1", 10, 60.0)
        assert store.increment_auth_failure("192.168.1.1", 10, 60.0) is True

    def test_increment_rate_limit(self):
        store = InMemoryAuthSecurityStore()
        for _ in range(59):
            assert store.increment_rate_limit("key_test_rl", 60, 60.0) is False


class TestDeriveApiUserId:
    def test_with_key(self):
        user_id = _derive_api_user_id("test_key")
        assert user_id.startswith("key_")
        assert len(user_id) > 4

    def test_without_key(self):
        assert _derive_api_user_id(None) == "anon"
        assert _derive_api_user_id("") == "anon"

    def test_deterministic(self):
        assert _derive_api_user_id("abc") == _derive_api_user_id("abc")


class TestResolveMemoryUserId:
    def test_ignores_body_override(self):
        result = _resolve_memory_user_id("spoofed_user", "real_key")
        assert result.startswith("key_")

    def test_no_key(self):
        assert _resolve_memory_user_id("", None) == "anon"


class TestResolveClientIp:
    def test_xff_ignored_without_trusted_proxies(self):
        # VERITAS_TRUSTED_PROXIES 未設定時は X-Forwarded-For を無視してフォールバック
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VERITAS_TRUSTED_PROXIES", None)
            assert _resolve_client_ip(None, "10.0.0.1, 10.0.0.2") == "unknown"

    def test_xff_used_when_direct_ip_is_trusted(self):
        # 直接接続 IP が信頼プロキシリストにある場合は X-Forwarded-For を使用
        req = mock.MagicMock()
        req.client.host = "10.0.0.2"
        with mock.patch.dict(os.environ, {"VERITAS_TRUSTED_PROXIES": "10.0.0.2"}):
            assert _resolve_client_ip(req, "1.2.3.4, 10.0.0.2") == "1.2.3.4"

    def test_xff_ignored_when_direct_ip_not_trusted(self):
        # 直接接続 IP が信頼プロキシリストにない場合は X-Forwarded-For を無視
        req = mock.MagicMock()
        req.client.host = "10.0.0.5"
        with mock.patch.dict(os.environ, {"VERITAS_TRUSTED_PROXIES": "10.0.0.2"}):
            assert _resolve_client_ip(req, "1.2.3.4, 10.0.0.5") == "10.0.0.5"

    def test_from_request(self):
        req = mock.MagicMock()
        req.client.host = "127.0.0.1"
        assert _resolve_client_ip(req, None) == "127.0.0.1"

    def test_unknown_fallback(self):
        assert _resolve_client_ip(None, None) == "unknown"


class TestAuthStoreFailureMode:
    def setup_method(self):
        _warn_auth_store_fail_open_once.cache_clear()

    def test_default_closed(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VERITAS_AUTH_STORE_FAILURE_MODE", None)
            assert _auth_store_failure_mode() == "closed"

    def test_open(self):
        with mock.patch.dict(
            os.environ,
            {
                "VERITAS_ENV": "local",
                "VERITAS_AUTH_STORE_FAILURE_MODE": "open",
                "VERITAS_AUTH_ALLOW_FAIL_OPEN": "true",
            },
            clear=True,
        ):
            assert _auth_store_failure_mode() == "open"

    def test_open_emits_security_warning_once(self, caplog):
        caplog.set_level("WARNING")
        with mock.patch.dict(
            os.environ,
            {
                "VERITAS_ENV": "local",
                "VERITAS_AUTH_STORE_FAILURE_MODE": "open",
                "VERITAS_AUTH_ALLOW_FAIL_OPEN": "true",
            },
        ):
            assert _auth_store_failure_mode() == "open"
            assert _auth_store_failure_mode() == "open"

        assert (
            "[security-warning] VERITAS_AUTH_STORE_FAILURE_MODE=open is enabled."
            in caplog.text
        )
        warning_count = caplog.text.count(
            "[security-warning] VERITAS_AUTH_STORE_FAILURE_MODE=open is enabled."
        )
        assert warning_count == 1


    def test_open_without_allow_flag_forces_closed(self, caplog):
        caplog.set_level("WARNING")
        with mock.patch.dict(
            os.environ,
            {
                "VERITAS_AUTH_STORE_FAILURE_MODE": "open",
            },
            clear=True,
        ):
            assert _auth_store_failure_mode() == "closed"

        assert (
            "[security-warning] VERITAS_AUTH_STORE_FAILURE_MODE=open was ignored."
            in caplog.text
        )

    def test_open_outside_local_test_profiles_forces_closed(self, caplog):
        caplog.set_level("WARNING")
        with mock.patch.dict(
            os.environ,
            {
                "VERITAS_ENV": "staging",
                "VERITAS_AUTH_STORE_FAILURE_MODE": "open",
                "VERITAS_AUTH_ALLOW_FAIL_OPEN": "true",
            },
            clear=True,
        ):
            assert _auth_store_failure_mode() == "closed"

        assert "Fail-open is restricted to explicit local/test profiles." in caplog.text

    def test_open_with_unset_profile_forces_closed(self, caplog):
        caplog.set_level("WARNING")
        with mock.patch.dict(
            os.environ,
            {
                "VERITAS_AUTH_STORE_FAILURE_MODE": "open",
                "VERITAS_AUTH_ALLOW_FAIL_OPEN": "true",
            },
            clear=True,
        ):
            assert _auth_store_failure_mode() == "closed"

        assert "VERITAS_ENV=unset" in caplog.text
        assert "explicit local/test profiles" in caplog.text

    def test_invalid_falls_back(self):
        with mock.patch.dict(os.environ, {"VERITAS_AUTH_STORE_FAILURE_MODE": "bad"}):
            assert _auth_store_failure_mode() == "closed"

    def test_production_forces_closed(self):
        with mock.patch.dict(
            os.environ,
            {
                "VERITAS_ENV": "production",
                "VERITAS_AUTH_STORE_FAILURE_MODE": "open",
            },
        ):
            assert _auth_store_failure_mode() == "closed"

    def test_node_env_production_forces_closed(self):
        with mock.patch.dict(
            os.environ,
            {
                "NODE_ENV": "production",
                "VERITAS_AUTH_STORE_FAILURE_MODE": "open",
            },
            clear=True,
        ):
            assert _auth_store_failure_mode() == "closed"


class TestAuthStoreHealthSnapshot:
    def setup_method(self):
        _warn_auth_store_fail_open_once.cache_clear()

    def test_health_snapshot_marks_ignored_fail_open_request_degraded(self):
        """Ignored fail-open requests should stay visible in health telemetry."""
        with mock.patch.dict(
            os.environ,
            {
                "VERITAS_ENV": "staging",
                "VERITAS_AUTH_STORE_FAILURE_MODE": "open",
                "VERITAS_AUTH_ALLOW_FAIL_OPEN": "true",
            },
            clear=True,
        ):
            snapshot = auth_store_health_snapshot()

        assert snapshot["status"] == "degraded"
        assert snapshot["requested_failure_mode"] == "open"
        assert snapshot["failure_mode"] == "closed"
        assert "fail_open_request_ignored" in snapshot["reasons"]


class TestCreateAuthSecurityStore:
    def test_redis_mode_warns_and_falls_back_outside_production(self, caplog):
        """Non-production Redis auth-store failures may degrade with warning."""
        caplog.set_level("WARNING")

        with mock.patch.dict(
            os.environ,
            {
                "VERITAS_ENV": "local",
                "VERITAS_AUTH_SECURITY_STORE": "redis",
            },
            clear=True,
        ):
            store = _create_auth_security_store()

        assert isinstance(store, InMemoryAuthSecurityStore)
        assert "VERITAS_AUTH_REDIS_URL is missing" in caplog.text

    def test_redis_mode_rejects_missing_url_in_production(self):
        """Production must fail closed when Redis auth-store config is incomplete."""
        with mock.patch.dict(
            os.environ,
            {
                "VERITAS_ENV": "production",
                "VERITAS_AUTH_SECURITY_STORE": "redis",
            },
            clear=True,
        ):
            with pytest.raises(RuntimeError, match="VERITAS_AUTH_REDIS_URL is missing"):
                _create_auth_security_store()

    def test_redis_mode_rejects_runtime_init_failure_in_production(self):
        """Production must fail closed when Redis auth-store initialization fails."""
        with mock.patch.dict(
            os.environ,
            {
                "VERITAS_ENV": "production",
                "VERITAS_AUTH_SECURITY_STORE": "redis",
                "VERITAS_AUTH_REDIS_URL": "redis://example.test:6379/0",
            },
            clear=True,
        ):
            with mock.patch(
                "veritas_os.api.auth.importlib.import_module",
                side_effect=RuntimeError("redis unavailable"),
            ):
                with pytest.raises(RuntimeError, match="redis unavailable"):
                    _create_auth_security_store()


class TestEnvIntSafe:
    def test_default(self):
        assert _env_int_safe("NONEXISTENT_KEY_12345", 42) == 42

    def test_valid(self):
        with mock.patch.dict(os.environ, {"TEST_INT": "100"}):
            assert _env_int_safe("TEST_INT", 0) == 100

    def test_invalid(self):
        with mock.patch.dict(os.environ, {"TEST_INT": "bad"}):
            assert _env_int_safe("TEST_INT", 99) == 99


class TestIsPlaceholderSecret:
    def test_placeholder(self):
        assert _is_placeholder_secret("YOUR_VERITAS_API_SECRET_HERE") is True

    def test_not_placeholder(self):
        assert _is_placeholder_secret("real_secret_value") is False


class TestAllowSseQueryApiKey:
    def test_disabled_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VERITAS_ALLOW_SSE_QUERY_API_KEY", None)
            assert _allow_sse_query_api_key() is False

    def test_needs_dual_opt_in(self):
        with mock.patch.dict(os.environ, {"VERITAS_ALLOW_SSE_QUERY_API_KEY": "1"}):
            os.environ.pop("VERITAS_ACK_SSE_QUERY_API_KEY_RISK", None)
            assert _allow_sse_query_api_key() is False

    def test_enabled_with_both_flags(self):
        with mock.patch.dict(os.environ, {
            "VERITAS_ALLOW_SSE_QUERY_API_KEY": "1",
            "VERITAS_ACK_SSE_QUERY_API_KEY_RISK": "1",
        }):
            assert _allow_sse_query_api_key() is True


class TestAllowWsQueryApiKey:
    def test_disabled_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VERITAS_ALLOW_WS_QUERY_API_KEY", None)
            assert _allow_ws_query_api_key() is False

    def test_needs_dual_opt_in(self):
        with mock.patch.dict(os.environ, {"VERITAS_ALLOW_WS_QUERY_API_KEY": "1"}):
            os.environ.pop("VERITAS_ACK_WS_QUERY_API_KEY_RISK", None)
            assert _allow_ws_query_api_key() is False


class TestGetApiSecret:
    def test_placeholder_returns_empty(self):
        import veritas_os.api.auth as auth_mod
        orig = auth_mod.API_SECRET
        try:
            auth_mod.API_SECRET = b""
            with mock.patch.dict(os.environ, {"VERITAS_API_SECRET": "YOUR_VERITAS_API_SECRET_HERE"}):
                assert _get_api_secret() == b""
        finally:
            auth_mod.API_SECRET = orig


class TestCheckMultiworkerAuthStore:
    def test_single_worker_no_warning(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WEB_CONCURRENCY", None)
            os.environ.pop("UVICORN_WORKERS", None)
            _check_multiworker_auth_store()  # should not raise


class TestCheckAndRegisterNonce:
    def test_too_long_nonce(self):
        assert _check_and_register_nonce("x" * 1000) is False
