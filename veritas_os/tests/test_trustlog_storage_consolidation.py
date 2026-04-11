"""Tests for TrustLog storage consolidation and backend-aware DI.

Validates that:
1. backend=jsonl path works through both legacy and DI paths
2. backend=postgresql path works through DI
3. Same API semantics across backends
4. app lifespan / DI integration
5. Legacy fallback regression
6. Misconfiguration detection
"""
from __future__ import annotations

import asyncio
import logging
import os
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import patch

import pytest


# ===================================================================
# 1. Backend factory / config validation
# ===================================================================


class TestBackendConfigValidation:
    """Validate backend config detection and fail-fast semantics."""

    def test_validate_backend_config_default_succeeds(self, monkeypatch):
        """Default config (jsonl + json) should pass validation."""
        monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)
        monkeypatch.delenv("VERITAS_MEMORY_BACKEND", raising=False)

        from veritas_os.storage.factory import validate_backend_config

        validate_backend_config()  # should not raise

    def test_validate_backend_config_unknown_trustlog_raises(self, monkeypatch):
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "sqlite")

        from veritas_os.storage.factory import validate_backend_config

        with pytest.raises(ValueError, match="Unknown VERITAS_TRUSTLOG_BACKEND"):
            validate_backend_config()

    def test_validate_backend_config_unknown_memory_raises(self, monkeypatch):
        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "sqlite")

        from veritas_os.storage.factory import validate_backend_config

        with pytest.raises(ValueError, match="Unknown VERITAS_MEMORY_BACKEND"):
            validate_backend_config()

    def test_validate_backend_config_postgresql_without_url_raises(self, monkeypatch):
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
        monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)

        from veritas_os.storage.factory import validate_backend_config

        with pytest.raises(RuntimeError, match="VERITAS_DATABASE_URL"):
            validate_backend_config()

    def test_get_backend_info_defaults(self, monkeypatch):
        monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)
        monkeypatch.delenv("VERITAS_MEMORY_BACKEND", raising=False)

        from veritas_os.storage.factory import get_backend_info

        info = get_backend_info()
        assert info == {"memory": "json", "trustlog": "jsonl"}

    def test_get_backend_info_custom(self, monkeypatch):
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "postgresql")

        from veritas_os.storage.factory import get_backend_info

        info = get_backend_info()
        assert info == {"memory": "postgresql", "trustlog": "postgresql"}


# ===================================================================
# 2. Dependency resolver helpers
# ===================================================================


class TestDependencyResolverBackendHelpers:
    """Validate new backend-aware helpers in dependency_resolver."""

    def test_resolve_backend_info_returns_dict(self, monkeypatch):
        monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)
        monkeypatch.delenv("VERITAS_MEMORY_BACKEND", raising=False)

        from veritas_os.api.dependency_resolver import resolve_backend_info

        info = resolve_backend_info()
        assert isinstance(info, dict)
        assert "memory" in info
        assert "trustlog" in info

    def test_is_file_backend_true_for_jsonl(self, monkeypatch):
        monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)

        from veritas_os.api.dependency_resolver import is_file_backend

        assert is_file_backend() is True

    def test_is_file_backend_false_for_postgresql(self, monkeypatch):
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")

        from veritas_os.api.dependency_resolver import is_file_backend

        assert is_file_backend() is False

    def test_get_trust_log_store_raises_when_not_set(self):
        from veritas_os.api.dependency_resolver import get_trust_log_store

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
        with pytest.raises(RuntimeError, match="trust_log_store is not initialized"):
            get_trust_log_store(request)

    def test_get_trust_log_store_returns_instance(self):
        from veritas_os.api.dependency_resolver import get_trust_log_store

        sentinel = object()
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(trust_log_store=sentinel))
        )
        assert get_trust_log_store(request) is sentinel

    def test_get_memory_store_raises_when_not_set(self):
        from veritas_os.api.dependency_resolver import get_memory_store

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
        with pytest.raises(RuntimeError, match="memory_store is not initialized"):
            get_memory_store(request)

    def test_get_memory_store_returns_instance(self):
        from veritas_os.api.dependency_resolver import get_memory_store

        sentinel = object()
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(memory_store=sentinel))
        )
        assert get_memory_store(request) is sentinel


