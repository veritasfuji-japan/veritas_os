"""Mounted erasure must preserve owner/hold boundaries and trusted attribution."""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from veritas_os.api import auth, server
from veritas_os.core.memory.memory_store import MemoryStore


KEYS = ("erase-operator-one", "erase-operator-two")
AUDITOR = "erase-read-only"


@pytest.fixture()
def erase_state(tmp_path, monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", KEYS[0])
    monkeypatch.setenv("VERITAS_API_KEYS", json.dumps([
        *({"key": key, "role": "operator"} for key in KEYS),
        {"key": AUDITOR, "role": "auditor"},
    ]))
    store = MemoryStore(tmp_path / "memory.json")
    for key in KEYS:
        owner = auth._derive_api_user_id(key)
        for record_key, value in {
            "episode": {"kind": "episodic", "meta": {"user_id": owner}},
            "held": {"kind": "episodic", "meta": {
                "user_id": owner, "legal_hold": True,
            }},
            "derived": {"kind": "semantic", "meta": {
                "user_id": owner, "source_episode_keys": ["episode"],
            }},
        }.items():
            assert store.put(owner, record_key, value)
    erase = Mock(wraps=store.erase_user)
    monkeypatch.setattr(store, "erase_user", erase)
    monkeypatch.setattr(server, "get_memory_store", lambda: store)
    # Mounted authentication/permissions run normally; no startup/provider work.
    client = TestClient(server.app)
    try:
        yield client, store, erase
    finally:
        client.close()


@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("claimed_actor", ["other-admin", "", None])
def test_http_erasure_actor_is_authenticated(erase_state, key, claimed_actor):
    client, store, erase = erase_state
    body = {"reason": "temporary fixture erasure"}
    if claimed_actor is not None:
        body["actor"] = claimed_actor
    response = client.post(
        "/v1/memory/erase", headers={"X-API-Key": key}, json=body,
    )
    assert response.status_code == 200
    report = response.json()
    assert report["ok"] is True
    expected = auth._derive_api_user_id(key)
    assert report["actor"] == expected
    assert report["target_user_id"] == expected
    erase.assert_called_once_with(
        user_id=expected, reason=body["reason"], actor=expected,
    )
    # Reopen the actual file: check persisted attribution, not a mock receipt.
    reopened = MemoryStore(store.path)
    audit = reopened.list_all("__audit__")
    assert len(audit) == 1
    assert audit[0]["value"]["meta"]["payload"] == {
        name: value for name, value in report.items() if name != "ok"
    }


@pytest.mark.parametrize("key", KEYS)
def test_http_erasure_keeps_other_owner_and_legal_hold(erase_state, key):
    client, store, erase = erase_state
    owner = auth._derive_api_user_id(key)
    other = auth._derive_api_user_id(next(k for k in KEYS if k != key))
    before_other = store.list_all(other)
    before_hold = store.get(owner, "held")
    response = client.post(
        "/v1/memory/erase", headers={"X-API-Key": key},
        json={"user_id": other, "actor": "forged-admin", "legal_hold": False},
    )
    assert response.status_code == 200
    report = response.json()
    assert report["ok"] is True
    assert report["target_user_id"] == owner
    assert report["deleted_count"] == 1
    assert report["cascade_deleted_count"] == 1
    assert report["protected_by_legal_hold"] == 1
    assert erase.call_count == 1
    reopened = MemoryStore(store.path)
    assert reopened.list_all(other) == before_other
    assert reopened.get(owner, "held") == before_hold
    assert reopened.get(owner, "episode") is None
    assert reopened.get(owner, "derived") is None


@pytest.mark.parametrize("key, status", [(None, 401), ("invalid-erase-key", 401), (AUDITOR, 403)])
def test_http_erasure_refuses_without_write_permission(erase_state, key, status):
    client, store, erase = erase_state
    before = store.path.read_bytes()
    headers = {"X-API-Key": key} if key else {}
    response = client.post("/v1/memory/erase", headers=headers, json={})
    assert response.status_code == status
    erase.assert_not_called()
    assert store.path.read_bytes() == before


@pytest.mark.parametrize("key", KEYS)
def test_http_erasure_refuses_missing_principal(erase_state, monkeypatch, key):
    client, store, erase = erase_state
    before = store.path.read_bytes()
    monkeypatch.setattr(auth, "_bind_authenticated_principal", lambda request, key: None)
    response = client.post(
        "/v1/memory/erase", headers={"X-API-Key": key}, json={},
    )
    assert response.status_code == 403
    erase.assert_not_called()
    assert store.path.read_bytes() == before
