"""Exercise authentication and startup admission on the mounted WebSocket route."""

import os
from unittest.mock import Mock

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from veritas_os.api import auth, server


@pytest.fixture
def ws_app(monkeypatch):
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.delenv("VERITAS_POSTURE", raising=False)
    monkeypatch.setenv("VERITAS_API_KEY", "websocket-admission-test")
    monkeypatch.delenv("VERITAS_API_KEYS", raising=False)
    monkeypatch.setattr(server.app.state, "security_startup_complete", True, raising=False)
    monkeypatch.setattr(server.app.state, "security_startup_pid", os.getpid(), raising=False)
    hub = Mock()
    event = {"type": "trustlog.appended", "payload": {"test": True}}
    hub.register.return_value.get_nowait.side_effect = [event, WebSocketDisconnect()]
    monkeypatch.setattr(server, "_event_hub", hub)
    # Clients below intentionally skip lifespan and control admission state here.
    return server.app, hub, event


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "invalid"}])
@pytest.mark.parametrize("complete", [True, False])
def test_mounted_websocket_invalid_credentials_refused(ws_app, monkeypatch, headers, complete):
    app, hub, _ = ws_app
    monkeypatch.setattr(app.state, "security_startup_complete", complete)
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as caught:
        with client.websocket_connect("/v1/ws/trustlog", headers=headers):
            pytest.fail("invalid credentials admitted")
    assert caught.value.code == 1008
    hub.register.assert_not_called()


def test_mounted_websocket_valid_header_streams(ws_app):
    app, hub, event = ws_app
    client = TestClient(app)
    with client.websocket_connect(
        "/v1/ws/trustlog", headers={"X-API-Key": "websocket-admission-test"},
    ) as socket:
        assert socket.receive_json() == event
    hub.register.assert_called_once()
    hub.unregister.assert_called_once_with(hub.register.return_value)


@pytest.mark.parametrize("marker,pid", [(None, None), (False, None), ("true", os.getpid()), (True, 0)])
def test_mounted_websocket_incomplete_startup_refused(ws_app, monkeypatch, marker, pid):
    app, hub, _ = ws_app
    monkeypatch.setattr(app.state, "security_startup_complete", marker)
    monkeypatch.setattr(app.state, "security_startup_pid", pid)
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as caught:
        with client.websocket_connect(
            "/v1/ws/trustlog", headers={"X-API-Key": "websocket-admission-test"},
        ):
            pytest.fail("incomplete startup admitted")
    assert caught.value.code == 1013
    assert caught.value.reason == "security_startup_incomplete"
    hub.register.assert_not_called()


def test_mounted_websocket_query_credentials_blocked_in_production(ws_app, monkeypatch):
    app, hub, _ = ws_app
    monkeypatch.setenv("VERITAS_ALLOW_WS_QUERY_API_KEY", "1")
    monkeypatch.setenv("VERITAS_ACK_WS_QUERY_API_KEY_RISK", "1")
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as caught:
        with client.websocket_connect("/v1/ws/trustlog?api_key=websocket-admission-test"):
            pytest.fail("production query credentials admitted")
    assert caught.value.code == 1008
    hub.register.assert_not_called()


def test_mounted_sse_retains_http_auth_and_startup_guard(ws_app, monkeypatch):
    # Isolate failed attempts accumulated by other tests using the same client IP.
    monkeypatch.setattr(auth, "_auth_fail_bucket", {})
    app, hub, _ = ws_app
    monkeypatch.setattr(app.state, "security_startup_complete", False)
    # Isolate this auth check from failures recorded for the default test client.
    client = TestClient(app, client=("192.0.2.241", 50000))
    assert client.get("/v1/events").status_code == 401
    response = client.get("/v1/events", headers={"X-API-Key": "websocket-admission-test"})
    assert response.status_code == 503
    assert response.json()["detail"] == "API security startup incomplete"
    hub.register.assert_not_called()


def test_mounted_websocket_non_strict_retains_admission(ws_app, monkeypatch):
    app, _, event = ws_app
    monkeypatch.setenv("VERITAS_ENV", "local")
    monkeypatch.delenv("VERITAS_POSTURE", raising=False)
    monkeypatch.setattr(app.state, "security_startup_complete", False)
    client = TestClient(app)
    with client.websocket_connect(
        "/v1/ws/trustlog", headers={"X-API-Key": "websocket-admission-test"},
    ) as socket:
        assert socket.receive_json() == event
