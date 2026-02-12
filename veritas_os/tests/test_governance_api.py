"""Governance API tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import veritas_os.api.server as server


def test_governance_policy_get_and_put(monkeypatch, tmp_path: Path):
    """`/v1/governance/policy` should read and persist file-backed policy."""
    monkeypatch.setenv("VERITAS_API_KEY", "test-key")
    monkeypatch.setattr(server, "GOVERNANCE_POLICY_PATH", tmp_path / "governance.json")
    monkeypatch.setattr(server, "GOVERNANCE_STORE", server.FileGovernancePolicyStore(server.GOVERNANCE_POLICY_PATH))

    client = TestClient(server.app)

    get_response = client.get("/v1/governance/policy", headers={"X-API-Key": "test-key"})
    assert get_response.status_code == 200
    assert get_response.json()["fuji_enabled"] is True

    updated = {
        "fuji_enabled": False,
        "risk_threshold": 0.8,
        "auto_stop_conditions": ["manual_override"],
        "log_retention_days": 30,
        "audit_intensity": "strict",
    }
    put_response = client.put("/v1/governance/policy", headers={"X-API-Key": "test-key"}, json=updated)
    assert put_response.status_code == 200
    assert put_response.json()["audit_intensity"] == "strict"

    get_after = client.get("/v1/governance/policy", headers={"X-API-Key": "test-key"})
    assert get_after.status_code == 200
    assert get_after.json()["fuji_enabled"] is False
    assert server.GOVERNANCE_POLICY_PATH.exists()
