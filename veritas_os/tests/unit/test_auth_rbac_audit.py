from fastapi import HTTPException
from starlette.requests import Request

from veritas_os.api import auth
from veritas_os.api.rbac import Permission, Role
from veritas_os.audit.trustlog_signed import build_trustlog_summary


def _build_request(path: str = "/v1/secure", method: str = "GET", query_string: bytes = b"") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": query_string,
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "server": ("testserver", 80),
    }
    req = Request(scope)
    req.state.trace_id = "trace-001"
    return req


def test_rbac_denial_appends_audit_event(monkeypatch):
    captured = []
    monkeypatch.setattr(auth, "resolve_role_for_key", lambda _key: Role.auditor)
    monkeypatch.setattr(auth, "append_signed_decision", lambda payload: captured.append(payload))
    auth._rbac_denial_dedupe_cache.clear()

    checker = auth.require_permission(Permission.decide)
    request = _build_request(path="/v1/decide", method="POST")

    try:
        checker(request=request, x_api_key="valid-key")
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 403

    assert len(captured) == 1
    event = captured[0]
    assert event["event_type"] == "rbac_denial"
    assert event["reason_code"] == "RBAC_INSUFFICIENT_PERMISSION"
    assert event["actor_role"] == "auditor"
    assert event["requested_permission"] == "decide"
    assert event["endpoint"] == "/v1/decide"
    assert event["method"] == "POST"
    assert event["trace_id"] == "trace-001"


def test_rbac_denial_append_failure_still_returns_403(monkeypatch):
    monkeypatch.setattr(auth, "resolve_role_for_key", lambda _key: Role.auditor)

    def _raise(_payload):
        raise RuntimeError("append failed")

    monkeypatch.setattr(auth, "append_signed_decision", _raise)
    auth._rbac_denial_dedupe_cache.clear()

    checker = auth.require_permission(Permission.decide)
    request = _build_request()
    try:
        checker(request=request, x_api_key="valid-key")
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 403


def test_rbac_denial_payload_excludes_secrets(monkeypatch):
    captured = []
    monkeypatch.setattr(auth, "resolve_role_for_key", lambda _key: Role.auditor)
    monkeypatch.setattr(auth, "append_signed_decision", lambda payload: captured.append(payload))
    auth._rbac_denial_dedupe_cache.clear()

    checker = auth.require_permission(Permission.decide)
    request = _build_request(path="/v1/private", query_string=b"token=secret")
    try:
        checker(request=request, x_api_key="valid-key")
        raise AssertionError("expected HTTPException")
    except HTTPException:
        pass

    event = captured[0]
    dumped = str(event)
    assert "Authorization" not in dumped
    assert "X-API-Key" not in dumped
    assert "Cookie" not in dumped
    assert "token=secret" not in dumped
    assert event["endpoint"] == "/v1/private"


def test_rbac_denial_dedupe(monkeypatch):
    captured = []
    monkeypatch.setattr(auth, "resolve_role_for_key", lambda _key: Role.auditor)
    monkeypatch.setattr(auth, "append_signed_decision", lambda payload: captured.append(payload))
    auth._rbac_denial_dedupe_cache.clear()

    checker = auth.require_permission(Permission.decide)
    req1 = _build_request(path="/v1/decide")
    req1.state.trace_id = "same"
    req2 = _build_request(path="/v1/decide")
    req2.state.trace_id = "same"

    for request in (req1, req2):
        try:
            checker(request=request, x_api_key="valid-key")
        except HTTPException:
            pass

    assert len(captured) == 1

    req3 = _build_request(path="/v1/decide")
    req3.state.trace_id = "different"
    try:
        checker(request=req3, x_api_key="valid-key")
    except HTTPException:
        pass
    assert len(captured) == 2


def test_rbac_denial_helper_handles_none_request(monkeypatch):
    captured = []
    monkeypatch.setattr(auth, "append_signed_decision", lambda payload: captured.append(payload))
    auth._rbac_denial_dedupe_cache.clear()

    auth._append_rbac_denial_audit_event_best_effort(
        request=None,
        role=Role.auditor,
        permission=Permission.decide,
        reason_code="RBAC_INSUFFICIENT_PERMISSION",
    )

    assert len(captured) == 1
    assert captured[0]["endpoint"] == "unknown"
    assert captured[0]["method"] == "unknown"


def test_rbac_denial_fields_survive_signed_summary_compaction():
    payload = {
        "event_type": "rbac_denial",
        "decision_id": "rbac-denial-test",
        "actor_role": "auditor",
        "requested_permission": "decide",
        "endpoint": "/v1/decide",
        "method": "POST",
        "reason_code": "RBAC_INSUFFICIENT_PERMISSION",
        "trace_id": "trace-001",
        "ts": "2026-05-04T00:00:00+00:00",
        "audit_schema_version": "rbac_denial.v1",
        "Authorization": "Bearer secret",
        "X-API-Key": "secret",
        "query_string": "token=secret",
    }

    summary = build_trustlog_summary(payload)

    assert summary["event_type"] == "rbac_denial"
    assert summary["actor_role"] == "auditor"
    assert summary["requested_permission"] == "decide"
    assert summary["endpoint"] == "/v1/decide"
    assert summary["method"] == "POST"
    assert summary["reason_code"] == "RBAC_INSUFFICIENT_PERMISSION"
    assert summary["trace_id"] == "trace-001"
    assert summary["audit_schema_version"] == "rbac_denial.v1"
    assert summary["ts"] == "2026-05-04T00:00:00+00:00"

    assert "Authorization" not in summary
    assert "X-API-Key" not in summary
    assert "query_string" not in summary


def test_normal_decision_summary_allowlist_unchanged():
    payload = {
        "decision_id": "decision-001",
        "decision_status": "approved",
        "chosen_title": "Allow",
        "world_state": {"secret": "should-not-leak"},
    }

    summary = build_trustlog_summary(payload)
    assert summary["decision_id"] == "decision-001"
    assert summary["decision_status"] == "approved"
    assert summary["chosen_title"] == "Allow"
    assert "world_state" not in summary
