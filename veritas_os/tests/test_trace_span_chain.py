"""Tests for observability tracing span-chain helpers and hooks."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from veritas_os.api import auth
from veritas_os.api import routes_governance
from veritas_os.api.rbac import Permission, Role
from veritas_os.observability import tracing
from veritas_os.policy.bind_artifacts import FinalOutcome


def test_tracing_noop_without_opentelemetry(monkeypatch):
    monkeypatch.setattr(tracing, "otel_trace", None)
    with tracing.start_span("noop.span", attributes={"trace_id": "abc"}):
        tracing.set_span_attribute("k", "v")
        tracing.add_span_event("evt", attributes={"a": 1})


def test_trace_step_handles_exception_and_reraises(monkeypatch):
    events = []

    def _capture(name, attributes=None):
        events.append((name, attributes))

    monkeypatch.setattr(tracing, "add_span_event", _capture)

    with pytest.raises(ValueError):
        with tracing.trace_step("test.step"):
            raise ValueError("boom")

    assert any(name == "step.exception" for name, _ in events)


def test_governance_put_span_chain_happy_path(monkeypatch):
    steps = []

    class _Step:
        def __init__(self, name, attributes=None):
            self.name = name

        def __enter__(self):
            steps.append(self.name)

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    monkeypatch.setattr(routes_governance, "trace_step", lambda name, attributes=None: _Step(name, attributes))
    monkeypatch.setattr(routes_governance, "set_span_attribute", lambda *a, **k: None)
    monkeypatch.setattr(routes_governance, "add_span_event", lambda *a, **k: None)

    class _Receipt:
        def to_dict(self):
            return {"final_outcome": FinalOutcome.COMMITTED.value, "bind_receipt_id": "br-1"}

    monkeypatch.setattr(routes_governance, "update_governance_policy_with_bind_boundary", lambda **k: _Receipt())

    class _Srv:
        def enforce_four_eyes_approval(self, body):
            return None

        def get_policy(self):
            return {"updated_at": "x", "updated_by": "api"}

        def update_policy(self, patch):
            return patch

        def _publish_event(self, *_a, **_k):
            return None

    monkeypatch.setattr(routes_governance, "_get_server", lambda: _Srv())
    monkeypatch.setattr(routes_governance, "_emit_governance_change_alert", lambda **k: None)

    resp = routes_governance.governance_put({"updated_by": "alice", "approvals": [{}, {}]})
    assert resp["ok"] is True
    assert "governance.policy_update.request" in steps
    assert "governance.approval.validate" in steps
    assert "governance.bind_boundary.evaluate" in steps


def test_governance_put_approval_failure_adds_event(monkeypatch):
    events = []
    monkeypatch.setattr(routes_governance, "trace_step", lambda n, attributes=None: tracing.trace_step(n, attributes))
    monkeypatch.setattr(routes_governance, "add_span_event", lambda name, attributes=None: events.append((name, attributes)))

    class _Srv:
        def enforce_four_eyes_approval(self, _body):
            raise PermissionError("approval missing")

    monkeypatch.setattr(routes_governance, "_get_server", lambda: _Srv())
    resp = routes_governance.governance_put({})
    assert resp.status_code == 403
    assert any(name == "governance.approval.failed" for name, _ in events)


def test_rbac_denial_adds_span_event(monkeypatch):
    captured = []
    monkeypatch.setattr(auth, "resolve_role_for_key", lambda _key: Role.auditor)
    monkeypatch.setattr(auth, "append_signed_decision", lambda payload: None)
    monkeypatch.setattr(auth, "add_span_event", lambda name, attributes=None: captured.append((name, attributes)))
    auth._rbac_denial_dedupe_cache.clear()

    checker = auth.require_permission(Permission.decide)
    request = SimpleNamespace(url=SimpleNamespace(path="/v1/decide"), method="POST", state=SimpleNamespace(trace_id="trace-1"))

    with pytest.raises(Exception):
        checker(request=request, x_api_key="valid-key")

    assert captured
    assert captured[0][0] == "rbac.denied"
    assert "token" not in str(captured[0][1]).lower()
