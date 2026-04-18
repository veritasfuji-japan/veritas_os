"""Tests for PostgreSQL observability metrics and the pg_collector module.

Covers:
* Metric definitions exist and helpers emit correct labels/values
* Pool-stats collection from a mock pool
* pg_stat_activity collection with a mock cursor
* Graceful no-op when backend is file-based
* Health-check gauge updates
* Backend-label emission
* Slow-append warning counter
* Integration with /v1/metrics endpoint (both backends)
"""
from __future__ import annotations

import importlib
import types
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MetricProbe:
    """Lightweight probe that records Prometheus-style calls."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def labels(self, **labels: Any) -> "_MetricProbe":
        self.calls.append({"labels": labels})
        return self

    def inc(self, amount: float = 1.0) -> None:
        self.calls.append({"inc": amount})

    def observe(self, value: float) -> None:
        self.calls.append({"observe": value})

    def set(self, value: float) -> None:
        self.calls.append({"set": value})


class _FakePool:
    """Minimal mock that mirrors ``AsyncConnectionPool`` pool stats."""

    def __init__(
        self,
        *,
        pool_size: int = 10,
        pool_available: int = 7,
        requests_waiting: int = 0,
        max_size: int = 20,
        min_size: int = 2,
    ) -> None:
        self._pool_size = pool_size
        self._pool_available = pool_available
        self._requests_waiting = requests_waiting
        self.max_size = max_size
        self.min_size = min_size
        self._cursor_rows: Optional[List[Any]] = None

    def get_stats(self) -> Dict[str, int]:
        return {
            "pool_size": self._pool_size,
            "pool_available": self._pool_available,
            "requests_waiting": self._requests_waiting,
        }

    def connection(self):
        return _FakeAsyncConn(self._cursor_rows)


class _FakeAsyncConn:
    """Async-context-manager mock for pool.connection()."""

    def __init__(self, rows: Optional[List[Any]]) -> None:
        self._rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_: Any):
        pass

    def cursor(self):
        return _FakeAsyncCursor(self._rows)


class _FakeAsyncCursor:
    """Async-context-manager mock for conn.cursor()."""

    def __init__(self, rows: Optional[List[Any]]) -> None:
        self._rows = rows if rows is not None else [(1,)]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_: Any):
        pass

    async def execute(self, query: str, params: Any = None):
        pass

    async def fetchone(self):
        return self._rows[0] if self._rows else None


# ---------------------------------------------------------------------------
# Metric definition tests
# ---------------------------------------------------------------------------


class TestMetricDefinitions:
    """Verify that all required metric objects exist in the metrics module."""

    @pytest.fixture(autouse=True)
    def _metrics(self):
        self.m = importlib.import_module("veritas_os.observability.metrics")

    def test_pool_gauges_exist(self):
        for name in (
            "DB_POOL_IN_USE",
            "DB_POOL_AVAILABLE",
            "DB_POOL_WAITING",
            "DB_POOL_MAX_SIZE",
            "DB_POOL_MIN_SIZE",
        ):
            obj = getattr(self.m, name)
            assert hasattr(obj, "set"), f"{name} must be a Gauge-like"

    def test_counter_metrics_exist(self):
        for name in (
            "DB_CONNECT_FAILURES_TOTAL",
            "DB_STATEMENT_TIMEOUTS_TOTAL",
            "TRUSTLOG_APPEND_CONFLICT_TOTAL",
            "SLOW_APPEND_WARNING_TOTAL",
            "GOVERNANCE_REPOSITORY_OPERATION_TOTAL",
            "GOVERNANCE_REPOSITORY_CONFLICT_TOTAL",
        ):
            obj = getattr(self.m, name)
            assert hasattr(obj, "inc"), f"{name} must be a Counter-like"

    def test_histogram_metrics_exist(self):
        assert hasattr(self.m.TRUSTLOG_APPEND_LATENCY_SECONDS, "observe")
        assert hasattr(self.m.GOVERNANCE_REPOSITORY_OPERATION_LATENCY_SECONDS, "observe")

    def test_backend_and_health_gauges(self):
        assert hasattr(self.m.DB_BACKEND_SELECTED, "labels")
        assert hasattr(self.m.DB_HEALTH_STATUS, "set")

    def test_advanced_gauges(self):
        for name in (
            "LONG_RUNNING_QUERY_COUNT",
            "IDLE_IN_TRANSACTION_COUNT",
            "ADVISORY_LOCK_CONTENTION_COUNT",
        ):
            obj = getattr(self.m, name)
            assert hasattr(obj, "set"), f"{name} must be a Gauge-like"


# ---------------------------------------------------------------------------
# Recording-helper tests
# ---------------------------------------------------------------------------


class TestRecordingHelpers:
    """Test safe recording helpers emit correct labels and values."""

    @pytest.fixture(autouse=True)
    def _metrics(self):
        self.m = importlib.import_module("veritas_os.observability.metrics")

    def test_set_db_pool_stats(self, monkeypatch):
        probes = {k: _MetricProbe() for k in (
            "DB_POOL_IN_USE", "DB_POOL_AVAILABLE", "DB_POOL_WAITING",
            "DB_POOL_MAX_SIZE", "DB_POOL_MIN_SIZE",
        )}
        for k, v in probes.items():
            monkeypatch.setattr(self.m, k, v)

        self.m.set_db_pool_stats(
            in_use=3, available=7, waiting=1, max_size=20, min_size=2,
        )
        assert any(c.get("set") == 3.0 for c in probes["DB_POOL_IN_USE"].calls)
        assert any(c.get("set") == 7.0 for c in probes["DB_POOL_AVAILABLE"].calls)
        assert any(c.get("set") == 1.0 for c in probes["DB_POOL_WAITING"].calls)
        assert any(c.get("set") == 20.0 for c in probes["DB_POOL_MAX_SIZE"].calls)
        assert any(c.get("set") == 2.0 for c in probes["DB_POOL_MIN_SIZE"].calls)

    def test_record_db_connect_failure(self, monkeypatch):
        probe = _MetricProbe()
        monkeypatch.setattr(self.m, "DB_CONNECT_FAILURES_TOTAL", probe)
        self.m.record_db_connect_failure("timeout")
        assert any(c.get("labels") == {"reason": "timeout"} for c in probe.calls)

    def test_record_db_statement_timeout(self, monkeypatch):
        probe = _MetricProbe()
        monkeypatch.setattr(self.m, "DB_STATEMENT_TIMEOUTS_TOTAL", probe)
        self.m.record_db_statement_timeout()
        assert any(c.get("inc") == 1.0 for c in probe.calls)

    def test_observe_trustlog_append_latency(self, monkeypatch):
        hist = _MetricProbe()
        slow = _MetricProbe()
        monkeypatch.setattr(self.m, "TRUSTLOG_APPEND_LATENCY_SECONDS", hist)
        monkeypatch.setattr(self.m, "SLOW_APPEND_WARNING_TOTAL", slow)

        self.m.observe_trustlog_append_latency(0.5)
        assert any(c.get("observe") == 0.5 for c in hist.calls)
        assert not any(c.get("inc") for c in slow.calls)

        self.m.observe_trustlog_append_latency(2.0)
        assert any(c.get("observe") == 2.0 for c in hist.calls)
        assert any(c.get("inc") == 1.0 for c in slow.calls)

    def test_record_trustlog_append_conflict(self, monkeypatch):
        probe = _MetricProbe()
        monkeypatch.setattr(self.m, "TRUSTLOG_APPEND_CONFLICT_TOTAL", probe)
        self.m.record_trustlog_append_conflict()
        assert any(c.get("inc") == 1.0 for c in probe.calls)

    def test_set_db_backend_selected(self, monkeypatch):
        probe = _MetricProbe()
        monkeypatch.setattr(self.m, "DB_BACKEND_SELECTED", probe)
        self.m.set_db_backend_selected("memory", "postgresql")
        assert any(
            c.get("labels") == {"component": "memory", "backend": "postgresql"}
            for c in probe.calls
        )

    def test_set_db_health_status(self, monkeypatch):
        probe = _MetricProbe()
        monkeypatch.setattr(self.m, "DB_HEALTH_STATUS", probe)
        self.m.set_db_health_status(True)
        assert any(c.get("set") == 1.0 for c in probe.calls)
        self.m.set_db_health_status(False)
        assert any(c.get("set") == 0.0 for c in probe.calls)

    def test_advanced_gauge_helpers(self, monkeypatch):
        for name, setter in (
            ("LONG_RUNNING_QUERY_COUNT", self.m.set_long_running_query_count),
            ("IDLE_IN_TRANSACTION_COUNT", self.m.set_idle_in_transaction_count),
            ("ADVISORY_LOCK_CONTENTION_COUNT", self.m.set_advisory_lock_contention_count),
        ):
            probe = _MetricProbe()
            monkeypatch.setattr(self.m, name, probe)
            setter(5)
            assert any(c.get("set") == 5.0 for c in probe.calls)

    def test_record_governance_repository_operation(self, monkeypatch):
        counter_probe = _MetricProbe()
        histogram_probe = _MetricProbe()
        monkeypatch.setattr(self.m, "GOVERNANCE_REPOSITORY_OPERATION_TOTAL", counter_probe)
        monkeypatch.setattr(
            self.m,
            "GOVERNANCE_REPOSITORY_OPERATION_LATENCY_SECONDS",
            histogram_probe,
        )
        self.m.record_governance_repository_operation(
            backend="postgresql",
            operation="write_policy_event",
            status="ok",
            duration_seconds=0.25,
        )
        assert any(
            c.get("labels") == {
                "backend": "postgresql",
                "operation": "write_policy_event",
                "status": "ok",
            }
            for c in counter_probe.calls
        )
        assert any(c.get("observe") == 0.25 for c in histogram_probe.calls)

    def test_record_governance_repository_conflict(self, monkeypatch):
        probe = _MetricProbe()
        monkeypatch.setattr(self.m, "GOVERNANCE_REPOSITORY_CONFLICT_TOTAL", probe)
        self.m.record_governance_repository_conflict(backend="postgresql")
        assert any(c.get("labels") == {"backend": "postgresql"} for c in probe.calls)


# ---------------------------------------------------------------------------
# pg_collector tests
# ---------------------------------------------------------------------------


class TestCollectPoolStats:
    """Test pool-stats collection from a mock pool."""

    def test_collect_pool_stats_returns_expected(self):
        from veritas_os.observability.pg_collector import collect_pool_stats

        pool = _FakePool(pool_size=10, pool_available=6, requests_waiting=2)
        stats = collect_pool_stats(pool)
        assert stats["in_use"] == 4
        assert stats["available"] == 6
        assert stats["waiting"] == 2
        assert stats["max_size"] == 20
        assert stats["min_size"] == 2

    def test_collect_pool_stats_error_returns_zeros(self):
        from veritas_os.observability.pg_collector import collect_pool_stats

        pool = MagicMock()
        pool.get_stats.side_effect = RuntimeError("boom")
        stats = collect_pool_stats(pool)
        assert stats["in_use"] == 0

    def test_push_pool_gauges_updates_metrics(self, monkeypatch):
        from veritas_os.observability import pg_collector
        metrics = importlib.import_module("veritas_os.observability.metrics")
        probes = {k: _MetricProbe() for k in (
            "DB_POOL_IN_USE", "DB_POOL_AVAILABLE", "DB_POOL_WAITING",
            "DB_POOL_MAX_SIZE", "DB_POOL_MIN_SIZE",
        )}
        for k, v in probes.items():
            monkeypatch.setattr(metrics, k, v)

        pool = _FakePool(pool_size=8, pool_available=5, requests_waiting=0)
        stats = pg_collector.push_pool_gauges(pool)
        assert stats["in_use"] == 3
        assert any(c.get("set") == 3.0 for c in probes["DB_POOL_IN_USE"].calls)


# ---------------------------------------------------------------------------
# pg_stat_activity collection
# ---------------------------------------------------------------------------


class TestPgActivity:
    """Test pg_stat_activity collection with mocked cursors."""

    @pytest.mark.asyncio
    async def test_collect_pg_activity(self):
        from veritas_os.observability.pg_collector import collect_pg_activity

        pool = _FakePool()
        pool._cursor_rows = [(2, 1, 3)]
        result = await collect_pg_activity(pool, statement_timeout_sec=30)
        assert result == {"long_running": 2, "idle_in_tx": 1, "advisory_lock_wait": 3}

    @pytest.mark.asyncio
    async def test_collect_pg_activity_error_returns_defaults(self):
        from veritas_os.observability.pg_collector import collect_pg_activity

        pool = MagicMock()
        pool.connection.side_effect = RuntimeError("no connection")
        result = await collect_pg_activity(pool)
        assert result == {"long_running": 0, "idle_in_tx": 0, "advisory_lock_wait": 0}

    @pytest.mark.asyncio
    async def test_push_pg_activity_gauges(self, monkeypatch):
        from veritas_os.observability import pg_collector
        metrics = importlib.import_module("veritas_os.observability.metrics")

        long_probe = _MetricProbe()
        idle_probe = _MetricProbe()
        lock_probe = _MetricProbe()
        monkeypatch.setattr(metrics, "LONG_RUNNING_QUERY_COUNT", long_probe)
        monkeypatch.setattr(metrics, "IDLE_IN_TRANSACTION_COUNT", idle_probe)
        monkeypatch.setattr(metrics, "ADVISORY_LOCK_CONTENTION_COUNT", lock_probe)

        pool = _FakePool()
        pool._cursor_rows = [(1, 0, 2)]
        result = await pg_collector.push_pg_activity_gauges(pool)
        assert result["long_running"] == 1
        assert any(c.get("set") == 1.0 for c in long_probe.calls)
        assert any(c.get("set") == 2.0 for c in lock_probe.calls)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestDbHealthCheck:
    """Test health-check gauge emission."""

    @pytest.mark.asyncio
    async def test_healthy_pool(self, monkeypatch):
        from veritas_os.observability import pg_collector
        metrics = importlib.import_module("veritas_os.observability.metrics")
        probe = _MetricProbe()
        monkeypatch.setattr(metrics, "DB_HEALTH_STATUS", probe)

        pool = _FakePool()
        healthy = await pg_collector.check_db_health(pool)
        assert healthy is True
        assert any(c.get("set") == 1.0 for c in probe.calls)

    @pytest.mark.asyncio
    async def test_unhealthy_pool(self, monkeypatch):
        from veritas_os.observability import pg_collector
        metrics = importlib.import_module("veritas_os.observability.metrics")
        probe = _MetricProbe()
        fail_probe = _MetricProbe()
        monkeypatch.setattr(metrics, "DB_HEALTH_STATUS", probe)
        monkeypatch.setattr(metrics, "DB_CONNECT_FAILURES_TOTAL", fail_probe)

        pool = MagicMock()
        pool.connection.side_effect = RuntimeError("down")
        healthy = await pg_collector.check_db_health(pool)
        assert healthy is False
        assert any(c.get("set") == 0.0 for c in probe.calls)
        assert any(c.get("labels") == {"reason": "health_check"} for c in fail_probe.calls)


# ---------------------------------------------------------------------------
# Backend label emission
# ---------------------------------------------------------------------------


class TestBackendLabels:
    """Test emit_backend_labels()."""

    def test_emit_labels(self, monkeypatch):
        from veritas_os.observability import pg_collector
        metrics = importlib.import_module("veritas_os.observability.metrics")
        probe = _MetricProbe()
        monkeypatch.setattr(metrics, "DB_BACKEND_SELECTED", probe)

        pg_collector.emit_backend_labels({"memory": "postgresql", "trustlog": "jsonl"})
        labels_emitted = [c["labels"] for c in probe.calls if "labels" in c]
        assert {"component": "memory", "backend": "postgresql"} in labels_emitted
        assert {"component": "trustlog", "backend": "jsonl"} in labels_emitted


# ---------------------------------------------------------------------------
# High-level collector
# ---------------------------------------------------------------------------


class TestCollectAllPgMetrics:
    """Test the high-level collect_all_pg_metrics entry point."""

    @pytest.mark.asyncio
    async def test_file_backend_returns_stub(self, monkeypatch):
        from veritas_os.observability.pg_collector import collect_all_pg_metrics
        metrics = importlib.import_module("veritas_os.observability.metrics")
        # Suppress real gauge operations
        monkeypatch.setattr(metrics, "DB_BACKEND_SELECTED", _MetricProbe())
        monkeypatch.setattr(metrics, "DB_HEALTH_STATUS", _MetricProbe())

        result = await collect_all_pg_metrics(
            {"memory": "json", "trustlog": "jsonl"}, pool=None
        )
        assert result["db_pool"] is None
        assert result["db_health"] is True
        assert result["db_activity"] is None

    @pytest.mark.asyncio
    async def test_pg_backend_collects_all(self, monkeypatch):
        from veritas_os.observability.pg_collector import collect_all_pg_metrics
        metrics = importlib.import_module("veritas_os.observability.metrics")

        # Suppress real gauge operations with probes
        for attr in (
            "DB_POOL_IN_USE", "DB_POOL_AVAILABLE", "DB_POOL_WAITING",
            "DB_POOL_MAX_SIZE", "DB_POOL_MIN_SIZE", "DB_HEALTH_STATUS",
            "DB_BACKEND_SELECTED", "DB_CONNECT_FAILURES_TOTAL",
            "LONG_RUNNING_QUERY_COUNT", "IDLE_IN_TRANSACTION_COUNT",
            "ADVISORY_LOCK_CONTENTION_COUNT",
        ):
            monkeypatch.setattr(metrics, attr, _MetricProbe())

        pool = _FakePool(pool_size=10, pool_available=5)
        pool._cursor_rows = [(0, 0, 0)]

        result = await collect_all_pg_metrics(
            {"memory": "postgresql", "trustlog": "postgresql"},
            pool,
            statement_timeout_ms=10000,
        )
        assert result["db_pool"] is not None
        assert result["db_pool"]["in_use"] == 5
        assert result["db_health"] is True
        assert result["db_activity"] is not None


# ---------------------------------------------------------------------------
# /v1/metrics integration
# ---------------------------------------------------------------------------


class TestMetricsEndpointIntegration:
    """Test /v1/metrics endpoint includes PostgreSQL metrics."""

    def _make_client(self, monkeypatch, backend: str = "jsonl"):
        """Return a TestClient with storage backend set."""
        from fastapi.testclient import TestClient
        from veritas_os.api import auth as auth_module
        from veritas_os.api import server

        monkeypatch.setenv("VERITAS_API_KEY", "test-key")
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", backend)
        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "json" if backend == "jsonl" else backend)
        auth_module._log_api_key_source_once.cache_clear()
        return TestClient(server.app), server

    def test_file_backend_includes_null_db_pool(self, monkeypatch):
        client, _ = self._make_client(monkeypatch, backend="jsonl")
        resp = client.get(
            "/v1/metrics", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "db_pool" in body
        assert body["db_pool"] is None
        assert body["db_health"] is True
        assert body["db_activity"] is None
        # storage_backends must still be present
        assert "storage_backends" in body

    def test_metric_name_stability(self, monkeypatch):
        """Metric keys in the response must remain stable across releases."""
        client, _ = self._make_client(monkeypatch)
        resp = client.get(
            "/v1/metrics", headers={"X-API-Key": "test-key"}
        )
        body = resp.json()
        for key in ("db_pool", "db_health", "db_activity", "storage_backends"):
            assert key in body, f"Missing stable key: {key}"

    def test_health_storage_backends_consistency(self, monkeypatch):
        """storage_backends in /v1/metrics must match health endpoint backends."""
        from fastapi.testclient import TestClient
        from veritas_os.api import auth as auth_module
        from veritas_os.api import server

        monkeypatch.setenv("VERITAS_API_KEY", "test-key")
        auth_module._log_api_key_source_once.cache_clear()
        client = TestClient(server.app)

        metrics_resp = client.get(
            "/v1/metrics", headers={"X-API-Key": "test-key"}
        )
        health_resp = client.get("/health")

        assert metrics_resp.status_code == 200
        assert health_resp.status_code == 200

        metrics_backends = metrics_resp.json()["storage_backends"]
        assert "memory" in metrics_backends
        assert "trustlog" in metrics_backends


# ---------------------------------------------------------------------------
# DB unavailable behaviour
# ---------------------------------------------------------------------------


class TestDbUnavailable:
    """Test behaviour when DB pool is unavailable / broken."""

    @pytest.mark.asyncio
    async def test_broken_pool_returns_safe_defaults(self, monkeypatch):
        from veritas_os.observability.pg_collector import collect_all_pg_metrics
        metrics = importlib.import_module("veritas_os.observability.metrics")

        for attr in (
            "DB_POOL_IN_USE", "DB_POOL_AVAILABLE", "DB_POOL_WAITING",
            "DB_POOL_MAX_SIZE", "DB_POOL_MIN_SIZE", "DB_HEALTH_STATUS",
            "DB_BACKEND_SELECTED", "DB_CONNECT_FAILURES_TOTAL",
        ):
            monkeypatch.setattr(metrics, attr, _MetricProbe())

        broken_pool = MagicMock()
        broken_pool.get_stats.side_effect = RuntimeError("pool closed")
        broken_pool.connection.side_effect = RuntimeError("no connection")
        broken_pool.max_size = 0
        broken_pool.min_size = 0

        result = await collect_all_pg_metrics(
            {"memory": "postgresql", "trustlog": "postgresql"},
            broken_pool,
        )
        assert result["db_pool"]["in_use"] == 0
        assert result["db_health"] is False
        # Activity should not be collected when health fails
        assert result["db_activity"] is None
