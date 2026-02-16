from __future__ import annotations

import os

from fastapi.testclient import TestClient

import veritas_os.api.server as server

_TEST_API_KEY = "test-governance-key"
os.environ["VERITAS_API_KEY"] = _TEST_API_KEY

client = TestClient(server.app)
_HEADERS = {"X-API-Key": _TEST_API_KEY}


def _governance_payload() -> dict:
    return {
        "fuji_enabled": False,
        "risk_threshold": 0.42,
        "auto_stop_conditions": ["risk_threshold_exceeded", "manual_override"],
        "log_retention_days": 120,
        "audit_intensity": "high",
    }


def test_get_governance_policy_initializes_default(tmp_path, monkeypatch):
    """GET initializes the file-backed policy with defaults when absent."""
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    monkeypatch.setattr(server, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(server, "_governance_store_state", server._LazyState())

    response = client.get("/v1/governance/policy", headers=_HEADERS)
    assert response.status_code == 200

    payload = response.json()
    assert payload["fuji_enabled"] is True
    assert payload["risk_threshold"] == 0.6
    assert payload["audit_intensity"] == "standard"
    assert (tmp_path / "governance.json").exists()


def test_put_governance_policy_persists_and_increments_version(tmp_path, monkeypatch):
    """PUT validates and persists policy with version bump and timestamp update."""
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    monkeypatch.setattr(server, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(server, "_governance_store_state", server._LazyState())

    first = client.get("/v1/governance/policy", headers=_HEADERS)
    assert first.status_code == 200
    first_version = first.json()["version"]

    update = client.put("/v1/governance/policy", headers=_HEADERS, json=_governance_payload())
    assert update.status_code == 200
    updated_payload = update.json()

    assert updated_payload["version"] == first_version + 1
    assert updated_payload["fuji_enabled"] is False
    assert updated_payload["audit_intensity"] == "high"

    fetch_again = client.get("/v1/governance/policy", headers=_HEADERS)
    assert fetch_again.status_code == 200
    assert fetch_again.json()["risk_threshold"] == 0.42


def test_put_governance_policy_rejects_invalid_payload(tmp_path, monkeypatch):
    """PUT rejects invalid governance policy with 400 details."""
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    monkeypatch.setattr(server, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(server, "_governance_store_state", server._LazyState())

    response = client.put(
        "/v1/governance/policy",
        headers=_HEADERS,
        json={
            "fuji_enabled": "yes",
            "risk_threshold": 1.2,
            "auto_stop_conditions": [],
            "log_retention_days": 0,
            "audit_intensity": "extreme",
        },
    )

    assert response.status_code == 400
    assert "fuji_enabled must be boolean" in response.json()["detail"]
