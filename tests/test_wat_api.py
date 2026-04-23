from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from veritas_os.api.server import app
from veritas_os.audit import wat_events


def _headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def _configure_auth(monkeypatch) -> None:
    monkeypatch.setenv(
        "VERITAS_API_KEYS",
        json.dumps(
            [
                {"key": "k-admin", "role": "admin"},
                {"key": "k-operator", "role": "operator"},
                {"key": "k-auditor", "role": "auditor"},
            ]
        ),
    )


def _configure_wat_store(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "wat_events_test.jsonl"
    monkeypatch.setattr(wat_events, "WAT_EVENTS_JSONL", path)
    monkeypatch.setattr(
        wat_events,
        "append_signed_decision",
        lambda *_args, **_kwargs: {"decision_id": "stub", "payload_hash": "hash"},
    )


def test_issue_shadow_success(monkeypatch, tmp_path: Path) -> None:
    _configure_auth(monkeypatch)
    _configure_wat_store(monkeypatch, tmp_path)
    client = TestClient(app)

    response = client.post(
        "/v1/wat/issue-shadow",
        headers=_headers("k-operator"),
        json={"psid": "psid-1", "observable_digest": "abc"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["event"]["event_type"] == "wat_issued"


def test_validate_shadow_success(monkeypatch, tmp_path: Path) -> None:
    _configure_auth(monkeypatch)
    _configure_wat_store(monkeypatch, tmp_path)
    client = TestClient(app)

    issue = client.post(
        "/v1/wat/issue-shadow",
        headers=_headers("k-operator"),
        json={"psid": "psid-2"},
    ).json()
    wat_id = issue["wat_id"]

    response = client.post(
        "/v1/wat/validate-shadow",
        headers=_headers("k-operator"),
        json={"wat_id": wat_id, "outcome_event": "wat_validated"},
    )

    assert response.status_code == 200
    assert response.json()["event"]["event_type"] == "wat_validated"


def test_get_wat_by_id(monkeypatch, tmp_path: Path) -> None:
    _configure_auth(monkeypatch)
    _configure_wat_store(monkeypatch, tmp_path)
    client = TestClient(app)

    issued = client.post(
        "/v1/wat/issue-shadow",
        headers=_headers("k-operator"),
        json={"psid": "psid-3"},
    ).json()

    response = client.get(f"/v1/wat/{issued['wat_id']}", headers=_headers("k-auditor"))

    assert response.status_code == 200
    data = response.json()
    assert data["wat_id"] == issued["wat_id"]
    assert data["latest"]["event_type"] == "wat_issued"


def test_list_wat_events(monkeypatch, tmp_path: Path) -> None:
    _configure_auth(monkeypatch)
    _configure_wat_store(monkeypatch, tmp_path)
    client = TestClient(app)

    for idx in range(2):
        client.post(
            "/v1/wat/issue-shadow",
            headers=_headers("k-operator"),
            json={"psid": f"psid-{idx}"},
        )

    response = client.get("/v1/wat/events?limit=5", headers=_headers("k-auditor"))

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["count"] >= 2


def test_revoke_path(monkeypatch, tmp_path: Path) -> None:
    _configure_auth(monkeypatch)
    _configure_wat_store(monkeypatch, tmp_path)
    client = TestClient(app)

    issue = client.post(
        "/v1/wat/issue-shadow",
        headers=_headers("k-operator"),
        json={"psid": "psid-r"},
    ).json()

    response = client.post(
        f"/v1/wat/revocation/{issue['wat_id']}",
        headers=_headers("k-operator"),
        json={"confirmed": True, "reason": "manual"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["pending"]["event_type"] == "wat_revocation_pending"
    assert data["confirmed"]["event_type"] == "wat_revoked_confirmed"


def test_auth_rbac_read_vs_mutation(monkeypatch, tmp_path: Path) -> None:
    _configure_auth(monkeypatch)
    _configure_wat_store(monkeypatch, tmp_path)
    client = TestClient(app)

    create = client.post(
        "/v1/wat/issue-shadow",
        headers=_headers("k-operator"),
        json={"psid": "psid-auth"},
    ).json()

    read_response = client.get(f"/v1/wat/{create['wat_id']}", headers=_headers("k-auditor"))
    mutate_response = client.post(
        "/v1/wat/issue-shadow",
        headers=_headers("k-auditor"),
        json={"psid": "psid-blocked"},
    )

    assert read_response.status_code == 200
    assert mutate_response.status_code == 403


def test_wat_events_emit_canonical_event_ts(monkeypatch, tmp_path: Path) -> None:
    _configure_wat_store(monkeypatch, tmp_path)
    event = wat_events.persist_wat_issuance_event(
        wat_id="wat-ts-1",
        actor="test",
        details={"request_id": "rid-ts-1"},
    )
    assert event["event_ts"].endswith("Z")
    assert event["event_ts"] == event["ts"]
