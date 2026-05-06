"""Tests for observability tracing span-chain helpers and hooks."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from veritas_os.api import auth
from veritas_os.api import routes_governance
from veritas_os.api.rbac import Permission, Role
from veritas_os.observability import tracing
from veritas_os.policy.bind_artifacts import FinalOutcome

EXPECTED_GOVERNANCE_TRACE_SPANS = (
    "http.request",
    "governance.policy_update.request",
    "governance.approval.validate",
    "governance.bind_boundary.evaluate",
    "bind.boundary.evaluate.start",
    "bind.boundary.evaluate.end",
    "governance.policy.persist",
    "governance.policy_update.response",
)
EXPECTED_RBAC_TRACE_EVENTS = (
    "rbac.denied",
    "rbac.denial.audit_append",
)

FORBIDDEN_TRACE_ATTRIBUTE_NAMES = {
    "authorization",
    "x-api-key",
    "cookie",
    "token",
    "secret",
    "password",
    "raw request body",
    "query_string",
    "personally identifying free-text payloads",
    "approval signature raw secret beyond existing v1 token string semantics",
    "medical/financial record contents",
}


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


def test_start_span_attaches_attributes_to_activated_span(monkeypatch):
    class _FakeSpan:
        def __init__(self):
            self.attributes = {}

        def set_attribute(self, key, value):
            self.attributes[key] = value

    class _FakeContextManager:
        def __init__(self, span):
            self._span = span

        def __enter__(self):
            return self._span

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    class _FakeTracer:
        def __init__(self, span):
            self._span = span

        def start_as_current_span(self, _name):
            return _FakeContextManager(self._span)

    stale_span = _FakeSpan()
    active_span = _FakeSpan()
    monkeypatch.setattr(tracing, "get_tracer", lambda: _FakeTracer(active_span))
    monkeypatch.setattr(tracing, "_active_span", lambda: stale_span)

    with tracing.start_span("x", attributes={"a": "b"}):
        pass

    assert active_span.attributes == {"a": "b"}
    assert stale_span.attributes == {}


def test_start_span_attribute_failure_does_not_break_context(monkeypatch):
    events = []

    class _FlakySpan:
        def set_attribute(self, _key, _value):
            raise RuntimeError("cannot set")

        def add_event(self, name, attributes=None):
            events.append((name, attributes))

    class _FakeContextManager:
        def __init__(self, span):
            self._span = span

        def __enter__(self):
            return self._span

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    class _FakeTracer:
        def __init__(self, span):
            self._span = span

        def start_as_current_span(self, _name):
            return _FakeContextManager(self._span)

    monkeypatch.setattr(tracing, "get_tracer", lambda: _FakeTracer(_FlakySpan()))

    with tracing.start_span("x", attributes={"a": "b"}):
        tracing.add_span_event("inside")


def test_trace_step_exception_marks_active_span(monkeypatch):
    class _FakeSpan:
        def __init__(self):
            self.attributes = {}
            self.events = []

        def set_attribute(self, key, value):
            self.attributes[key] = value

        def add_event(self, name, attributes=None):
            self.events.append((name, attributes or {}))

    class _FakeContextManager:
        def __init__(self, trace_api, span):
            self._trace_api = trace_api
            self._span = span

        def __enter__(self):
            self._trace_api._current = self._span
            return self._span

        def __exit__(self, exc_type, exc_val, exc_tb):
            self._trace_api._current = self._trace_api._stale
            return False

    class _FakeTracer:
        def __init__(self, trace_api):
            self._trace_api = trace_api

        def start_as_current_span(self, _name):
            span = _FakeSpan()
            self._trace_api._started.append(span)
            return _FakeContextManager(self._trace_api, span)

    class _FakeTraceAPI:
        def __init__(self):
            self._stale = _FakeSpan()
            self._current = self._stale
            self._started = []

        def get_tracer(self, _name):
            return _FakeTracer(self)

        def get_current_span(self):
            return self._current

    fake_api = _FakeTraceAPI()
    monkeypatch.setattr(tracing, "otel_trace", fake_api)

    with pytest.raises(ValueError):
        with tracing.trace_step("test.step", attributes={"k": "v"}):
            raise ValueError("boom")

    step_span = fake_api._started[0]
    assert step_span.attributes["k"] == "v"
    assert step_span.attributes["error"] is True
    assert any(name == "step.exception" for name, _attrs in step_span.events)


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
    assert "governance.policy.persist" in steps
    assert "governance.policy_update.response" in steps


def test_governance_trace_span_expectation_alignment():
    implemented_steps = {
        "governance.policy_update.request",
        "governance.approval.validate",
        "governance.bind_boundary.evaluate",
        "governance.policy.persist",
        "governance.policy_update.response",
    }
    assert implemented_steps.issubset(set(EXPECTED_GOVERNANCE_TRACE_SPANS))


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
    lowered_keys = {str(key).lower() for key in captured[0][1].keys()}
    assert lowered_keys.isdisjoint(FORBIDDEN_TRACE_ATTRIBUTE_NAMES)


@pytest.mark.parametrize(
    "doc_path",
    (
        "docs/en/operations/governance-trace-span-chain.md",
        "docs/ja/operations/governance-trace-span-chain.md",
    ),
)
def test_trace_docs_include_expected_spans_and_forbidden_attributes(doc_path):
    content = open(doc_path, "r", encoding="utf-8").read()
    for span_name in EXPECTED_GOVERNANCE_TRACE_SPANS:
        assert span_name in content
    for event_name in EXPECTED_RBAC_TRACE_EVENTS:
        assert event_name in content
    assert "audit_append_status = success | failed | deduped" in content
    content_lower = content.lower()
    for forbidden_name in FORBIDDEN_TRACE_ATTRIBUTE_NAMES:
        assert forbidden_name in content_lower
