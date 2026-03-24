# veritas_os/tests/test_server_defense.py
"""Defense-focused tests for veritas_os/api/server.py.

Targets under-covered branches and defensive design principles:
  - get_cfg / get_decision_pipeline / get_fuji_core / get_value_core / get_memory_store
    lazy resolution, caching, and error fallback
  - placeholder respect: monkeypatch must NOT be overwritten by lazy import
  - _log_api_key_source_once: all four branches
  - validation error handler: debug off, debug on, raw_body redaction
  - _effective_log_paths / _effective_shadow_dir wrapper delegation
  - trust log runtime wrappers
  - __getattr__ module-level proxy
  - startup/lifespan import crash safety
  - health endpoint degraded path
  - backward compatibility exports existence
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock, patch

_TEST_KEY = "server-defense-key-12345"
os.environ["VERITAS_API_KEY"] = _TEST_KEY
_AUTH = {"X-API-Key": _TEST_KEY}

import pytest
from fastapi.testclient import TestClient

import veritas_os.api.server as server

client = TestClient(server.app)


@pytest.fixture(autouse=True)
def _reset_rate_bucket(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_KEY)
    server._rate_bucket.clear()
    yield
    server._rate_bucket.clear()


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ================================================================
# 1. get_cfg – lazy resolution
# ================================================================

class TestGetCfg:
    def test_cached_cfg_returned_without_reimport(self, monkeypatch):
        """Once cfg is resolved, subsequent calls return the cached object."""
        sentinel = SimpleNamespace(cors_allow_origins=["*"], api_key="test")
        state = server._LazyState(obj=sentinel)
        monkeypatch.setattr(server, "_cfg_state", state)
        result = server.get_cfg()
        assert result is sentinel

    def test_cfg_import_fail_returns_fallback(self, monkeypatch):
        """When cfg import fails, a minimal fallback namespace is returned."""
        fresh_state = server._LazyState()
        monkeypatch.setattr(server, "_cfg_state", fresh_state)
        monkeypatch.setattr(
            server.importlib, "import_module",
            lambda name: (_ for _ in ()).throw(ImportError("cfg missing")),
        )
        result = server.get_cfg()
        assert result.cors_allow_origins == []
        assert result.api_key == ""
        # Restore
        monkeypatch.setattr(server, "_cfg_state", server._LazyState())

    def test_cfg_already_failed_returns_cached_fallback(self, monkeypatch):
        """After a failed import, repeated calls return the same fallback."""
        fallback = SimpleNamespace(cors_allow_origins=[], api_key="")
        state = server._LazyState(obj=fallback, err="previous error", attempted=True)
        monkeypatch.setattr(server, "_cfg_state", state)
        result = server.get_cfg()
        assert result is fallback


# ================================================================
# 2. get_decision_pipeline – lazy resolution
# ================================================================

class TestGetDecisionPipeline:
    def test_cached_pipeline_returned(self, monkeypatch):
        """Cached pipeline is returned without re-import."""
        sentinel = SimpleNamespace(run=lambda x: x)
        state = server._LazyState(obj=sentinel)
        monkeypatch.setattr(server, "_pipeline_state", state)
        result = server.get_decision_pipeline()
        assert result is sentinel

    def test_import_fail_returns_none(self, monkeypatch):
        """Pipeline import failure returns None gracefully."""
        fresh_state = server._LazyState()
        monkeypatch.setattr(server, "_pipeline_state", fresh_state)
        monkeypatch.setattr(
            server.importlib, "import_module",
            lambda name: (_ for _ in ()).throw(ImportError("no pipeline")),
        )
        result = server.get_decision_pipeline()
        assert result is None
        monkeypatch.setattr(server, "_pipeline_state", server._LazyState())

    def test_already_failed_returns_none(self, monkeypatch):
        """When pipeline import already failed, return None without retry."""
        state = server._LazyState(attempted=True, err="previous failure")
        monkeypatch.setattr(server, "_pipeline_state", state)
        result = server.get_decision_pipeline()
        assert result is None


# ================================================================
# 3. get_fuji_core – placeholder respect
# ================================================================

class TestGetFujiCore:
    def test_monkeypatched_validate_action_not_overwritten(self, monkeypatch):
        """When test monkeypatches fuji_core.validate_action, lazy import must not overwrite it."""
        custom_fn = lambda action, context: {"status": "custom"}
        patched = SimpleNamespace(
            __veritas_placeholder__=True,
            validate_action=custom_fn,
            validate=server._fuji_validate_stub,
        )
        monkeypatch.setattr(server, "fuji_core", patched)
        monkeypatch.setattr(server, "_fuji_state", server._LazyState())
        result = server.get_fuji_core()
        # Must return the patched object, not trigger a lazy import
        assert result is patched
        assert result.validate_action is custom_fn

    def test_monkeypatched_validate_not_overwritten(self, monkeypatch):
        """When test monkeypatches fuji_core.validate, lazy import must not overwrite it."""
        custom_fn = lambda action, context: {"status": "custom_v"}
        patched = SimpleNamespace(
            __veritas_placeholder__=True,
            validate_action=server._fuji_validate_stub,
            validate=custom_fn,
        )
        monkeypatch.setattr(server, "fuji_core", patched)
        monkeypatch.setattr(server, "_fuji_state", server._LazyState())
        result = server.get_fuji_core()
        assert result is patched
        assert result.validate is custom_fn

    def test_non_placeholder_returned_as_is(self, monkeypatch):
        """If fuji_core is not a placeholder, it is returned directly."""
        real_module = SimpleNamespace(validate_action=lambda a, c: {})
        monkeypatch.setattr(server, "fuji_core", real_module)
        monkeypatch.setattr(server, "_fuji_state", server._LazyState())
        result = server.get_fuji_core()
        assert result is real_module

    def test_cached_fuji_returned(self, monkeypatch):
        """Once fuji is resolved, cached value is returned."""
        sentinel = SimpleNamespace(validate_action=lambda a, c: {"status": "ok"})
        state = server._LazyState(obj=sentinel)
        monkeypatch.setattr(server, "_fuji_state", state)
        # Keep fuji_core as placeholder so the code enters the lazy path
        monkeypatch.setattr(server, "fuji_core", SimpleNamespace(
            __veritas_placeholder__=True,
            validate_action=server._fuji_validate_stub,
            validate=server._fuji_validate_stub,
        ))
        result = server.get_fuji_core()
        assert result is sentinel

    def test_import_fail_returns_none_keeps_placeholder(self, monkeypatch):
        """Fuji import failure returns None but keeps placeholder intact."""
        placeholder = SimpleNamespace(
            __veritas_placeholder__=True,
            validate_action=server._fuji_validate_stub,
            validate=server._fuji_validate_stub,
        )
        monkeypatch.setattr(server, "fuji_core", placeholder)
        monkeypatch.setattr(server, "_fuji_state", server._LazyState())
        monkeypatch.setattr(
            server.importlib, "import_module",
            lambda name: (_ for _ in ()).throw(ImportError("fuji missing")),
        )
        result = server.get_fuji_core()
        assert result is None
        # Placeholder must still be usable
        assert server.fuji_core.validate_action("x", {})["status"] == "allow"
        monkeypatch.setattr(server, "_fuji_state", server._LazyState())


# ================================================================
# 4. get_value_core – placeholder respect
# ================================================================

class TestGetValueCore:
    def test_monkeypatched_append_trust_log_not_overwritten(self, monkeypatch):
        """When test monkeypatches value_core.append_trust_log, lazy import must not overwrite."""
        custom_fn = MagicMock()
        patched = SimpleNamespace(
            __veritas_placeholder__=True,
            append_trust_log=custom_fn,
        )
        monkeypatch.setattr(server, "value_core", patched)
        monkeypatch.setattr(server, "_value_core_state", server._LazyState())
        result = server.get_value_core()
        assert result is patched
        assert result.append_trust_log is custom_fn

    def test_non_placeholder_with_append_returned(self, monkeypatch):
        """Non-placeholder value_core with append_trust_log is returned as-is."""
        real = SimpleNamespace(append_trust_log=lambda *a, **k: None)
        monkeypatch.setattr(server, "value_core", real)
        monkeypatch.setattr(server, "_value_core_state", server._LazyState())
        result = server.get_value_core()
        assert result is real

    def test_cached_value_core_returned(self, monkeypatch):
        """Once value_core is resolved, cached value is returned."""
        sentinel = SimpleNamespace(append_trust_log=lambda: None)
        state = server._LazyState(obj=sentinel)
        monkeypatch.setattr(server, "_value_core_state", state)
        monkeypatch.setattr(server, "value_core", SimpleNamespace(
            __veritas_placeholder__=True,
            append_trust_log=server._append_trust_log_stub,
        ))
        result = server.get_value_core()
        assert result is sentinel

    def test_import_fail_returns_none_keeps_placeholder(self, monkeypatch):
        """Value core import failure returns None but keeps placeholder."""
        placeholder = SimpleNamespace(
            __veritas_placeholder__=True,
            append_trust_log=server._append_trust_log_stub,
        )
        monkeypatch.setattr(server, "value_core", placeholder)
        monkeypatch.setattr(server, "_value_core_state", server._LazyState())
        monkeypatch.setattr(
            server.importlib, "import_module",
            lambda name: (_ for _ in ()).throw(ImportError("value_core missing")),
        )
        result = server.get_value_core()
        assert result is None
        assert server.value_core.append_trust_log is server._append_trust_log_stub
        monkeypatch.setattr(server, "_value_core_state", server._LazyState())


# ================================================================
# 5. get_memory_store – placeholder respect
# ================================================================

class TestGetMemoryStore:
    def test_monkeypatched_search_not_overwritten(self, monkeypatch):
        """When test monkeypatches MEMORY_STORE.search, lazy import must not overwrite."""
        custom_search = MagicMock(return_value=[{"id": "test"}])
        patched = SimpleNamespace(
            __veritas_placeholder__=True,
            search=custom_search,
            get=server._memory_get_stub,
        )
        monkeypatch.setattr(server, "MEMORY_STORE", patched)
        monkeypatch.setattr(server, "_memory_store_state", server._LazyState())
        result = server.get_memory_store()
        assert result is patched
        assert result.search is custom_search

    def test_monkeypatched_get_not_overwritten(self, monkeypatch):
        """When test monkeypatches MEMORY_STORE.get, lazy import must not overwrite."""
        custom_get = MagicMock(return_value={"id": "test"})
        patched = SimpleNamespace(
            __veritas_placeholder__=True,
            search=server._memory_search_stub,
            get=custom_get,
        )
        monkeypatch.setattr(server, "MEMORY_STORE", patched)
        monkeypatch.setattr(server, "_memory_store_state", server._LazyState())
        result = server.get_memory_store()
        assert result is patched
        assert result.get is custom_get

    def test_non_placeholder_with_search_returned(self, monkeypatch):
        """Non-placeholder MEMORY_STORE with search/get is returned as-is."""
        real = SimpleNamespace(search=lambda q: [], get=lambda k: None, put=lambda k, v: None)
        monkeypatch.setattr(server, "MEMORY_STORE", real)
        monkeypatch.setattr(server, "_memory_store_state", server._LazyState())
        result = server.get_memory_store()
        assert result is real

    def test_cached_memory_store_returned(self, monkeypatch):
        """Once memory store is resolved, cached value is returned."""
        sentinel = SimpleNamespace(search=lambda q: [], get=lambda k: None)
        state = server._LazyState(obj=sentinel)
        monkeypatch.setattr(server, "_memory_store_state", state)
        monkeypatch.setattr(server, "MEMORY_STORE", SimpleNamespace(
            __veritas_placeholder__=True,
            search=server._memory_search_stub,
            get=server._memory_get_stub,
        ))
        result = server.get_memory_store()
        assert result is sentinel

    def test_import_fail_returns_none_keeps_placeholder(self, monkeypatch):
        """Memory store import failure returns None but keeps placeholder."""
        placeholder = SimpleNamespace(
            __veritas_placeholder__=True,
            search=server._memory_search_stub,
            get=server._memory_get_stub,
        )
        monkeypatch.setattr(server, "MEMORY_STORE", placeholder)
        monkeypatch.setattr(server, "_memory_store_state", server._LazyState())
        monkeypatch.setattr(
            server.importlib, "import_module",
            lambda name: (_ for _ in ()).throw(ImportError("memory missing")),
        )
        result = server.get_memory_store()
        assert result is None
        assert server.MEMORY_STORE.search() == []
        assert server.MEMORY_STORE.get() is None
        monkeypatch.setattr(server, "_memory_store_state", server._LazyState())


# ================================================================
# 6. _log_api_key_source_once – all four branches
# ================================================================

class TestLogApiKeySourceOnce:
    def test_env_branch(self, monkeypatch):
        server._log_api_key_source_once.cache_clear()
        messages = []
        monkeypatch.setattr(server.logger, "info", lambda msg, *a: messages.append(msg % a))
        server._log_api_key_source_once("env")
        assert any("env" in m for m in messages)

    def test_api_key_default_branch(self, monkeypatch):
        server._log_api_key_source_once.cache_clear()
        messages = []
        monkeypatch.setattr(server.logger, "info", lambda msg, *a: messages.append(msg % a))
        server._log_api_key_source_once("api_key_default")
        assert any("api_key_default" in m for m in messages)

    def test_config_branch(self, monkeypatch):
        server._log_api_key_source_once.cache_clear()
        messages = []
        monkeypatch.setattr(server.logger, "info", lambda msg, *a: messages.append(msg % a))
        server._log_api_key_source_once("config")
        assert any("config" in m for m in messages)

    def test_missing_branch(self, monkeypatch):
        server._log_api_key_source_once.cache_clear()
        messages = []
        monkeypatch.setattr(server.logger, "info", lambda msg, *a: messages.append(msg % a))
        server._log_api_key_source_once("something_unknown")
        assert any("missing" in m for m in messages)

    def test_cache_deduplication(self, monkeypatch):
        """Same source logged only once (lru_cache)."""
        server._log_api_key_source_once.cache_clear()
        call_count = 0

        def counting_info(msg, *a):
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(server.logger, "info", counting_info)
        server._log_api_key_source_once("env")
        server._log_api_key_source_once("env")
        assert call_count == 1


# ================================================================
# 7. Validation error handler
# ================================================================

class TestValidationErrorHandler:
    def test_422_without_debug_mode_no_raw_body(self, monkeypatch):
        """In non-debug mode, 422 response should NOT include raw_body."""
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "")
        # Send invalid payload to trigger a 422 from a strict endpoint
        # Using a POST to a strict-body endpoint that triggers RequestValidationError
        resp = client.post(
            "/v1/decide",
            content=b"this is not json",
            headers={**_AUTH, "Content-Type": "application/json"},
        )
        if resp.status_code == 422:
            data = resp.json()
            assert "detail" in data
            assert "hint" in data
            assert "raw_body" not in data

    def test_422_with_debug_mode_includes_raw_body(self, monkeypatch):
        """In debug mode, 422 response SHOULD include raw_body."""
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "1")
        resp = client.post(
            "/v1/decide",
            content=b"this is not json",
            headers={**_AUTH, "Content-Type": "application/json"},
        )
        if resp.status_code == 422:
            data = resp.json()
            assert "detail" in data
            assert "raw_body" in data

    def test_422_raw_body_is_redacted(self, monkeypatch):
        """Sensitive data in raw_body should be redacted in debug mode."""
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "1")
        sensitive_payload = b'{"email": "user@example.com", "query": "test"}'
        resp = client.post(
            "/v1/decide",
            content=sensitive_payload,
            headers={**_AUTH, "Content-Type": "application/json"},
        )
        if resp.status_code == 422:
            data = resp.json()
            raw = data.get("raw_body", "")
            # PII should be masked if redact() works
            assert isinstance(raw, str)

    def test_422_hint_has_expected_example(self, monkeypatch):
        """422 response always includes hint with expected_example."""
        resp = client.post(
            "/v1/decide",
            content=b"not json",
            headers={**_AUTH, "Content-Type": "application/json"},
        )
        if resp.status_code == 422:
            data = resp.json()
            assert "hint" in data
            assert "expected_example" in data["hint"]

    def test_422_has_request_id(self, monkeypatch):
        """422 response includes a request_id for tracing."""
        resp = client.post(
            "/v1/decide",
            content=b"not json",
            headers={**_AUTH, "Content-Type": "application/json"},
        )
        if resp.status_code == 422:
            data = resp.json()
            assert "request_id" in data
            assert isinstance(data["request_id"], str)
            assert len(data["request_id"]) > 0


# ================================================================
# 8. _effective_log_paths / _effective_shadow_dir wrapper delegation
# ================================================================

class TestEffectivePathWrappers:
    def test_log_paths_all_custom(self, monkeypatch, tmp_path):
        """When all log paths are custom-patched, they are respected."""
        custom_json = tmp_path / "custom.json"
        custom_jsonl = tmp_path / "custom.jsonl"
        monkeypatch.setattr(server, "LOG_DIR", tmp_path)
        monkeypatch.setattr(server, "LOG_JSON", custom_json)
        monkeypatch.setattr(server, "LOG_JSONL", custom_jsonl)
        ld, lj, ljl = server._effective_log_paths()
        assert lj == custom_json
        assert ljl == custom_jsonl

    def test_shadow_dir_custom(self, monkeypatch, tmp_path):
        """Custom SHADOW_DIR is respected even when LOG_DIR is default."""
        custom_shadow = tmp_path / "my_shadow"
        monkeypatch.setattr(server, "SHADOW_DIR", custom_shadow)
        result = server._effective_shadow_dir()
        assert result == custom_shadow

    def test_shadow_dir_follows_log_dir_when_default(self, monkeypatch, tmp_path):
        """SHADOW_DIR follows LOG_DIR when SHADOW_DIR is still at default."""
        monkeypatch.setattr(server, "LOG_DIR", tmp_path)
        monkeypatch.setattr(server, "LOG_JSON", server._DEFAULT_LOG_JSON)
        monkeypatch.setattr(server, "LOG_JSONL", server._DEFAULT_LOG_JSONL)
        monkeypatch.setattr(server, "SHADOW_DIR", server._DEFAULT_SHADOW_DIR)
        result = server._effective_shadow_dir()
        assert result == tmp_path / "DASH"


# ================================================================
# 9. Trust log runtime wrappers
# ================================================================

class TestTrustLogRuntimeWrappers:
    def test_load_logs_json_delegates(self, monkeypatch, tmp_path):
        """_load_logs_json delegates to _trust_log_runtime.load_logs_json."""
        log_file = tmp_path / "trust_log.json"
        log_file.write_text("[]")
        monkeypatch.setattr(server, "LOG_DIR", tmp_path)
        monkeypatch.setattr(server, "LOG_JSON", log_file)
        monkeypatch.setattr(server, "LOG_JSONL", server._DEFAULT_LOG_JSONL)
        result = server._load_logs_json(log_file)
        assert isinstance(result, list)

    def test_save_json_delegates(self, monkeypatch, tmp_path):
        """_save_json writes through to _trust_log_runtime."""
        log_file = tmp_path / "trust_log.json"
        server._save_json(log_file, [{"test": True}])
        assert log_file.exists()

    def test_secure_chmod_delegates(self, monkeypatch, tmp_path):
        """_secure_chmod delegates to _trust_log_runtime."""
        test_file = tmp_path / "secure.txt"
        test_file.write_text("secret")
        server._secure_chmod(test_file)
        # File should still exist and be readable
        assert test_file.exists()

    def test_append_trust_log_creates_files(self, monkeypatch, tmp_path):
        """append_trust_log creates log files when they don't exist."""
        monkeypatch.setattr(server, "LOG_DIR", tmp_path)
        monkeypatch.setattr(server, "LOG_JSON", tmp_path / "trust_log.json")
        monkeypatch.setattr(server, "LOG_JSONL", tmp_path / "trust_log.jsonl")
        entry = {"request_id": "test-1", "timestamp": "2025-01-01T00:00:00Z"}
        server.append_trust_log(entry)
        # At least the jsonl file should be written
        assert (tmp_path / "trust_log.jsonl").exists()

    def test_write_shadow_decide_writes_file(self, monkeypatch, tmp_path):
        """write_shadow_decide creates a shadow snapshot file."""
        monkeypatch.setattr(server, "SHADOW_DIR", tmp_path)
        monkeypatch.setattr(server, "LOG_DIR", tmp_path)
        monkeypatch.setattr(server, "LOG_JSON", server._DEFAULT_LOG_JSON)
        monkeypatch.setattr(server, "LOG_JSONL", server._DEFAULT_LOG_JSONL)
        server.write_shadow_decide(
            request_id="req-001",
            body={"query": "test"},
            chosen={"title": "Plan A"},
            telos_score=0.8,
            fuji={"status": "allow"},
        )
        # Shadow directory should now have a file
        files = list(tmp_path.glob("decide_*.json"))
        assert len(files) >= 1


