from __future__ import annotations

import json

from fastapi.testclient import TestClient
import pytest

import veritas_os.api.server as server
import veritas_os.logging.trust_log as trust_log


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", "test-key")
    return TestClient(server.app)


def _write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_trust_logs_pagination(client, monkeypatch, tmp_path):
    jsonl = tmp_path / "trust_log.jsonl"
    json_file = tmp_path / "trust_log.json"

    rows = [
        {"request_id": "req-1", "stage": "plan", "sha256": "h1", "sha256_prev": None},
        {"request_id": "req-2", "stage": "value", "sha256": "h2", "sha256_prev": "h1"},
        {"request_id": "req-3", "stage": "fuji", "sha256": "h3", "sha256_prev": "h2"},
    ]
    _write_jsonl(jsonl, rows)
    json_file.write_text(json.dumps({"items": rows}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(server, "LOG_JSONL", jsonl)
    monkeypatch.setattr(server, "LOG_JSON", json_file)
    monkeypatch.setattr(trust_log, "LOG_JSONL", jsonl)
    monkeypatch.setattr(trust_log, "LOG_JSON", json_file)

    response = client.get("/v1/trust/logs?limit=2", headers={"X-API-Key": "test-key"})

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 2
    assert body["has_more"] is True
    assert body["next_cursor"] == "2"
    assert [item["request_id"] for item in body["items"]] == ["req-3", "req-2"]


def test_trust_log_by_request_chain_status(client, monkeypatch, tmp_path):
    jsonl = tmp_path / "trust_log.jsonl"
    json_file = tmp_path / "trust_log.json"

    rows = [
        {"request_id": "same", "stage": "evidence", "sha256": "a1", "sha256_prev": None},
        {"request_id": "other", "stage": "plan", "sha256": "b1", "sha256_prev": "a1"},
        {"request_id": "same", "stage": "value", "sha256": "a2", "sha256_prev": "a1"},
    ]
    _write_jsonl(jsonl, rows)
    json_file.write_text(json.dumps({"items": rows}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(server, "LOG_JSONL", jsonl)
    monkeypatch.setattr(server, "LOG_JSON", json_file)
    monkeypatch.setattr(trust_log, "LOG_JSONL", jsonl)
    monkeypatch.setattr(trust_log, "LOG_JSON", json_file)

    response = client.get("/v1/trust/same", headers={"X-API-Key": "test-key"})

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "same"
    assert body["count"] == 2
    assert body["chain_ok"] is True
    assert body["verification_result"] == "ok"
