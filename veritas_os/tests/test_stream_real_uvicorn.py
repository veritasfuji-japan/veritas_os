"""Real loopback HTTP/WebSocket transport checks after synthetic startup readiness.

Thread and independent-interpreter fixtures do not validate strict startup
dependencies, TLS, or other hosts.
A dedicated CI job requires the optional WebSocket transport and forbids skips.
"""

from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
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
        if isinstance(hub, _ProcessHub):
            count = hub.command("status")["subscribers"]
        else:
            with hub._lock:
                count = len(hub._subscribers)
        if count == expected:
            return
        time.sleep(0.01)
    pytest.fail(f"subscriber count remained {count}, expected {expected}")


class _ProcessHub:
    """Parent-side fixture controls; no control route is mounted in the API."""

    def __init__(self, process):
        self.process = process
        self.buffer = b""
        self.sequence = 0
        self.expected_exit_code = None

    def read_reply(self, timeout=10):
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            while time.monotonic() < deadline:
                while b"\n" in self.buffer:
                    line, self.buffer = self.buffer.split(b"\n", 1)
                    if line.startswith(b"STREAM_FIXTURE "):
                        return json.loads(line.removeprefix(b"STREAM_FIXTURE "))
                if not selector.select(timeout=0.1):
                    continue
                chunk = os.read(self.process.stdout.fileno(), 65536)
                if not chunk:
                    raise RuntimeError("fixture child exited before replying")
                self.buffer += chunk
        raise TimeoutError("fixture child did not reply")

    def command(self, action, **fields):
        self.sequence += 1
        self.process.stdin.write((json.dumps({"id": self.sequence, "action": action, **fields}) + "\n").encode())
        self.process.stdin.flush()
        reply = self.read_reply()
        assert reply["id"] == self.sequence
        assert reply["pid"] == self.process.pid
        return reply

    def stop(self, mode):
        if mode == "graceful":
            self.command("shutdown")
            assert self.process.wait(timeout=5) == 0
        else:
            assert mode == "crash"
            self.process.kill()
            assert self.process.wait(timeout=3) < 0
        self.expected_exit_code = self.process.returncode

    def publish(self, event_type, payload):
        assert event_type == "trustlog.appended"
        return self.command("publish", label=payload["test"])["event"]


@contextmanager
def _process_server(tmp_path, record_property, *, port=0, key_generation="original"):
    env = dict(os.environ)
    root = Path(__file__).resolve().parents[2]
    env["PYTHONPATH"] = str(root)
    tmp_path.mkdir(parents=True, exist_ok=True)
    with (tmp_path / "uvicorn-child.log").open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, "-u", "-m", "veritas_os.tests.helpers.stream_process_fixture",
             "--port", str(port), "--key-generation", key_generation],
            cwd=root, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
        )
        hub = _ProcessHub(process)
        try:
            ready = hub.read_reply()
            assert ready["id"] == 0 and ready["ready"] is True
            assert ready["pid"] == process.pid and process.pid != os.getpid()
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            assert ready["tested_sha"] == sha
            hub.tested_sha = ready["tested_sha"]
            record_property("server_pid", process.pid)
            record_property("client_pid", os.getpid())
            record_property("child_tested_sha", ready["tested_sha"])
            yield f"http://127.0.0.1:{ready['port']}", hub
            if hub.expected_exit_code is None:
                _wait_subscribers(hub, 0)
                hub.command("shutdown")
                assert process.wait(timeout=5) == 0
            else:
                assert process.poll() == hub.expected_exit_code
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            process.stdin.close()
            process.stdout.close()


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


def _require_socket_transport():
    if importlib.util.find_spec("websockets") is None:
        if os.getenv("VERITAS_REQUIRE_STREAM_SOCKET_TESTS") == "1":
            pytest.fail("dedicated transport checks require websockets")
        pytest.skip("optional WebSocket transport; required by dedicated CI")


@pytest.fixture(params=["thread", "process"])
def live_stream_server(monkeypatch, request, tmp_path, record_property):
    _require_socket_transport()
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.delenv("VERITAS_POSTURE", raising=False)
    monkeypatch.setenv("VERITAS_API_KEY", KEY)
    monkeypatch.delenv("VERITAS_API_KEYS", raising=False)
    record_property("server_mode", request.param)
    if request.param == "process":
        if os.name != "posix":
            pytest.skip("child stdout selectors require POSIX; dedicated CI uses Linux")
        with _process_server(tmp_path, record_property) as live:
            yield live
        return
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
        if isinstance(hub, _ProcessHub):
            hub.command("rotate")
            assert os.environ["VERITAS_API_KEY"] == KEY
        else:
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
    if isinstance(hub, _ProcessHub):
        hub.command("unready")
    else:
        monkeypatch.setattr(server.app.state, "security_startup_complete", False)
    with httpx.Client(timeout=3, trust_env=False) as client:
        assert client.get(base + "/v1/events", headers={"X-API-Key": KEY}).status_code == 503
    with pytest.raises(InvalidStatus) as caught:
        _ws_connect(base)
    assert caught.value.response.status_code == 403
    _wait_subscribers(hub, 0)


@pytest.mark.parametrize("transport", ["sse", "websocket"])
@pytest.mark.parametrize("stop_mode", ["graceful", "crash"])
def test_real_socket_process_restart(tmp_path, record_property, transport, stop_mode):
    _require_socket_transport()
    if os.name != "posix":
        pytest.skip("subprocess restart transport checks require POSIX")
    from websockets.exceptions import ConnectionClosed, InvalidStatus

    record_property("server_mode", "restart")
    record_property("client_pid", os.getpid())
    record_property("stop_mode", stop_mode)
    with _process_server(tmp_path / "old", lambda *_: None) as (base, old):
        old_pid = old.process.pid
        record_property("old_server_pid", old_pid)
        record_property("old_tested_sha", old.tested_sha)
        port = int(base.rsplit(":", 1)[1])
        record_property("port", port)
        with _stream(base, transport) as (connection, receive):
            event = old.publish("trustlog.appended", {"test": "before-restart"})
            assert receive() == event
            _wait_subscribers(old, 1)
            old.stop(stop_mode)
            assert old.process.poll() is not None
            if transport == "websocket":
                with pytest.raises(ConnectionClosed):
                    connection.recv(timeout=3)
            else:
                try:
                    assert receive() is None
                except (httpx.RemoteProtocolError, httpx.ReadError):
                    # A killed HTTP stream may end without its final chunk.
                    pass
        record_property("old_connection_terminated", True)

    with _process_server(
        tmp_path / "new", lambda *_: None, port=port, key_generation="replacement",
    ) as (new_base, new):
        assert new_base == base
        assert new.process.pid != old_pid
        record_property("new_server_pid", new.process.pid)
        record_property("new_tested_sha", new.tested_sha)
        _wait_subscribers(new, 0)
        if transport == "websocket":
            with pytest.raises(InvalidStatus) as caught:
                _ws_connect(new_base, KEY)
            assert caught.value.response.status_code == 403
        else:
            with httpx.Client(timeout=3, trust_env=False) as client:
                assert client.get(new_base + "/v1/events", headers={"X-API-Key": KEY}).status_code == 401
        with _stream(new_base, transport, REPLACEMENT) as (_, receive):
            event = new.publish("trustlog.appended", {"test": "after-restart"})
            assert receive() == event
            _wait_subscribers(new, 1)
        _wait_subscribers(new, 0)
    record_property("replacement_verified", True)
