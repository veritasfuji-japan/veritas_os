"""Governance policy API tests."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import veritas_os.api.server as server


TEST_API_KEY = "test-governance-key"
HEADERS = {"X-API-Key": TEST_API_KEY}


client = TestClient(server.app)


def test_get_governance_policy_returns_defaults(tmp_path, monkeypatch):
    """GET should return default policy when storage file is missing."""
    policy_path = tmp_path / "governance.json"
    monkeypatch.setenv("VERITAS_API_KEY", TEST_API_KEY)
    monkeypatch.setattr(server, "GOVERNANCE_POLICY_PATH", policy_path)

    response = client.get("/v1/governance/policy", headers=HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["policy"]["fuji_enabled"] is True
    assert payload["policy"]["audit_strength"] == "standard"


def test_put_governance_policy_persists_and_returns_diff(tmp_path, monkeypatch):
    """PUT should persist the policy file and return before/after diff."""
    policy_path = tmp_path / "governance.json"
    monkeypatch.setenv("VERITAS_API_KEY", TEST_API_KEY)
    monkeypatch.setattr(server, "GOVERNANCE_POLICY_PATH", policy_path)

    put_response = client.put(
        "/v1/governance/policy",
        headers=HEADERS,
        json={
            "policy": {
                "fuji_enabled": False,
                "risk_threshold": 0.25,
                "auto_stop_conditions": ["manual_override", "high_risk_detected"],
                "log_retention_days": 365,
                "audit_strength": "strict",
            }
        },
    )

    assert put_response.status_code == 200
    body = put_response.json()
    assert body["policy"]["fuji_enabled"] is False
    assert "risk_threshold" in body["diff"]

    persisted = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    assert persisted["risk_threshold"] == 0.25

    get_response = client.get("/v1/governance/policy", headers=HEADERS)
    assert get_response.status_code == 200
    assert get_response.json()["policy"]["audit_strength"] == "strict"
