"""Mounted event streams must not bypass the permissions of ordinary read APIs."""

import asyncio
from contextlib import asynccontextmanager
import json
import os

import pytest

from veritas_os.api import server
from veritas_os.api.sse_hub import SSEEventHub


KEY = "stream-authorization-test-only"
EVENT_TYPES = (
    "trustlog.appended", "trustlog.debate", "trustlog.critique",
    "decide.completed", "fuji.rejected", "wat.shadow.validation", "compliance.config.updated",
    "compliance.pending_review", "governance.updated", "governance.alert",
    "unclassified.future.event",
)


@asynccontextmanager
async def mounted_stream(
    monkeypatch, transport, role, credential_mode="header", history=False, governance_headers=None,
):
    """Use the actual app with synthetic readiness and an isolated process-local hub."""
    monkeypatch.setenv("VERITAS_ENV", "production" if credential_mode == "header" else "local")
    monkeypatch.delenv("VERITAS_POSTURE", raising=False)
    monkeypatch.setenv("VERITAS_API_KEY", "unrelated-legacy-test-only")
    monkeypatch.setenv("VERITAS_API_KEYS", json.dumps([{"key": KEY, "role": role}]))
    monkeypatch.setenv("VERITAS_GOVERNANCE_ENFORCE_RBAC", "1")
    monkeypatch.setenv("VERITAS_GOVERNANCE_ALLOWED_ROLES", "admin,compliance_owner")
    monkeypatch.setenv("VERITAS_GOVERNANCE_TENANT_ID", "synthetic-tenant")
    for flag in ("SSE", "WS"):
        monkeypatch.setenv(f"VERITAS_ALLOW_{flag}_QUERY_API_KEY", "1")
        monkeypatch.setenv(f"VERITAS_ACK_{flag}_QUERY_API_KEY_RISK", "1")
    monkeypatch.setattr(server.app.state, "security_startup_complete", True, raising=False)
    monkeypatch.setattr(server.app.state, "security_startup_pid", os.getpid(), raising=False)
    hub = SSEEventHub(timestamp_factory=lambda: "test")
    monkeypatch.setattr(server, "_event_hub", hub)
    incoming = asyncio.Queue()
    markers = asyncio.Queue()
    sent = []

    async def send(message):
        sent.append(message)
        payload = message.get("body", b"") if transport == "sse" else message.get("text", "")
        text = payload.decode() if isinstance(payload, bytes) else payload
        for marker in ("initial-barrier", "final-barrier"):
            if marker in text:
                markers.put_nowait(marker)

    def publish_batch():
        for event_type in EVENT_TYPES:
            hub.publish(event_type, {"marker": f"payload-{event_type}"})
        hub.publish("trustlog.appended", {"marker": "final-barrier"})

    is_ws = transport == "websocket"
    path = "/v1/ws/trustlog" if is_ws else "/v1/events"
    headers = list(governance_headers) if governance_headers is not None else [
        (b"x-role", b"admin"), (b"x-tenant-id", b"synthetic-tenant"),
    ]
    if credential_mode == "header":
        headers.append((b"x-api-key", KEY.encode()))
    scope = {
        "type": "websocket" if is_ws else "http",
        "asgi": {"version": "3.0", "spec_version": "2.0"},
        "scheme": "ws" if is_ws else "http", "method": "GET", "http_version": "1.1",
        "root_path": "", "path": path, "raw_path": path.encode(),
        "query_string": f"api_key={KEY}".encode() if credential_mode == "query" else b"",
        "headers": headers, "subprotocols": [], "state": {},
        "client": ("127.0.0.1", 1234), "server": ("testserver", 80),
    }
    await incoming.put({"type": "websocket.connect"} if is_ws else {
        "type": "http.request", "body": b"", "more_body": False,
    })
    if history:
        publish_batch()
    else:
        hub.publish("trustlog.appended", {"marker": "initial-barrier"})
    task = asyncio.create_task(server.app(scope, incoming.get, send))
    try:
        marker = await asyncio.wait_for(markers.get(), timeout=2)
        assert marker == ("final-barrier" if history else "initial-barrier")
        yield hub, sent, markers, publish_batch, scope
    finally:
        await incoming.put({"type": "websocket.disconnect", "code": 1000} if is_ws else {
            "type": "http.disconnect",
        })
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=2)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert not hub._subscribers