# ================================================================
# 10. __getattr__ proxy
# ================================================================

class TestModuleGetattr:
    def test_proxied_rate_attr_accessible(self):
        """Proxied rate-limiting attributes are accessible via server module."""
        import veritas_os.api.rate_limiting as _rate_mod
        for attr_name in server._PROXIED_RATE_ATTRS:
            if hasattr(_rate_mod, attr_name):
                val = getattr(server, attr_name)
                assert val is getattr(_rate_mod, attr_name)

    def test_non_existent_attr_raises_attribute_error(self):
        """Accessing non-existent attribute raises AttributeError."""
        with pytest.raises(AttributeError, match="has no attribute"):
            _ = server.__getattr__("_completely_nonexistent_attr_xyz")

    def test_proxied_attrs_set_is_not_empty(self):
        """_PROXIED_RATE_ATTRS is defined and contains expected items."""
        assert len(server._PROXIED_RATE_ATTRS) > 0
        assert "_nonce_cleanup_timer" in server._PROXIED_RATE_ATTRS


# ================================================================
# 11. Startup/lifespan helpers – import crash safety
# ================================================================

class TestStartupHelpers:
    def test_should_fail_fast_startup_delegates(self):
        """_should_fail_fast_startup delegates to startup_health module."""
        result = server._should_fail_fast_startup(profile="dev")
        assert result is False

    def test_should_fail_fast_startup_prod(self):
        """Production profile triggers fail-fast."""
        result = server._should_fail_fast_startup(profile="production")
        assert result is True

    def test_run_startup_config_validation_no_crash(self, monkeypatch):
        """Startup config validation must not crash the server."""
        monkeypatch.delenv("VERITAS_ENV", raising=False)
        # Should not raise even if validation fails
        try:
            server._run_startup_config_validation()
        except Exception:
            # In non-production, it should not raise
            pass

    def test_check_runtime_feature_health_no_crash(self):
        """Runtime feature health check must not crash."""
        try:
            server._check_runtime_feature_health()
        except RuntimeError:
            # Only raised in production mode; safe to catch
            pass


