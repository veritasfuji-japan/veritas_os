"""Tests for governance policy API and local persistence behavior."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

import veritas_os.api.server as server

_TEST_KEY = "governance-test-key"
os.environ["VERITAS_API_KEY"] = _TEST_KEY

client = TestClient(server.app)


def test_get_governance_policy_returns_defaults(monkeypatch, tmp_path):
    """GET endpoint returns validated default policy when file does not exist."""
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_KEY)
    store = server.GovernancePolicyStore(tmp_path / "governance.json")
    monkeypatch.setattr(server, "GOVERNANCE_STORE", store)

    response = client.get("/v1/governance/policy", headers={"X-API-Key": _TEST_KEY})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["policy"]["fuji_enabled"] is True
    assert payload["policy"]["audit_intensity"] == "standard"


def test_put_governance_policy_persists_and_returns_diff(monkeypatch, tmp_path):
    """PUT endpoint persists policy and returns before/after snapshots."""
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_KEY)
    store = server.GovernancePolicyStore(tmp_path / "governance.json")
    monkeypatch.setattr(server, "GOVERNANCE_STORE", store)

    policy = {
        "fuji_enabled": False,
        "risk_threshold": 0.42,
        "auto_stop_conditions": ["critical_fuji_violation"],
        "log_retention_days": 60,
        "audit_intensity": "strict",
    }
    response = client.put(
        "/v1/governance/policy",
        headers={"X-API-Key": _TEST_KEY},
        json={"policy": policy},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["before"]["fuji_enabled"] is True
    assert payload["policy"] == policy

    file_payload = (tmp_path / "governance.json").read_text(encoding="utf-8")
    assert '"audit_intensity": "strict"' in file_payload


def test_put_governance_policy_rejects_invalid_threshold(monkeypatch, tmp_path):
    """Schema validation blocks unsafe threshold values outside 0..1."""
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_KEY)
    monkeypatch.setattr(server, "GOVERNANCE_STORE", server.GovernancePolicyStore(tmp_path / "governance.json"))

    response = client.put(
        "/v1/governance/policy",
        headers={"X-API-Key": _TEST_KEY},
        json={
            "policy": {
                "fuji_enabled": True,
                "risk_threshold": 1.5,
                "auto_stop_conditions": [],
                "log_retention_days": 180,
                "audit_intensity": "standard",
            }
        },
    )
    assert response.status_code == 422
