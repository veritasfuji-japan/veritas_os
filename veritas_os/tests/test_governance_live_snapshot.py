"""Tests for governance live snapshot endpoint."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

import veritas_os.api.server as server
from veritas_os.policy.bind_artifacts import BindReceipt, FinalOutcome

_TEST_KEY = "gov-live-snapshot-test-key"
os.environ["VERITAS_API_KEY"] = _TEST_KEY
_AUTH = {"X-API-Key": _TEST_KEY, "X-Role": "admin"}

client = TestClient(server.app)


@pytest.fixture(autouse=True)
def _reset_auth(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_KEY)
    monkeypatch.setenv("VERITAS_API_KEYS", "[{\"key\":\"gov-live-snapshot-test-key\",\"role\":\"auditor\"}]")



def test_governance_live_snapshot_returns_200(monkeypatch):
    receipt = BindReceipt(final_outcome=FinalOutcome.COMMITTED, bind_ts="2026-04-30T00:00:00Z")
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda limit=1: [receipt],
    )

    response = client.get("/v1/governance/live-snapshot", headers=_AUTH)
    assert response.status_code == 200
    payload = response.json()
    assert "governance_layer_snapshot" in payload


def test_governance_live_snapshot_has_required_fields(monkeypatch):
    receipt = BindReceipt(final_outcome=FinalOutcome.ESCALATED, bind_ts="2026-04-30T00:00:00Z")
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda limit=1: [receipt],
    )

    snapshot = client.get("/v1/governance/live-snapshot", headers=_AUTH).json()["governance_layer_snapshot"]
    for key in (
        "participation_state",
        "preservation_state",
        "intervention_viability",
        "bind_outcome",
        "source",
        "updated_at",
    ):
        assert key in snapshot


def test_governance_live_snapshot_degraded_when_artifact_unavailable(monkeypatch):
    def _raise(limit=1):
        raise RuntimeError("no storage")

    monkeypatch.setattr("veritas_os.api.governance_live_snapshot.find_bind_receipts", _raise)
    response = client.get("/v1/governance/live-snapshot", headers=_AUTH)
    assert response.status_code == 200
    snapshot = response.json()["governance_layer_snapshot"]
    assert snapshot["source"] == "degraded_no_recent_governance_artifact"
    assert snapshot["bind_outcome"] == "UNKNOWN"


def test_governance_live_snapshot_vocabulary(monkeypatch):
    monkeypatch.setattr("veritas_os.api.governance_live_snapshot.find_bind_receipts", lambda limit=1: [])
    snapshot = client.get("/v1/governance/live-snapshot", headers=_AUTH).json()["governance_layer_snapshot"]
    assert snapshot["participation_state"] in {"informative", "participatory", "decision_shaping", "unknown"}
    assert snapshot["preservation_state"] in {"open", "degrading", "collapsed", "unknown"}
    assert snapshot["intervention_viability"] in {"high", "medium", "minimal", "unknown"}
    assert snapshot["bind_outcome"] in {
        "COMMITTED",
        "BLOCKED",
        "ESCALATED",
        "ROLLED_BACK",
        "APPLY_FAILED",
        "SNAPSHOT_FAILED",
        "PRECONDITION_FAILED",
        "UNKNOWN",
    }


def test_governance_live_snapshot_requires_auth():
    response = client.get("/v1/governance/live-snapshot")
    assert response.status_code in {401, 403}
