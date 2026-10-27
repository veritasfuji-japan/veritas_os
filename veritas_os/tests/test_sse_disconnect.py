"""SSE teardown must release subscriptions without leaving blocked readers."""

import asyncio
import threading

import pytest
from starlette.requests import Request

from veritas_os.api import routes_system, server
from veritas_os.api.sse_hub import SSEEventHub


@pytest.fixture(autouse=True)
def _direct_sse_credentials(monkeypatch):
    """Direct generator/response cases also carry a currently valid stream key."""
    monkeypatch.setenv("VERITAS_API_KEY", "direct-sse-stream-test")
    monkeypatch.delenv("VERITAS_API_KEYS", raising=False)


async def test_sse_cancellation_leaves_no_blocked_reader(monkeypatch):
    hub = SSEEventHub(timestamp_factory=lambda: "test")
    subscriber = hub.register()
    monkeypatch.setattr(hub, "register", lambda: subscriber)
    monkeypatch.setattr(server, "_event_hub", hub)
    active = threading.Event()
    original_get = subscriber.get

    def tracked_get(*args, **kwargs):
        active.set()
        try:
            return original_get(*args, **kwargs)
        finally:
            active.clear()

    monkeypatch.setattr(subscriber, "get", tracked_get)
    request = Request({"type": "http", "headers": [(b"x-api-key", b"direct-sse-stream-test")]})
    monkeypatch.setattr(request, "is_disconnected", lambda: asyncio.sleep(0, result=False))
    response = await routes_system.events(request, heartbeat_sec=5)
    stream = response.body_iterator
    assert await anext(stream) == ": connected\n\n"
    pending = asyncio.create_task(anext(stream))
    try:
        await asyncio.sleep(0.05)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert not hub._subscribers
        assert not active.is_set(), "SSE queue reader remains blocked after cancellation"
    finally:
        subscriber.put_nowait({"type": "test.cleanup"})
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await stream.aclose()


@pytest.mark.parametrize("spec_version", ["2.0", "2.4"])
@pytest.mark.parametrize("publish_event", [False, True])
@pytest.mark.parametrize("termination", ["disconnect", "cancel"])
async def test_mounted_sse_releases_subscription(monkeypatch, publish_event, termination, spec_version):
    import os

    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.delenv("VERITAS_POSTURE", raising=False)
    monkeypatch.setenv("VERITAS_API_KEY", "sse-disconnect-test")
    monkeypatch.delenv("VERITAS_API_KEYS", raising=False)
    monkeypatch.setattr(server.app.state, "security_startup_complete", True, raising=False)
    monkeypatch.setattr(server.app.state, "security_startup_pid", os.getpid(), raising=False)
    hub = SSEEventHub(timestamp_factory=lambda: "test")
    monkeypatch.setattr(server, "_event_hub", hub)
    incoming = asyncio.Queue()
    connected = asyncio.Event()
    delivered = asyncio.Event()

    async def send(message):
        body = message.get("body", b"")
        if b": connected" in body:
            connected.set()
        if b"event: test.event" in body:
            delivered.set()

    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": spec_version},
        "scheme": "http", "method": "GET", "http_version": "1.1", "root_path": "",
        "path": "/v1/events", "raw_path": b"/v1/events",
        "query_string": b"heartbeat_sec=5", "headers": [(b"x-api-key", b"sse-disconnect-test")],
        "client": ("127.0.0.1", 1234), "server": ("testserver", 80), "state": {},
    }
    await incoming.put({"type": "http.request", "body": b"", "more_body": False})
    task = asyncio.create_task(server.app(scope, incoming.get, send))
    try:
        await asyncio.wait_for(connected.wait(), timeout=2)
        if publish_event:
            hub.publish("test.event", {"test": True})
            await asyncio.wait_for(delivered.wait(), timeout=2)
        if termination == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(task), timeout=1)
        else:
            await incoming.put({"type": "http.disconnect"})
            await asyncio.wait_for(asyncio.shield(task), timeout=1)
        assert not hub._subscribers
    finally:
        hub.publish("test.cleanup", {})
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_sse_event_heartbeat_and_observed_disconnect(monkeypatch):
    hub = SSEEventHub(timestamp_factory=lambda: "test")
    monkeypatch.setattr(server, "_event_hub", hub)
    request = Request({"type": "http", "headers": [(b"x-api-key", b"direct-sse-stream-test")]})
    disconnected = False

    async def is_disconnected():
        return disconnected

    monkeypatch.setattr(request, "is_disconnected", is_disconnected)
    # A short interval isolates generator behavior; the HTTP route still enforces 5..60.
    response = await routes_system.events(request, heartbeat_sec=0.01)
    stream = response.body_iterator
    try:
        assert response.media_type == "text/event-stream"
        assert response.headers["X-Accel-Buffering"] == "no"
        assert await anext(stream) == ": connected\n\n"
        event = hub.publish("test.event", {"test": True})
        assert await anext(stream) == server._format_sse_message(event)
        assert (await asyncio.wait_for(anext(stream), timeout=1)).startswith(": heartbeat ")
        disconnected = True
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
        assert not hub._subscribers
    finally:
        await stream.aclose()