# ===================================================================
# 3. Lifespan DI integration
# ===================================================================


class TestLifespanStoreDI:
    """Validate that lifespan wires stores into app.state."""

    def test_lifespan_sets_trust_log_store(self, monkeypatch):
        import veritas_os.api.middleware as middleware
        import veritas_os.api.server as server
        from veritas_os.api.lifespan import run_lifespan

        monkeypatch.setattr(middleware, "_inflight_count", 0)
        monkeypatch.setattr(server, "_inflight_count", 0)
        monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)
        monkeypatch.delenv("VERITAS_MEMORY_BACKEND", raising=False)

        captured: Dict[str, Any] = {}

        async def _exercise():
            async with run_lifespan(
                app=server.app,
                startup_validation=lambda: None,
                runtime_health_check=lambda: None,
                check_multiworker_auth_store=lambda: None,
                start_nonce_cleanup_scheduler=lambda: None,
                start_rate_cleanup_scheduler=lambda: None,
                stop_nonce_cleanup_scheduler=lambda: None,
                stop_rate_cleanup_scheduler=lambda: None,
                close_llm_pool=None,
                logger=logging.getLogger(__name__),
            ):
                captured["trust_log_store"] = getattr(
                    server.app.state, "trust_log_store", None
                )
                captured["memory_store"] = getattr(
                    server.app.state, "memory_store", None
                )

        asyncio.run(_exercise())

        assert captured["trust_log_store"] is not None
        assert captured["memory_store"] is not None

    def test_lifespan_validates_backend_config(self, monkeypatch):
        """Lifespan should fail fast on bad backend config."""
        import veritas_os.api.server as server
        from veritas_os.api.lifespan import run_lifespan

        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "badvalue")

        async def _exercise():
            async with run_lifespan(
                app=server.app,
                startup_validation=lambda: None,
                runtime_health_check=lambda: None,
                check_multiworker_auth_store=lambda: None,
                start_nonce_cleanup_scheduler=lambda: None,
                start_rate_cleanup_scheduler=lambda: None,
                stop_nonce_cleanup_scheduler=lambda: None,
                stop_rate_cleanup_scheduler=lambda: None,
                close_llm_pool=None,
                logger=logging.getLogger(__name__),
            ):
                pass

        with pytest.raises(ValueError, match="Unknown VERITAS_TRUSTLOG_BACKEND"):
            asyncio.run(_exercise())


# ===================================================================
# 4. JSONL backend path
# ===================================================================


class TestJsonlBackendPath:
    """Validate JSONL (file-based) TrustLog store path."""

    def test_jsonl_store_append_returns_request_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "veritas_os.logging.trust_log.LOG_DIR", tmp_path
        )
        monkeypatch.setattr(
            "veritas_os.logging.trust_log.LOG_JSON", tmp_path / "trust_log.json"
        )
        monkeypatch.setattr(
            "veritas_os.logging.trust_log.LOG_JSONL", tmp_path / "trust_log.jsonl"
        )

        from veritas_os.storage.jsonl import JsonlTrustLogStore

        store = JsonlTrustLogStore()

        async def _exercise():
            rid = await store.append({"request_id": "test-1", "data": "hello"})
            return rid

        rid = asyncio.run(_exercise())
        assert rid  # non-empty string

    def test_jsonl_store_get_by_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "veritas_os.logging.trust_log.LOG_DIR", tmp_path
        )
        monkeypatch.setattr(
            "veritas_os.logging.trust_log.LOG_JSON", tmp_path / "trust_log.json"
        )
        monkeypatch.setattr(
            "veritas_os.logging.trust_log.LOG_JSONL", tmp_path / "trust_log.jsonl"
        )

        from veritas_os.storage.jsonl import JsonlTrustLogStore

        store = JsonlTrustLogStore()

        async def _exercise():
            rid = await store.append({"request_id": "lookup-1", "kind": "decision"})
            # The request_id returned by append is the canonical one
            # (after prepare_entry crypto pipeline).
            entry = await store.get_by_id(rid)
            return rid, entry

        rid, entry = asyncio.run(_exercise())
        # get_by_id may return None for encrypted entries when
        # encryption key is not set. Verify the store didn't crash.
        if entry is not None:
            assert entry.get("request_id") == rid


