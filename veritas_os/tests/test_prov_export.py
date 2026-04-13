"""Tests for W3C PROV decision-trace export endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from veritas_os.api import server


client = TestClient(server.app)


def test_prov_export_success(monkeypatch) -> None:
    """Endpoint should return PROV payload for an existing trust trace."""
    monkeypatch.setenv("VERITAS_API_KEY", "test-key")
    monkeypatch.setattr(
        server,
        "get_trust_logs_by_request",
        lambda _rid: [
            {
                "request_id": "req-1",
                "decision_status": "allow",
                "risk": 0.2,
                "ts": "2026-03-14T00:00:00Z",
                "actor": "api",
            }
        ],
    )

    resp = client.get(
        "/v1/trust/req-1/prov",
        headers={"X-API-Key": "test-key"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "prov" in body
    assert "entity" in body["prov"]


def test_prov_export_not_found(monkeypatch) -> None:
    """Endpoint should return 404 when trust trace is missing."""
    monkeypatch.setenv("VERITAS_API_KEY", "test-key")
    monkeypatch.setattr(server, "get_trust_logs_by_request", lambda _rid: [])

    resp = client.get(
        "/v1/trust/missing/prov",
        headers={"X-API-Key": "test-key"},
    )

    assert resp.status_code == 404
    assert resp.json()["ok"] is False


def test_prov_export_non_finite_risk_is_sanitized(monkeypatch) -> None:
    """Endpoint should ignore non-finite risk values before PROV export."""
    monkeypatch.setenv("VERITAS_API_KEY", "test-key")
    monkeypatch.setattr(
        server,
        "get_trust_logs_by_request",
        lambda _rid: [{"request_id": "req-1", "risk": float("nan")}],
    )

    observed: dict[str, object] = {}

    def _build_w3c_prov_document(**kwargs):
        observed["risk"] = kwargs.get("risk")
        return {"entity": {}, "activity": {}, "agent": {}}

    monkeypatch.setattr(server, "build_w3c_prov_document", _build_w3c_prov_document)

    resp = client.get(
        "/v1/trust/req-1/prov",
        headers={"X-API-Key": "test-key"},
    )

    assert resp.status_code == 200
    assert observed["risk"] is None
