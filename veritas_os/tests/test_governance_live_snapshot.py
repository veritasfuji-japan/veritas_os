"""Tests for governance live snapshot endpoint and builder behavior."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

import veritas_os.api.server as server
from veritas_os.api.governance_live_snapshot import (
    _normalize_bind_outcome,
    _normalize_state,
    build_governance_live_snapshot,
)
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
        lambda: [receipt],
    )

    response = client.get("/v1/governance/live-snapshot", headers=_AUTH)
    assert response.status_code == 200
    payload = response.json()
    assert "governance_layer_snapshot" in payload


def test_governance_live_snapshot_has_required_fields(monkeypatch):
    receipt = BindReceipt(final_outcome=FinalOutcome.ESCALATED, bind_ts="2026-04-30T00:00:00Z")
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [receipt],
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


def test_governance_live_snapshot_uses_latest_receipt(monkeypatch):
    old = BindReceipt(final_outcome=FinalOutcome.BLOCKED, bind_ts="2026-04-29T00:00:00Z")
    latest = BindReceipt(final_outcome=FinalOutcome.COMMITTED, bind_ts="2026-04-30T00:00:00Z")
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [old, latest],
    )

    snapshot = client.get("/v1/governance/live-snapshot", headers=_AUTH).json()["governance_layer_snapshot"]
    assert snapshot["source"] == "backend_live_snapshot"
    assert snapshot["bind_outcome"] == "COMMITTED"
    assert snapshot["updated_at"] == "2026-04-30T00:00:00Z"


def test_governance_live_snapshot_degraded_when_no_receipts(monkeypatch):
    monkeypatch.setattr("veritas_os.api.governance_live_snapshot.find_bind_receipts", lambda: [])

    snapshot = client.get("/v1/governance/live-snapshot", headers=_AUTH).json()["governance_layer_snapshot"]
    assert snapshot["source"] == "degraded_no_recent_governance_artifact"
    assert snapshot["bind_outcome"] == "UNKNOWN"


def test_governance_live_snapshot_degraded_when_artifact_unavailable(monkeypatch):
    def _raise():
        raise RuntimeError("no storage")

    monkeypatch.setattr("veritas_os.api.governance_live_snapshot.find_bind_receipts", _raise)
    response = client.get("/v1/governance/live-snapshot", headers=_AUTH)
    assert response.status_code == 200
    snapshot = response.json()["governance_layer_snapshot"]
    assert snapshot["source"] == "degraded_no_recent_governance_artifact"
    assert snapshot["bind_outcome"] == "UNKNOWN"


def test_governance_live_snapshot_vocabulary(monkeypatch):
    class _FakeReceipt:
        def to_dict(self):
            return {
                "participation_state": "INVALID",
                "preservation_state": "",
                "intervention_viability": "NOT_A_STATE",
                "final_outcome": "not_real",
                "bind_ts": "2026-04-30T00:00:00Z",
            }

    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [_FakeReceipt()],
    )
    snapshot = client.get("/v1/governance/live-snapshot", headers=_AUTH).json()["governance_layer_snapshot"]
    assert snapshot["participation_state"] == "unknown"
    assert snapshot["preservation_state"] == "unknown"
    assert snapshot["intervention_viability"] == "unknown"
    assert snapshot["bind_outcome"] == "UNKNOWN"


def test_builder_uses_latest_receipt(monkeypatch):
    old = BindReceipt(final_outcome=FinalOutcome.BLOCKED, bind_ts="2026-04-29T00:00:00Z")
    latest = BindReceipt(final_outcome=FinalOutcome.ESCALATED, bind_ts="2026-04-30T00:00:00Z")
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [old, latest],
    )

    snapshot = build_governance_live_snapshot()["governance_layer_snapshot"]
    assert snapshot["source"] == "backend_live_snapshot"
    assert snapshot["bind_outcome"] == "ESCALATED"
    assert snapshot["updated_at"] == "2026-04-30T00:00:00Z"


def test_builder_degraded_on_exception(monkeypatch):
    def _raise():
        raise RuntimeError("boom")

    monkeypatch.setattr("veritas_os.api.governance_live_snapshot.find_bind_receipts", _raise)
    snapshot = build_governance_live_snapshot()["governance_layer_snapshot"]
    assert snapshot["source"] == "degraded_no_recent_governance_artifact"
    assert snapshot["bind_outcome"] == "UNKNOWN"


def test_normalizers_invalid_values():
    assert _normalize_state("invalid", allowed={"known", "unknown"}) == "unknown"
    assert _normalize_state(None, allowed={"known", "unknown"}) == "unknown"
    assert _normalize_bind_outcome("not_real") == "UNKNOWN"
    assert _normalize_bind_outcome(None) == "UNKNOWN"


def test_governance_live_snapshot_requires_auth():
    response = client.get("/v1/governance/live-snapshot")
    assert response.status_code in {401, 403}