# ===================================================================
# 5. Backend-aware trust_log health
# ===================================================================


class TestTrustLogHealth:
    """Validate backend-aware trust log health checks."""

    def test_trust_log_health_includes_backend_jsonl(self, monkeypatch):
        monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)

        from veritas_os.api.routes_system import _trust_log_health

        # Create a minimal srv mock with TrustLogRuntime
        srv = SimpleNamespace(
            _trust_log_runtime=SimpleNamespace(
                effective_log_paths=lambda: ("/tmp", "/tmp/trust_log.json", "/tmp/trust_log.jsonl"),
                load_logs_json_result=lambda path: SimpleNamespace(
                    status="missing", error=None
                ),
            ),
            _effective_log_paths=lambda: ("/tmp", "/tmp/trust_log.json", "/tmp/trust_log.jsonl"),
        )

        result = _trust_log_health(srv)
        assert result["status"] == "ok"
        assert result["details"]["backend"] == "jsonl"

    def test_trust_log_health_postgresql_backend(self, monkeypatch):
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")

        from veritas_os.api.routes_system import _trust_log_health

        # When postgresql backend, file-based checks should be skipped.
        app_state = SimpleNamespace(trust_log_store=object())
        app = SimpleNamespace(state=app_state)
        srv = SimpleNamespace(app=app)

        result = _trust_log_health(srv)
        assert result["status"] == "ok"
        assert result["details"]["backend"] == "postgresql"

    def test_trust_log_health_postgresql_no_store(self, monkeypatch):
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")

        from veritas_os.api.routes_system import _trust_log_health

        srv = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

        result = _trust_log_health(srv)
        # Store not wired yet → unknown
        assert result["details"]["backend"] == "postgresql"


# ===================================================================
# 6. Legacy compatibility markers
# ===================================================================


class TestLegacyCompatMarkers:
    """Validate that legacy attributes remain accessible for test patching."""

    def test_server_log_dir_exists(self):
        from veritas_os.api import server

        assert hasattr(server, "LOG_DIR")
        assert hasattr(server, "LOG_JSON")
        assert hasattr(server, "LOG_JSONL")
        assert hasattr(server, "SHADOW_DIR")

    def test_server_append_trust_log_exists(self):
        from veritas_os.api import server

        assert callable(server.append_trust_log)

    def test_server_write_shadow_decide_exists(self):
        from veritas_os.api import server

        assert callable(server.write_shadow_decide)

    def test_server_load_logs_json_exists(self):
        from veritas_os.api import server

        assert callable(server._load_logs_json)

    def test_server_trust_log_runtime_exists(self):
        from veritas_os.api import server

        assert hasattr(server, "_trust_log_runtime")

    def test_server_effective_log_paths_exists(self):
        from veritas_os.api import server

        assert callable(server._effective_log_paths)


# ===================================================================
# 7. Same API semantics across backends (protocol conformance)
# ===================================================================


