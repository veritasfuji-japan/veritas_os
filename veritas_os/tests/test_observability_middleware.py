"""Integration tests for observability middleware."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from veritas_os.observability.middleware import observe_request_metrics


def test_observe_request_metrics_records_status_and_path(monkeypatch):
    captured: list[dict] = []

    def _capture(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(
        "veritas_os.observability.middleware.record_http_request",
        _capture,
    )

    app = FastAPI()
    app.middleware("http")(observe_request_metrics)

    @app.get("/health")
    async def health():
        return {"ok": True}

    client = TestClient(app)
    res = client.get("/health")

    assert res.status_code == 200
    assert captured
    assert captured[0]["method"] == "GET"
    assert captured[0]["path"] == "/health"
    assert captured[0]["status_code"] == 200
    assert captured[0]["duration_seconds"] >= 0.0


def test_observe_request_metrics_handles_exceptions(monkeypatch):
    captured: list[dict] = []

    def _capture(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(
        "veritas_os.observability.middleware.record_http_request",
        _capture,
    )

    app = FastAPI()
    app.middleware("http")(observe_request_metrics)

    @app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)
    res = client.get("/boom")

    assert res.status_code == 500
    assert captured
    assert captured[0]["path"] == "/boom"
    assert captured[0]["status_code"] == 500