@pytest.mark.parametrize("transport", ["sse", "websocket"])
@pytest.mark.parametrize("role", ["admin", "operator", "auditor"])
@pytest.mark.parametrize("credential_mode", ["header", "query"])
@pytest.mark.parametrize("history", [False, True])
async def test_stream_filters_history_and_live_events(monkeypatch, transport, role, credential_mode, history):
    async with mounted_stream(monkeypatch, transport, role, credential_mode, history) as fixture:
        _, sent, markers, publish_batch, _ = fixture
        if not history:
            publish_batch()
            assert await asyncio.wait_for(markers.get(), timeout=2) == "final-barrier"
        expected = {"trustlog.appended", "trustlog.debate", "trustlog.critique"}
        if transport == "sse":
            expected |= {"decide.completed", "fuji.rejected", "wat.shadow.validation"}
            if role != "operator":
                expected |= {"compliance.config.updated", "governance.updated", "governance.alert"}
        if role != "operator":
            expected.add("compliance.pending_review")
        for event_type in EVENT_TYPES:
            assert (f"payload-{event_type}" in repr(sent)) == (event_type in expected), event_type


@pytest.mark.parametrize("transport", ["sse", "websocket"])
@pytest.mark.parametrize("credential_mode", ["header", "query"])
async def test_stream_rechecks_role_before_queued_delivery(monkeypatch, transport, credential_mode):
    async with mounted_stream(monkeypatch, transport, "admin", credential_mode) as fixture:
        _, sent, markers, publish_batch, _ = fixture
        publish_batch()
        # These events are already queued; no await permits delivery before the downgrade.
        monkeypatch.setenv("VERITAS_API_KEYS", json.dumps([{"key": KEY, "role": "operator"}]))
        assert await asyncio.wait_for(markers.get(), timeout=2) == "final-barrier"
        assert "payload-trustlog.appended" in repr(sent)
        assert "payload-compliance.pending_review" not in repr(sent)
        assert "payload-compliance.config.updated" not in repr(sent)
        assert "payload-governance.updated" not in repr(sent)
        assert "payload-governance.alert" not in repr(sent)


@pytest.mark.parametrize("transport", ["sse", "websocket"])
@pytest.mark.parametrize("header_key", [KEY, "invalid-test-only"])
def test_stream_permission_uses_header_before_privileged_query(monkeypatch, transport, header_key):
    from starlette.requests import Request
    from starlette.websockets import WebSocket

    from veritas_os.api.auth import stream_has_permission
    from veritas_os.api.rbac import Permission

    monkeypatch.setenv("VERITAS_API_KEY", "query-admin-test-only")
    monkeypatch.setenv("VERITAS_API_KEYS", json.dumps([{"key": KEY, "role": "operator"}]))
    scope = {
        "type": "websocket" if transport == "websocket" else "http",
        "headers": [(b"x-api-key", header_key.encode()), (b"x-role", b"admin")],
        "query_string": b"api_key=query-admin-test-only",
    }
    async def unexpected_io(*_args):
        raise AssertionError("permission resolution must not perform transport I/O")

    connection = WebSocket(scope, unexpected_io, unexpected_io) if transport == "websocket" else Request(scope)
    assert not stream_has_permission(connection, Permission.compliance_read)


@pytest.mark.parametrize("change", ["missing-role", "wrong-role", "wrong-tenant", "disabled-unacknowledged"])
async def test_sse_governance_events_respect_existing_access_guard(monkeypatch, change):
    headers = [(b"x-tenant-id", b"synthetic-tenant")] if change == "missing-role" else None
    async with mounted_stream(monkeypatch, "sse", "admin", governance_headers=headers) as fixture:
        _, sent, markers, publish_batch, _ = fixture
        if change == "disabled-unacknowledged":
            monkeypatch.setenv("VERITAS_GOVERNANCE_ENFORCE_RBAC", "0")
            monkeypatch.delenv("VERITAS_GOVERNANCE_ALLOW_RBAC_BYPASS", raising=False)
        elif change == "wrong-role":
            monkeypatch.setenv("VERITAS_GOVERNANCE_ALLOWED_ROLES", "compliance_owner")
        elif change == "wrong-tenant":
            monkeypatch.setenv("VERITAS_GOVERNANCE_TENANT_ID", "another-tenant")
        publish_batch()
        assert await asyncio.wait_for(markers.get(), timeout=2) == "final-barrier"
        assert "payload-trustlog.appended" in repr(sent)
        assert "payload-governance.updated" not in repr(sent)
        assert "payload-governance.alert" not in repr(sent)