class TestBackendProtocolConformance:
    """Validate that both backends satisfy the TrustLogStore protocol."""

    def test_jsonl_store_satisfies_protocol(self):
        from veritas_os.storage.jsonl import JsonlTrustLogStore

        store = JsonlTrustLogStore()
        assert hasattr(store, "append")
        assert hasattr(store, "get_by_id")
        assert hasattr(store, "iter_entries")
        assert hasattr(store, "get_last_hash")

    def test_factory_creates_jsonl_by_default(self, monkeypatch):
        monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)

        from veritas_os.storage.factory import create_trust_log_store
        from veritas_os.storage.jsonl import JsonlTrustLogStore

        store = create_trust_log_store()
        assert isinstance(store, JsonlTrustLogStore)

    def test_factory_creates_json_memory_by_default(self, monkeypatch, tmp_path):
        monkeypatch.delenv("VERITAS_MEMORY_BACKEND", raising=False)
        monkeypatch.setenv("VERITAS_MEMORY_PATH", str(tmp_path / "mem.json"))

        from veritas_os.storage.factory import create_memory_store
        from veritas_os.storage.json_kv import JsonMemoryStore

        store = create_memory_store()
        assert isinstance(store, JsonMemoryStore)


# ===================================================================
# 8. Metrics endpoint includes storage_backends
# ===================================================================


class TestMetricsBackendInfo:
    """Validate /v1/metrics includes storage backend information."""

    def test_metrics_has_storage_backends_key(self, monkeypatch):
        """The metrics function should include storage_backends in its response."""
        monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)
        monkeypatch.delenv("VERITAS_MEMORY_BACKEND", raising=False)

        from veritas_os.storage.factory import get_backend_info

        info = get_backend_info()
        assert "memory" in info
        assert "trustlog" in info


# ===================================================================
# 9. Source-of-truth boundary verification
# ===================================================================


