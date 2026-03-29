"""Unit tests for observability metric recording helpers."""
from __future__ import annotations

import importlib
import sys
from typing import Any

import pytest
from fastapi.testclient import TestClient

from veritas_os.api import auth as auth_module
from veritas_os.api import routes_memory
from veritas_os.api import server


@pytest.fixture(autouse=True)
def _restore_server_pipeline_state():
    """Restore global lazy pipeline state after each test in this module."""
    original = server._pipeline_state
    try:
        yield
    finally:
        server._pipeline_state = original


class _MetricProbe:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def labels(self, **labels: Any) -> "_MetricProbe":
        self.calls.append({"labels": labels})
        return self

    def inc(self, amount: float = 1.0) -> None:
        self.calls.append({"inc": amount})

    def observe(self, value: float) -> None:
        self.calls.append({"observe": value})

    def set(self, value: float) -> None:
        self.calls.append({"set": value})


def test_record_decide_and_gauge_helpers(monkeypatch):
    metrics = importlib.import_module("veritas_os.observability.metrics")
    decide_total = _MetricProbe()
    decide_duration = _MetricProbe()
    telos = _MetricProbe()
    degraded = _MetricProbe()

    monkeypatch.setattr(metrics, "VERITAS_DECIDE_TOTAL", decide_total)
    monkeypatch.setattr(metrics, "VERITAS_DECIDE_DURATION_SECONDS", decide_duration)
    monkeypatch.setattr(metrics, "VERITAS_TELOS_SCORE", telos)
    monkeypatch.setattr(metrics, "VERITAS_DEGRADED_SUBSYSTEMS", degraded)

    metrics.record_decide(status="allow", mode="fast", intent="qa", duration_seconds=0.25)
    metrics.set_telos_score(user_id="u-1", score=0.87)
    metrics.set_degraded_subsystems(2)

    assert any(call.get("labels") == {"status": "allow", "mode": "fast", "intent": "qa"} for call in decide_total.calls)
    assert any(call.get("observe") == 0.25 for call in decide_duration.calls)
    assert any(call.get("labels") == {"user_id": "u-1"} for call in telos.calls)
    assert any(call.get("set") == 2.0 for call in degraded.calls)


def test_fuji_and_memory_metrics(monkeypatch):
    metrics = importlib.import_module("veritas_os.observability.metrics")
    fuji_decisions = _MetricProbe()
    fuji_violations = _MetricProbe()
    mem_ops = _MetricProbe()

    monkeypatch.setattr(metrics, "VERITAS_FUJI_DECISIONS_TOTAL", fuji_decisions)
    monkeypatch.setattr(metrics, "VERITAS_FUJI_VIOLATIONS_TOTAL", fuji_violations)
    monkeypatch.setattr(metrics, "VERITAS_MEMORY_OPERATIONS_TOTAL", mem_ops)

    metrics.record_fuji_decision("deny")
    metrics.record_fuji_violations(["pii", "policy"])
    metrics.record_memory_operation("search", "semantic")

    assert any(call.get("labels") == {"decision_status": "deny"} for call in fuji_decisions.calls)
    assert any(call.get("labels") == {"violation_type": "pii"} for call in fuji_violations.calls)
    assert any(call.get("labels") == {"operation": "search", "kind": "semantic"} for call in mem_ops.calls)


def test_noop_mode_without_prometheus_client(monkeypatch):
    monkeypatch.setitem(sys.modules, "prometheus_client", None)
    metrics = importlib.reload(importlib.import_module("veritas_os.observability.metrics"))

    # Must not raise even when prometheus_client is missing.
    metrics.record_decide(status="allow", mode="normal", intent="unknown", duration_seconds=0.01)
    metrics.record_auth_rejection("api_key_invalid")
    metrics.observe_pipeline_stage_duration("kernel_execute", 0.05)


def test_decide_unavailable_resets_stale_pipeline_state(monkeypatch):
    """Unavailable decide path should reset stale lazy state for next requests."""
    monkeypatch.setenv("VERITAS_API_KEY", "test-key")
    auth_module._log_api_key_source_once.cache_clear()
    monkeypatch.setattr(
        server,
        "_pipeline_state",
        server._LazyState(obj=None, err="boom", attempted=True),
    )
    client = TestClient(server.app)

    response = client.post(
        "/v1/decide",
        headers={"X-API-Key": "test-key"},
        json={"query": "reset check"},
    )

    assert response.status_code == 503
    assert server._pipeline_state.err is None
    assert server._pipeline_state.attempted is False


def test_health_recovers_pipeline_boom_sentinel(monkeypatch):
    """Health endpoint should recover from the temporary pipeline boom sentinel."""
    monkeypatch.setattr(
        server,
        "_pipeline_state",
        server._LazyState(obj=None, err="boom", attempted=True),
    )
    client = TestClient(server.app)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["pipeline"] == "ok"


def test_health_keeps_forced_pipeline_unavailable(monkeypatch):
    """Health endpoint must preserve explicit forced-unavailable pipeline states."""
    monkeypatch.setattr(
        server,
        "_pipeline_state",
        server._LazyState(obj=None, err="forced", attempted=True),
    )
    client = TestClient(server.app)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["pipeline"] == "unavailable"


def test_memory_entry_observer_uses_count_only(monkeypatch):
    """Memory entry gauge observer must not trigger extra search calls."""
    called = {"count": 0, "search": 0}

    class _Store:
        @staticmethod
        def search(**_: Any):
            called["search"] += 1
            return []

    monkeypatch.setattr(
        routes_memory,
        "set_memory_store_entries",
        lambda user_id, entries: None,
    )
    routes_memory._observe_memory_store_entries(_Store(), "u-1")

    assert called["count"] == 0
    assert called["search"] == 0
