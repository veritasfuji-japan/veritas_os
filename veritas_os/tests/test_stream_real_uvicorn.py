"""Real loopback HTTP/WebSocket transport checks after synthetic startup readiness.

The fixture does not validate strict startup dependencies, TLS, or other hosts.
A dedicated CI job requires the optional WebSocket transport and forbids skips.
"""

from contextlib import contextmanager
import importlib.util
import json
import os
import socket
import threading
import time

import httpx
import pytest
import uvicorn

from veritas_os.api import server
from veritas_os.api.sse_hub import SSEEventHub

KEY = "real-stream-synthetic-test"
REPLACEMENT = "real-stream-replacement-test"


def _wait_subscribers(hub, expected):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        with hub._lock:
            count = len(hub._subscribers)
        if count == expected:
            return
        time.sleep(0.01)
    pytest.fail(f"subscriber count remained {count}, expected {expected}")


def _ws_connect(base, key=KEY):
    from websockets.sync.client import connect

    return connect(
        base.replace("http://", "ws://") + "/v1/ws/trustlog",
        additional_headers={"X-API-Key": key}, proxy=None,
        open_timeout=3, close_timeout=1, ping_interval=None,
    )


@contextmanager
def _stream(base, transport, key=KEY):
    if transport == "websocket":
        with _ws_connect(base, key) as connection:
            yield connection, lambda: json.loads(connection.recv(timeout=3))
    else:
        with httpx.Client(timeout=3, trust_env=False) as client:
            with client.stream("GET", base + "/v1/events", headers={"X-API-Key": key}) as response:
                assert response.status_code == 200
                lines = response.iter_lines()
                assert next(lines) == ": connected"

                def receive():
                    for line in lines:
                        if line.startswith("data: "):
                            return json.loads(line[6:])
                    return None

                yield response, receive


@pytest.fixture
def live_stream_server(monkeypatch):
    if importlib.util.find_spec("websockets") is None:
        if os.getenv("VERITAS_REQUIRE_STREAM_SOCKET_TESTS") == "1":
            pytest.fail("dedicated transport checks require websockets")
        pytest.skip("optional WebSocket transport; required by dedicated CI")
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.delenv("VERITAS_POSTURE", raising=False)
    monkeypatch.setenv("VERITAS_API_KEY", KEY)
    monkeypatch.delenv("VERITAS_API_KEYS", raising=False)
    # This is a post-startup transport fixture, not proof of security initialization.
    monkeypatch.setattr(server.app.state, "security_startup_complete", True, raising=False)
    monkeypatch.setattr(server.app.state, "security_startup_pid", os.getpid(), raising=False)
    hub = SSEEventHub(timestamp_factory=lambda: "test", max_subscribers=2)
    monkeypatch.setattr(server, "_event_hub", hub)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    port = listener.getsockname()[1]
    config = uvicorn.Config(
        server.app, host="127.0.0.1", port=port, lifespan="off", ws="websockets",
        log_level="critical", access_log=False, timeout_graceful_shutdown=2,
    )
    instance = uvicorn.Server(config)
    thread = threading.Thread(target=instance.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not instance.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert instance.started, "Uvicorn did not start"
        yield f"http://127.0.0.1:{port}", hub
    finally:
        instance.should_exit = True
        thread.join(timeout=5)
        if thread.is_alive():
            instance.force_exit = True
            thread.join(timeout=3)
        listener.close()
        assert not thread.is_alive(), "Uvicorn thread survived cleanup"
        _wait_subscribers(hub, 0)


@pytest.mark.parametrize("transport", ["sse", "websocket"])
def test_real_socket_disconnect_cleanup(live_stream_server, transport):
    base, hub = live_stream_server
    with _stream(base, transport) as (_, receive):
        _wait_subscribers(hub, 1)
        event = hub.publish("trustlog.appended", {"test": "before-disconnect"})
        assert receive() == event
    _wait_subscribers(hub, 0)


@pytest.mark.parametrize("transport", ["sse", "websocket"])
def test_real_socket_key_rotation(live_stream_server, monkeypatch, transport):
    from websockets.exceptions import ConnectionClosedError

    base, hub = live_stream_server
    with _stream(base, transport) as (connection, receive):
        event = hub.publish("trustlog.appended", {"test": "before-rotation"})
        assert receive() == event
        monkeypatch.setenv("VERITAS_API_KEY", REPLACEMENT)
        _wait_subscribers(hub, 0)
        hub.publish("trustlog.appended", {"test": "after-rotation"})
        if transport == "websocket":
            with pytest.raises(ConnectionClosedError) as caught:
                connection.recv(timeout=3)
            assert caught.value.rcvd.code == 1008
            assert caught.value.rcvd.reason == "api_key_no_longer_valid"
        else:
            assert receive() is None
    with _stream(base, transport, REPLACEMENT) as (_, receive):
        assert receive()["payload"]["test"] in {"before-rotation", "after-rotation"}
    _wait_subscribers(hub, 0)


def test_real_socket_shared_capacity_and_reuse(live_stream_server):
    from websockets.exceptions import InvalidStatus

    base, hub = live_stream_server
    with _stream(base, "sse"), _stream(base, "websocket"):
        _wait_subscribers(hub, 2)
        with httpx.Client(timeout=3, trust_env=False) as client:
            response = client.get(base + "/v1/events", headers={"X-API-Key": KEY})
            assert response.status_code == 503
            assert response.json()["detail"] == "Event stream capacity reached"
        with pytest.raises(InvalidStatus) as caught:
            _ws_connect(base)
        # A pre-accept ASGI close is an HTTP denial, not an on-wire WS close frame.
        assert caught.value.response.status_code == 403
        _wait_subscribers(hub, 2)
    _wait_subscribers(hub, 0)
    with _stream(base, "websocket"):
        _wait_subscribers(hub, 1)
    _wait_subscribers(hub, 0)


@pytest.mark.parametrize("transport", ["sse", "websocket"])
def test_real_socket_invalid_credentials(live_stream_server, transport):
    from websockets.exceptions import InvalidStatus

    base, hub = live_stream_server
    if transport == "sse":
        with httpx.Client(timeout=3, trust_env=False) as client:
            assert client.get(base + "/v1/events", headers={"X-API-Key": "invalid"}).status_code == 401
    else:
        with pytest.raises(InvalidStatus) as caught:
            _ws_connect(base, "invalid")
        assert caught.value.response.status_code == 403
    _wait_subscribers(hub, 0)


def test_real_socket_incomplete_startup_refused(live_stream_server, monkeypatch):
    from websockets.exceptions import InvalidStatus

    base, hub = live_stream_server
    monkeypatch.setattr(server.app.state, "security_startup_complete", False)
    with httpx.Client(timeout=3, trust_env=False) as client:
        assert client.get(base + "/v1/events", headers={"X-API-Key": KEY}).status_code == 503
    with pytest.raises(InvalidStatus) as caught:
        _ws_connect(base)
    assert caught.value.response.status_code == 403
    _wait_subscribers(hub, 0)