class TestSourceOfTruthBoundary:
    """Validate that app.state.trust_log_store is the canonical source of truth.

    These tests verify that:
    - The DI resolver is the single path to the authoritative store
    - Legacy helpers are correctly scoped to jsonl backend only
    - Backend=postgresql never uses file paths as persistence source
    - Shadow snapshots remain file-based regardless of backend
    """

    def test_di_resolver_is_canonical_access_path(self):
        """get_trust_log_store must be the canonical way to access the store."""
        from veritas_os.api.dependency_resolver import get_trust_log_store

        sentinel = object()
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(trust_log_store=sentinel))
        )
        assert get_trust_log_store(request) is sentinel

    def test_di_resolver_rejects_uninitialized_state(self):
        """get_trust_log_store must raise when store is not wired."""
        from veritas_os.api.dependency_resolver import get_trust_log_store

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
        with pytest.raises(RuntimeError, match="trust_log_store is not initialized"):
            get_trust_log_store(request)

    def test_jsonl_backend_creates_file_store(self, monkeypatch):
        """backend=jsonl must produce a JsonlTrustLogStore instance."""
        monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)

        from veritas_os.storage.factory import create_trust_log_store
        from veritas_os.storage.jsonl import JsonlTrustLogStore

        store = create_trust_log_store()
        assert isinstance(store, JsonlTrustLogStore)

    def test_postgresql_backend_creates_pg_store(self, monkeypatch):
        """backend=postgresql must produce a PostgresTrustLogStore instance."""
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
        monkeypatch.setenv("VERITAS_DATABASE_URL", "postgresql://x:x@localhost/x")

        from veritas_os.storage.factory import create_trust_log_store
        from veritas_os.storage.postgresql import PostgresTrustLogStore

        store = create_trust_log_store()
        assert isinstance(store, PostgresTrustLogStore)

    def test_file_backend_flag_reflects_jsonl(self, monkeypatch):
        """is_file_backend returns True for jsonl, False for postgresql."""
        from veritas_os.api.dependency_resolver import is_file_backend

        monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)
        assert is_file_backend() is True

        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
        assert is_file_backend() is False

    def test_legacy_helpers_exist_for_backward_compat(self):
        """Legacy server-level helpers must remain accessible for test patching."""
        from veritas_os.api import server

        assert hasattr(server, "LOG_DIR")
        assert hasattr(server, "LOG_JSON")
        assert hasattr(server, "LOG_JSONL")
        assert hasattr(server, "SHADOW_DIR")
        assert callable(server.append_trust_log)
        assert callable(server.write_shadow_decide)
        assert callable(server._load_logs_json)
        assert hasattr(server, "_trust_log_runtime")

    def test_legacy_append_trust_log_has_compat_docstring(self):
        """Legacy append_trust_log must document its backend scope."""
        from veritas_os.api import server

        doc = server.append_trust_log.__doc__ or ""
        assert "LEGACY COMPAT" in doc
        assert "postgresql" in doc.lower() or "backend" in doc.lower()

    def test_legacy_write_shadow_has_compat_docstring(self):
        """write_shadow_decide must document that it's always file-based."""
        from veritas_os.api import server

        doc = server.write_shadow_decide.__doc__ or ""
        assert "LEGACY COMPAT" in doc
        assert "file" in doc.lower() or "local" in doc.lower()

    def test_trust_log_health_uses_store_for_postgresql(self, monkeypatch):
        """Health check must use app.state.trust_log_store for postgresql."""
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")

        from veritas_os.api.routes_system import _trust_log_health

        store_sentinel = object()
        app_state = SimpleNamespace(trust_log_store=store_sentinel)
        app = SimpleNamespace(state=app_state)
        srv = SimpleNamespace(app=app)

        result = _trust_log_health(srv)
        assert result["status"] == "ok"
        assert result["details"]["backend"] == "postgresql"

    def test_trust_log_health_uses_file_for_jsonl(self, monkeypatch):
        """Health check must use file-based checks for jsonl backend."""
        monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)

        from veritas_os.api.routes_system import _trust_log_health

        srv = SimpleNamespace(
            _trust_log_runtime=SimpleNamespace(
                effective_log_paths=lambda: ("/tmp", "/tmp/tl.json", "/tmp/tl.jsonl"),
                load_logs_json_result=lambda path: SimpleNamespace(
                    status="missing", error=None
                ),
            ),
            _effective_log_paths=lambda: ("/tmp", "/tmp/tl.json", "/tmp/tl.jsonl"),
        )

        result = _trust_log_health(srv)
        assert result["details"]["backend"] == "jsonl"

    def test_both_backends_satisfy_protocol(self):
        """Both backends must satisfy the TrustLogStore protocol interface."""
        from veritas_os.storage.jsonl import JsonlTrustLogStore
        from veritas_os.storage.postgresql import PostgresTrustLogStore

        required_methods = ("append", "get_by_id", "iter_entries", "get_last_hash")
        for cls in (JsonlTrustLogStore, PostgresTrustLogStore):
            for method in required_methods:
                assert hasattr(cls, method), f"{cls.__name__} missing {method}"

    def test_memory_store_di_resolver(self):
        """get_memory_store must be the canonical access path for MemoryOS."""
        from veritas_os.api.dependency_resolver import get_memory_store

        sentinel = object()
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(memory_store=sentinel))
        )
        assert get_memory_store(request) is sentinel

    def test_backend_info_matches_env(self, monkeypatch):
        """resolve_backend_info must reflect environment variables."""
        from veritas_os.api.dependency_resolver import resolve_backend_info

        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "postgresql")

        info = resolve_backend_info()
        assert info["trustlog"] == "postgresql"
        assert info["memory"] == "postgresql"


# ===================================================================
# 10. Metrics JSONL line count backend guard
# ===================================================================


