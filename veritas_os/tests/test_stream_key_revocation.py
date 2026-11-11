"""Existing streams must stop when their key is removed from process configuration."""

import asyncio
import json
import os

import pytest

from veritas_os.api import server
from veritas_os.api.sse_hub import SSEEventHub


@pytest.mark.parametrize("transport", ["sse", "websocket"])
@pytest.mark.parametrize("credential_mode,config_kind", [
    ("header", "single"), ("header", "multi"),
    ("query", "single"), ("query", "multi"), ("query", "query-disabled"),
])
@pytest.mark.parametrize("queued_event", [False, True])
async def test_mounted_stream_key_removal_stops_delivery(
    monkeypatch, transport, config_kind, queued_event, credential_mode,
):
    key = "stream-revocation-test"
    replacement = "stream-replacement-test"
    monkeypatch.setenv("VERITAS_ENV", "production" if credential_mode == "header" else "local")
    flag = "WS" if transport == "websocket" else "SSE"
    monkeypatch.setenv(f"VERITAS_ALLOW_{flag}_QUERY_API_KEY", "1")
    monkeypatch.setenv(f"VERITAS_ACK_{flag}_QUERY_API_KEY_RISK", "1")
    monkeypatch.delenv("VERITAS_POSTURE", raising=False)
    monkeypatch.setenv("VERITAS_API_KEY", replacement if config_kind == "multi" else key)
    monkeypatch.delenv("VERITAS_API_KEYS", raising=False)
    if config_kind == "multi":
        monkeypatch.setenv("VERITAS_API_KEYS", json.dumps([{"key": key, "role": "operator"}]))
    monkeypatch.setattr(server.app.state, "security_startup_complete", True, raising=False)
    monkeypatch.setattr(server.app.state, "security_startup_pid", os.getpid(), raising=False)
    hub = SSEEventHub(timestamp_factory=lambda: "test")
    monkeypatch.setattr(server, "_event_hub", hub)
    incoming = asyncio.Queue()
    first_event = asyncio.Event()
    sent = []

    async def send(message):
        sent.append(message)
        payload = message.get("body", b"") if transport == "sse" else message.get("text", "")
        text = payload.decode() if isinstance(payload, bytes) else payload
        if "before-removal" in text:
            first_event.set()

    is_ws = transport == "websocket"
    path = "/v1/ws/trustlog" if is_ws else "/v1/events"
    scope = {
        "type": "websocket" if is_ws else "http",
        "asgi": {"version": "3.0", "spec_version": "2.0"},
        "scheme": "ws" if is_ws else "http", "method": "GET", "http_version": "1.1",
        "root_path": "", "path": path, "raw_path": path.encode(),
        "query_string": f"api_key={key}".encode() if credential_mode == "query" else b"",
        "headers": [(b"x-api-key", key.encode())] if credential_mode == "header" else [],
        "subprotocols": [],
        "client": ("127.0.0.1", 1234), "server": ("testserver", 80), "state": {},
    }
    await incoming.put({"type": "websocket.connect"} if is_ws else {
        "type": "http.request", "body": b"", "more_body": False,
    })
    hub.publish("trustlog.appended", {"test": "before-removal"})
    task = asyncio.create_task(server.app(scope, incoming.get, send))
    try:
        await asyncio.wait_for(first_event.wait(), timeout=2)
        if config_kind == "single":
            monkeypatch.setenv("VERITAS_API_KEY", replacement)
        elif config_kind == "multi":
            monkeypatch.setenv("VERITAS_API_KEYS", "[]")
        else:
            monkeypatch.delenv(f"VERITAS_ALLOW_{flag}_QUERY_API_KEY")
        if queued_event:
            hub.publish("trustlog.appended", {"test": "after-removal"})
        await asyncio.wait_for(asyncio.shield(task), timeout=1)
        assert not hub._subscribers
        assert "after-removal" not in repr(sent)
        if is_ws:
            close = next(m for m in sent if m["type"] == "websocket.close")
            assert close["code"] == 1008
            assert close["reason"] == "api_key_no_longer_valid"
    finally:
        await incoming.put({"type": "websocket.disconnect", "code": 1000} if is_ws else {
            "type": "http.disconnect",
        })
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
