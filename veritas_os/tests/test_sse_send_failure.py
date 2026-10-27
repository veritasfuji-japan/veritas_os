"""SSE response ownership must cover transport errors at every send boundary."""

import asyncio
import os

import pytest
from starlette.requests import ClientDisconnect, Request

from veritas_os.api import routes_system, server
from veritas_os.api.sse_hub import SSEEventHub


@pytest.fixture(autouse=True)
def _direct_sse_credentials(monkeypatch):
    """Direct generator/response cases also carry a currently valid stream key."""
    monkeypatch.setenv("VERITAS_API_KEY", "direct-sse-stream-test")
    monkeypatch.delenv("VERITAS_API_KEYS", raising=False)


@pytest.mark.parametrize("error_type", [RuntimeError, OSError])
@pytest.mark.parametrize("spec_version", ["2.0", "2.4"])
@pytest.mark.parametrize("boundary", ["headers", "connected", "event", "heartbeat"])
async def test_sse_send_failure_releases_subscription(
    monkeypatch, spec_version, boundary, error_type,
):
    hub = SSEEventHub(timestamp_factory=lambda: "test")
    monkeypatch.setattr(server, "_event_hub", hub)
    request = Request({"type": "http", "headers": [(b"x-api-key", b"direct-sse-stream-test")]})
    monkeypatch.setattr(request, "is_disconnected", lambda: asyncio.sleep(0, result=False))
    # Short direct-call heartbeat isolates response cleanup; HTTP bounds are unchanged.
    response = await routes_system.events(request, heartbeat_sec=0.01)
    if boundary == "event":
        hub.publish("test.event", {"test": True})
    failure = error_type("synthetic SSE send failure")
    failed = False

    async def send(message):
        nonlocal failed
        body = message.get("body", b"")
        if (
            (boundary == "headers" and message["type"] == "http.response.start")
            or (boundary == "connected" and b": connected" in body)
            or (boundary == "event" and b"event: test.event" in body)
            or (boundary == "heartbeat" and b": heartbeat" in body)
        ):
            failed = True
            raise failure

    async def receive():
        await asyncio.Event().wait()

    try:
        expected = ClientDisconnect if error_type is OSError and spec_version == "2.4" else error_type
        with pytest.raises(expected) as caught:
            await asyncio.wait_for(
                response({"type": "http", "asgi": {"spec_version": spec_version}}, receive, send),
                timeout=2,
            )
        if expected is ClientDisconnect:
            assert caught.value.__context__ is failure
        else:
            assert caught.value is failure
        assert failed
        assert not hub._subscribers, "SSE subscriber retained after response send failure"
    finally:
        # Keep the baseline failure from leaking into another case.
        await response.body_iterator.aclose()


@pytest.mark.parametrize("boundary", ["connected", "event"])
async def test_mounted_sse_send_failure_releases_subscription(monkeypatch, boundary):
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.delenv("VERITAS_POSTURE", raising=False)
    monkeypatch.setenv("VERITAS_API_KEY", "sse-send-failure-test")
    monkeypatch.delenv("VERITAS_API_KEYS", raising=False)
    monkeypatch.setattr(server.app.state, "security_startup_complete", True, raising=False)
    monkeypatch.setattr(server.app.state, "security_startup_pid", os.getpid(), raising=False)
    hub = SSEEventHub(timestamp_factory=lambda: "test")
    monkeypatch.setattr(server, "_event_hub", hub)
    hub.publish("test.event", {"test": True})
    incoming = asyncio.Queue()
    failed = False
    failure = RuntimeError("synthetic mounted SSE send failure")

    async def send(message):
        nonlocal failed
        body = message.get("body", b"")
        target = b": connected" if boundary == "connected" else b"event: test.event"
        if target in body:
            failed = True
            raise failure

    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.0"},
        "scheme": "http", "method": "GET", "http_version": "1.1", "root_path": "",
        "path": "/v1/events", "raw_path": b"/v1/events", "query_string": b"",
        "headers": [(b"x-api-key", b"sse-send-failure-test")],
        "client": ("127.0.0.1", 1234), "server": ("testserver", 80), "state": {},
    }
    await incoming.put({"type": "http.request", "body": b"", "more_body": False})
    with pytest.raises(RuntimeError, match="synthetic mounted SSE send failure") as caught:
        await asyncio.wait_for(server.app(scope, incoming.get, send), timeout=2)
    assert caught.value is failure
    assert failed
    assert not hub._subscribers
