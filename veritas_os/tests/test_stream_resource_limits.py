"""Event streams must bound subscribers and release stalled transport sends."""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

import pytest

from veritas_os.api import server, sse_hub
from veritas_os.api.sse_hub import SSEEventHub, SubscriberLimitReached


def test_default_hub_refuses_excess_subscribers():
    hub = SSEEventHub(timestamp_factory=lambda: "test")
    subscribers = []
    try:
        for _ in range(128):
            subscribers.append(hub.register())
        with pytest.raises(RuntimeError, match="subscriber limit"):
            hub.register()
        assert len(hub._subscribers) == 128
        hub.unregister(subscribers.pop())
        subscribers.append(hub.register())
    finally:
        for subscriber in subscribers:
            hub.unregister(subscriber)


@pytest.mark.parametrize("transport,boundary,stall_close", [
    ("sse", "headers", False), ("sse", "body", False),
    ("websocket", "headers", False), ("websocket", "body", False),
    ("websocket", "body", True),
])
async def test_mounted_stalled_stream_releases_subscription(
    monkeypatch, transport, boundary, stall_close,
):
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.delenv("VERITAS_POSTURE", raising=False)
    monkeypatch.setenv("VERITAS_API_KEY", "stream-limit-test")
    monkeypatch.delenv("VERITAS_API_KEYS", raising=False)
    monkeypatch.setattr(server.app.state, "security_startup_complete", True, raising=False)
    monkeypatch.setattr(server.app.state, "security_startup_pid", os.getpid(), raising=False)
    # Production uses a finite send deadline; keep this regression quick.
    monkeypatch.setattr(sse_hub, "STREAM_SEND_TIMEOUT_SEC", 0.02)
    hub = SSEEventHub(timestamp_factory=lambda: "test")
    monkeypatch.setattr(server, "_event_hub", hub)
    hub.publish("trustlog.appended", {"test": True})
    incoming = asyncio.Queue()
    blocked = asyncio.Event()
    released = asyncio.Event()
    closes = []
    is_ws = transport == "websocket"
    path = "/v1/ws/trustlog" if is_ws else "/v1/events"

    async def send(message):
        if message["type"] == "websocket.close":
            closes.append(message)
        targets = {"websocket.accept", "http.response.start"} if boundary == "headers" else {
            "websocket.send", "http.response.body",
        }
        if message["type"] in targets or (stall_close and message["type"] == "websocket.close"):
            blocked.set()
            try:
                await asyncio.Event().wait()
            finally:
                released.set()

    scope = {
        "type": "websocket" if is_ws else "http",
        "asgi": {"version": "3.0", "spec_version": "2.0"},
        "scheme": "ws" if is_ws else "http", "method": "GET", "http_version": "1.1",
        "root_path": "", "path": path, "raw_path": path.encode(), "query_string": b"",
        "headers": [(b"x-api-key", b"stream-limit-test")], "subprotocols": [],
        "client": ("127.0.0.1", 1234), "server": ("testserver", 80), "state": {},
    }
    await incoming.put({"type": "websocket.connect"} if is_ws else {
        "type": "http.request", "body": b"", "more_body": False,
    })
    task = asyncio.create_task(server.app(scope, incoming.get, send))
    try:
        await asyncio.wait_for(blocked.wait(), timeout=2)
        # The route may surface a timeout, but must finish and release its resources.
        done, _ = await asyncio.wait([task], timeout=0.5)
        assert task in done, "stream kept a subscriber during an indefinitely blocked send"
        result = await asyncio.gather(task, return_exceptions=True)
        assert result[0] is None or isinstance(result[0], TimeoutError)
        assert released.is_set()
        assert not hub._subscribers
        if is_ws:
            assert closes[-1]["code"] == 1013
            assert closes[-1]["reason"] == "stream_send_timeout"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def test_subscriber_limit_is_atomic_under_contention():
    hub = SSEEventHub(timestamp_factory=lambda: "test", max_subscribers=4)

    def register():
        try:
            return hub.register()
        except SubscriberLimitReached:
            return None

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: register(), range(32)))
    subscribers = [s for s in results if s is not None]
    assert len(subscribers) == 4
    assert len(hub._subscribers) == 4
    for subscriber in subscribers:
        hub.unregister(subscriber)
    assert not hub._subscribers


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_subscriber_limit_cannot_be_disabled(limit):
    with pytest.raises(ValueError, match="positive integer"):
        SSEEventHub(timestamp_factory=lambda: "test", max_subscribers=limit)


def test_mounted_capacity_refusals_preserve_existing_subscriber(monkeypatch):
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.delenv("VERITAS_POSTURE", raising=False)
    monkeypatch.setenv("VERITAS_API_KEY", "stream-limit-test")
    monkeypatch.delenv("VERITAS_API_KEYS", raising=False)
    monkeypatch.setattr(server.app.state, "security_startup_complete", True, raising=False)
    monkeypatch.setattr(server.app.state, "security_startup_pid", os.getpid(), raising=False)
    hub = SSEEventHub(timestamp_factory=lambda: "test", max_subscribers=1)
    monkeypatch.setattr(server, "_event_hub", hub)
    subscriber = hub.register()
    client = TestClient(server.app)
    try:
        assert client.get("/v1/events").status_code == 401
        response = client.get("/v1/events", headers={"X-API-Key": "stream-limit-test"})
        assert response.status_code == 503
        assert response.json()["detail"] == "Event stream capacity reached"
        with pytest.raises(WebSocketDisconnect) as caught:
            with client.websocket_connect("/v1/ws/trustlog", headers={"X-API-Key": "stream-limit-test"}):
                pytest.fail("over-capacity WebSocket admitted")
        assert caught.value.code == 1013
        assert caught.value.reason == "stream_capacity_reached"
        assert hub._subscribers == {subscriber}
        event = hub.publish("trustlog.appended", {"test": True})
        assert subscriber.get_nowait() == event
    finally:
        hub.unregister(subscriber)


async def test_sse_transport_deadline_does_not_limit_json(monkeypatch):
    from veritas_os.api.middleware import EventStreamSendTimeoutMiddleware

    monkeypatch.setattr(sse_hub, "STREAM_SEND_TIMEOUT_SEC", 0.01)
    started = asyncio.Event()
    release = asyncio.Event()

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})

    async def send(message):
        started.set()
        await release.wait()

    async def receive():
        return {"type": "http.disconnect"}

    task = asyncio.create_task(EventStreamSendTimeoutMiddleware(app)({"type": "http"}, receive, send))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        done, _ = await asyncio.wait([task], timeout=0.04)
        assert not done
        release.set()
        await asyncio.wait_for(task, timeout=1)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
