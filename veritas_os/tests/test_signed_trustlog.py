from __future__ import annotations

import json

from fastapi.testclient import TestClient
import pytest

import veritas_os.api.server as server
from veritas_os.audit import trustlog_signed


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", "test-key")
    return TestClient(server.app)


def test_append_and_verify_signed_trustlog(monkeypatch, tmp_path):
    log_path = tmp_path / "trustlog.jsonl"
    private_key = tmp_path / "keys" / "priv.key"
    public_key = tmp_path / "keys" / "pub.key"

    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", log_path)
    monkeypatch.setattr(trustlog_signed, "PRIVATE_KEY_PATH", private_key)
    monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", public_key)

    entry = trustlog_signed.append_signed_decision({"request_id": "r1", "decision": "allow"})

    assert entry["decision_id"]
    assert entry["payload_hash"]
    assert trustlog_signed.verify_signature(entry) is True

    verify_result = trustlog_signed.verify_trustlog_chain(path=log_path)
    assert verify_result["ok"] is True
    assert verify_result["entries_checked"] == 1


def test_detect_tampering(monkeypatch, tmp_path):
    log_path = tmp_path / "trustlog.jsonl"
    private_key = tmp_path / "keys" / "priv.key"
    public_key = tmp_path / "keys" / "pub.key"

    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", log_path)
    monkeypatch.setattr(trustlog_signed, "PRIVATE_KEY_PATH", private_key)
    monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", public_key)

    trustlog_signed.append_signed_decision({"request_id": "r1", "decision": "allow"})

    lines = log_path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["decision_payload"]["decision"] = "reject"
    log_path.write_text(json.dumps(first, ensure_ascii=False) + "\n", encoding="utf-8")

    tamper_result = trustlog_signed.detect_tampering(path=log_path)
    assert tamper_result["tampered"] is True
    assert tamper_result["issues"]


def test_trustlog_verify_and_export_api(client, monkeypatch, tmp_path):
    log_path = tmp_path / "trustlog.jsonl"
    private_key = tmp_path / "keys" / "priv.key"
    public_key = tmp_path / "keys" / "pub.key"

    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", log_path)
    monkeypatch.setattr(trustlog_signed, "PRIVATE_KEY_PATH", private_key)
    monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", public_key)

    trustlog_signed.append_signed_decision({"request_id": "r-api", "decision": "allow"})

    verify_resp = client.get("/v1/trustlog/verify", headers={"X-API-Key": "test-key"})
    assert verify_resp.status_code == 200
    assert verify_resp.json()["ok"] is True

    export_resp = client.get("/v1/trustlog/export", headers={"X-API-Key": "test-key"})
    assert export_resp.status_code == 200
    body = export_resp.json()
    assert body["count"] == 1
    assert body["entries"][0]["decision_payload"]["request_id"] == "r-api"
