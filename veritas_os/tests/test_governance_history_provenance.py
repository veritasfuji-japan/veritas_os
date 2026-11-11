"""HTTP policy changes record authenticated provenance."""

import threading

import pytest


@pytest.fixture
def isolated_api(monkeypatch, tmp_path):
    monkeypatch.setenv("VERITAS_ENV", "test")
    monkeypatch.setenv("VERITAS_API_KEY", "synthetic-audit-admin-key")
    monkeypatch.setenv("VERITAS_API_KEYS", "[]")
    monkeypatch.setenv("VERITAS_GOVERNANCE_REQUIRE_FOUR_EYES", "1")
    monkeypatch.setenv("VERITAS_GOVERNANCE_ENFORCE_RBAC", "1")
    monkeypatch.setenv("VERITAS_GOVERNANCE_ALLOWED_ROLES", "admin,auditor")
    monkeypatch.delenv("VERITAS_GOVERNANCE_TENANT_ID", raising=False)
    from fastapi.testclient import TestClient
    from veritas_os.api import server, governance as gov
    from veritas_os.governance.file_repository import FileGovernanceRepository
    from veritas_os.policy.bind_core import core
    repo = FileGovernanceRepository(policy_path=tmp_path / "policy.json",
        history_path=tmp_path / "history.jsonl", lock=threading.Lock(), policy_history_max=100)
    monkeypatch.setattr(gov, "_governance_repository_factory", lambda: repo)
    monkeypatch.setattr(gov, "_notify_policy_update", lambda _: None)
    monkeypatch.setattr(core, "append_execution_intent_trustlog", lambda _: None)
    monkeypatch.setattr(core, "append_bind_receipt_trustlog", lambda r: r)
    monkeypatch.setattr(server, "_publish_event", lambda *args: None)
    return TestClient(server.app), server, gov, repo


def test_policy_history_uses_authenticated_update_provenance(isolated_api):
    client, _, gov, repo = isolated_api
    body = {"version": "audit-reproduction", "updated_by": "unrelated-person",
        "_event_type": "rollback", "approvals": [
            {"reviewer": "invented-a", "signature": "not-a-signature-a"},
            {"reviewer": "invented-b", "signature": "not-a-signature-b"}]}
    response = client.put("/v1/governance/policy", json=body,
        headers={"X-API-Key": "synthetic-audit-admin-key", "X-Role": "admin"})
    assert response.status_code == 200, response.text
    actor = response.json()["bind_receipt"]["actor_identity"]
    assert actor.startswith("key_")
    assert gov.get_policy()["updated_by"] == actor
    assert gov.get_policy()["version"] == "audit-reproduction"
    history = repo.list_policy_history(limit=1, max_records=10)[0]
    assert history["changed_by"] == actor
    assert history["proposer"] == actor
    assert history["event_type"] == "update"