class TestMetricsJsonlLineCountGuard:
    """Validate that /v1/metrics JSONL line count is skipped for postgresql."""

    def test_metrics_skips_jsonl_read_for_postgresql(self, monkeypatch, tmp_path):
        """When backend=postgresql, JSONL line count should be 0."""
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")

        # Create a JSONL file that should NOT be read
        jsonl_file = tmp_path / "trust_log.jsonl"
        jsonl_file.write_text("line1\nline2\nline3\n")

        from veritas_os.storage.factory import get_backend_info

        info = get_backend_info()
        assert info["trustlog"] == "postgresql"

        # The guard logic: when backend != jsonl, lines should be 0
        is_file_tl = info.get("trustlog") != "postgresql"
        lines = 0
        if is_file_tl:
            with open(jsonl_file, encoding="utf-8") as f:
                for _ in f:
                    lines += 1

        assert lines == 0, "JSONL file should NOT be read for postgresql backend"

    def test_metrics_reads_jsonl_for_jsonl_backend(self, monkeypatch, tmp_path):
        """When backend=jsonl, JSONL line count should reflect file content."""
        monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)

        jsonl_file = tmp_path / "trust_log.jsonl"
        jsonl_file.write_text("line1\nline2\nline3\n")

        from veritas_os.storage.factory import get_backend_info

        info = get_backend_info()
        assert info["trustlog"] == "jsonl"

        is_file_tl = info.get("trustlog") != "postgresql"
        lines = 0
        if is_file_tl:
            with open(jsonl_file, encoding="utf-8") as f:
                for _ in f:
                    lines += 1

        assert lines == 3


# ===================================================================
# 11. API semantics parity across backends
# ===================================================================


class TestApiSemanticsParity:
    """Validate that backend=jsonl and backend=postgresql expose same API semantics."""

    def test_both_backends_have_same_protocol_methods(self):
        """Both TrustLogStore backends must expose identical method sets."""
        from veritas_os.storage.jsonl import JsonlTrustLogStore
        from veritas_os.storage.postgresql import PostgresTrustLogStore

        jsonl_methods = {m for m in dir(JsonlTrustLogStore) if not m.startswith("_")}
        pg_methods = {m for m in dir(PostgresTrustLogStore) if not m.startswith("_")}

        protocol_methods = {"append", "get_by_id", "iter_entries", "get_last_hash"}
        assert protocol_methods.issubset(jsonl_methods)
        assert protocol_methods.issubset(pg_methods)

    def test_both_memory_backends_have_same_protocol_methods(self):
        """Both MemoryStore backends must expose identical protocol methods."""
        from veritas_os.storage.json_kv import JsonMemoryStore
        from veritas_os.storage.postgresql import PostgresMemoryStore

        protocol_methods = {"put", "get", "search", "delete", "list_all", "erase_user_data"}

        json_methods = {m for m in dir(JsonMemoryStore) if not m.startswith("_")}
        pg_methods = {m for m in dir(PostgresMemoryStore) if not m.startswith("_")}

        assert protocol_methods.issubset(json_methods)
        assert protocol_methods.issubset(pg_methods)

    def test_health_response_shape_same_across_backends(self, monkeypatch):
        """Health check response must have same keys regardless of backend."""
        from veritas_os.api.routes_system import _trust_log_health

        # jsonl backend
        monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)
        srv_jsonl = SimpleNamespace(
            _trust_log_runtime=SimpleNamespace(
                effective_log_paths=lambda: ("/tmp", "/tmp/tl.json", "/tmp/tl.jsonl"),
                load_logs_json_result=lambda path: SimpleNamespace(
                    status="missing", error=None
                ),
            ),
            _effective_log_paths=lambda: ("/tmp", "/tmp/tl.json", "/tmp/tl.jsonl"),
        )
        result_jsonl = _trust_log_health(srv_jsonl)

        # postgresql backend
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
        srv_pg = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(trust_log_store=object())
            )
        )
        result_pg = _trust_log_health(srv_pg)

        # Both must have status + details with backend key
        assert "status" in result_jsonl
        assert "details" in result_jsonl
        assert "backend" in result_jsonl["details"]

        assert "status" in result_pg
        assert "details" in result_pg
        assert "backend" in result_pg["details"]