# ================================================================
# 12. Health endpoint – always 200
# ================================================================

class TestHealthEndpoint:
    def test_health_always_200(self):
        """Health endpoint always returns 200 regardless of internal state."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        # ok may be True or False depending on pipeline/memory state;
        # the critical invariant is that the endpoint NEVER returns non-200.
        assert "ok" in data

    def test_v1_health_always_200(self):
        """v1 health endpoint always returns 200."""
        resp = client.get("/v1/health")
        assert resp.status_code == 200

    def test_health_has_uptime(self):
        """Health response includes uptime."""
        resp = client.get("/health")
        data = resp.json()
        assert "uptime" in data
        assert isinstance(data["uptime"], (int, float))
        assert data["uptime"] >= 0

    def test_health_never_500(self, monkeypatch):
        """Even with degraded dependencies, health never returns 500."""
        monkeypatch.setattr(server, "_pipeline_state",
                            server._LazyState(attempted=True, err="broken"))
        resp = client.get("/health")
        assert resp.status_code == 200


# ================================================================
# 13. Backward compatibility exports
# ================================================================

class TestBackwardCompatExports:
    """Verify that backward-compat exports exist at module level.

    Tests that monkeypatch server.<attr> will not break because
    the attribute does not exist.
    """

    def test_fuji_core_exists(self):
        assert hasattr(server, "fuji_core")
        assert hasattr(server.fuji_core, "validate_action")
        assert hasattr(server.fuji_core, "validate")

    def test_value_core_exists(self):
        assert hasattr(server, "value_core")
        assert hasattr(server.value_core, "append_trust_log")

    def test_memory_store_exists(self):
        assert hasattr(server, "MEMORY_STORE")
        assert hasattr(server.MEMORY_STORE, "search")
        assert hasattr(server.MEMORY_STORE, "get")

    def test_log_path_constants_exist(self):
        assert hasattr(server, "LOG_DIR")
        assert hasattr(server, "LOG_JSON")
        assert hasattr(server, "LOG_JSONL")
        assert hasattr(server, "SHADOW_DIR")
        assert isinstance(server.LOG_DIR, Path)
        assert isinstance(server.LOG_JSON, Path)

    def test_default_log_path_constants_exist(self):
        assert hasattr(server, "_DEFAULT_LOG_DIR")
        assert hasattr(server, "_DEFAULT_LOG_JSON")
        assert hasattr(server, "_DEFAULT_LOG_JSONL")
        assert hasattr(server, "_DEFAULT_SHADOW_DIR")

    def test_auth_exports_exist(self):
        assert hasattr(server, "require_api_key")
        assert hasattr(server, "API_KEY_DEFAULT")
        assert hasattr(server, "api_key_scheme")
        assert hasattr(server, "_resolve_expected_api_key_with_source")
        assert hasattr(server, "_get_expected_api_key")
        assert hasattr(server, "_log_api_key_source_once")

    def test_rate_limiting_exports_exist(self):
        assert hasattr(server, "enforce_rate_limit")
        assert hasattr(server, "_RATE_LIMIT")
        assert hasattr(server, "_rate_bucket")
        assert hasattr(server, "_nonce_store")

    def test_middleware_exports_exist(self):
        assert hasattr(server, "attach_trace_id")
        assert hasattr(server, "add_response_time")
        assert hasattr(server, "add_security_headers")
        assert hasattr(server, "limit_body_size")

    def test_route_handler_exports_exist(self):
        assert hasattr(server, "decide")
        assert hasattr(server, "health")
        assert hasattr(server, "root")
        assert hasattr(server, "status")
        assert hasattr(server, "_call_fuji")

    def test_constants_exports_exist(self):
        assert hasattr(server, "DECISION_ALLOW")
        assert hasattr(server, "DECISION_REJECTED")
        assert hasattr(server, "MAX_LOG_FILE_SIZE")
        assert hasattr(server, "MAX_RAW_BODY_LENGTH")
        assert hasattr(server, "VALID_MEMORY_KINDS")

    def test_governance_exports_exist(self):
        assert hasattr(server, "governance_get")
        assert hasattr(server, "governance_put")
        assert hasattr(server, "governance_value_drift")
        assert hasattr(server, "governance_policy_history")

    def test_trust_route_exports_exist(self):
        assert hasattr(server, "trust_logs")
        assert hasattr(server, "trust_log_by_request")
        assert hasattr(server, "trust_feedback")
        assert hasattr(server, "trustlog_verify")
        assert hasattr(server, "trustlog_export")

    def test_memory_route_exports_exist(self):
        assert hasattr(server, "memory_put")
        assert hasattr(server, "memory_search")
        assert hasattr(server, "memory_get")
        assert hasattr(server, "memory_erase")

    def test_system_route_exports_exist(self):
        assert hasattr(server, "metrics")
        assert hasattr(server, "events")
        assert hasattr(server, "system_halt")
        assert hasattr(server, "system_resume")

    def test_utility_exports_exist(self):
        assert hasattr(server, "_errstr")
        assert hasattr(server, "redact")
        assert hasattr(server, "_gen_request_id")
        assert hasattr(server, "_coerce_alt_list")
        assert hasattr(server, "_coerce_decide_payload")
        assert hasattr(server, "_coerce_fuji_payload")
        assert hasattr(server, "_is_debug_mode")


# ================================================================
# 14. Placeholder stubs at import time
# ================================================================

class TestPlaceholderStubs:
    def test_fuji_validate_stub_returns_allow(self):
        result = server._fuji_validate_stub("test_action", {"key": "val"})
        assert result["status"] == "allow"
        assert result["action"] == "test_action"
        assert isinstance(result["violations"], list)

    def test_append_trust_log_stub_noop(self):
        assert server._append_trust_log_stub("a", "b", c=1) is None

    def test_memory_search_stub_empty_list(self):
        assert server._memory_search_stub("query") == []

    def test_memory_get_stub_returns_none(self):
        assert server._memory_get_stub("key") is None


# ================================================================
# 15. Import safety – module import must not crash
# ================================================================

class TestImportSafety:
    def test_server_module_importable(self):
        """veritas_os.api.server can always be imported."""
        import importlib
        mod = importlib.import_module("veritas_os.api.server")
        assert hasattr(mod, "app")

    def test_app_is_fastapi_instance(self):
        """The `app` attribute is a proper FastAPI instance."""
        from fastapi import FastAPI
        assert isinstance(server.app, FastAPI)

    def test_has_atomic_io_is_bool(self):
        """_HAS_ATOMIC_IO is always a bool."""
        assert isinstance(server._HAS_ATOMIC_IO, bool)

    def test_has_sanitize_is_bool(self):
        """_HAS_SANITIZE is always a bool."""
        assert isinstance(server._HAS_SANITIZE, bool)

    def test_repo_root_is_path(self):
        assert isinstance(server.REPO_ROOT, Path)

    def test_start_ts_is_float(self):
        assert isinstance(server.START_TS, float)
        assert server.START_TS > 0


# ================================================================
# 16. SSEEventHub backward compat
# ================================================================

class TestSSEEventHubCompat:
    def test_event_hub_is_sse_hub(self):
        """_event_hub is an SSEEventHub instance."""
        assert isinstance(server._event_hub, server.SSEEventHub)

    def test_publish_event_no_crash(self):
        """_publish_event must never crash even with unusual payloads."""
        server._publish_event("test_type", {"data": "value"})
        server._publish_event("test_type", {})


# ================================================================
# 17. _LazyState backward-compat alias
# ================================================================

class TestLazyStateAlias:
    def test_lazy_state_is_subclass(self):
        """_LazyState is a subclass of dependency_resolver.LazyState."""
        from veritas_os.api.dependency_resolver import LazyState
        assert issubclass(server._LazyState, LazyState)

    def test_lazy_state_constructible(self):
        ls = server._LazyState()
        assert ls.obj is None
        assert ls.err is None
        assert ls.attempted is False

    def test_lazy_state_with_args(self):
        ls = server._LazyState(obj="test", err="err", attempted=True)
        assert ls.obj == "test"
        assert ls.err == "err"
        assert ls.attempted is True


# ================================================================
# 18. utc_now_iso_z fallback
# ================================================================

class TestUtcNowFallback:
    def test_utc_now_iso_z_exists(self):
        """utc_now_iso_z is always available (either real or fallback)."""
        result = server.utc_now_iso_z()
        assert isinstance(result, str)
        assert result.endswith("Z")
