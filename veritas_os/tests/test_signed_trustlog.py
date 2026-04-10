from __future__ import annotations

import base64
import json

from fastapi.testclient import TestClient
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

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
    assert entry["signer_type"] == "file"
    assert entry["signer_key_id"]
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


def test_worm_mirror_and_verify_metadata(monkeypatch, tmp_path):
    log_path = tmp_path / "trustlog.jsonl"
    mirror_path = tmp_path / "worm" / "trustlog_mirror.jsonl"
    private_key = tmp_path / "keys" / "priv.key"
    public_key = tmp_path / "keys" / "pub.key"

    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", log_path)
    monkeypatch.setattr(trustlog_signed, "PRIVATE_KEY_PATH", private_key)
    monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", public_key)
    monkeypatch.setenv("VERITAS_TRUSTLOG_WORM_MIRROR_PATH", str(mirror_path))

    entry = trustlog_signed.append_signed_decision(
        {"request_id": "r-worm", "decision": "allow"}
    )

    assert entry["worm_mirror"]["configured"] is True
    assert entry["worm_mirror"]["ok"] is True
    assert mirror_path.exists()

    verify_result = trustlog_signed.verify_trustlog_chain(path=log_path)
    assert verify_result["ok"] is True
    assert verify_result["worm_mirror"]["configured"] is True
    assert verify_result["worm_mirror"]["exists"] is True
    assert verify_result["worm_mirror"]["entries"] == 1
    assert verify_result["key_management"]["public_key_present"] is True
    assert verify_result["key_management"]["signer_type"] == "file"
    assert verify_result["key_management"]["signer_key_id"]


def test_worm_hard_fail_mode_raises_when_mirror_write_fails(monkeypatch, tmp_path):
    log_path = tmp_path / "trustlog.jsonl"
    private_key = tmp_path / "keys" / "priv.key"
    public_key = tmp_path / "keys" / "pub.key"
    read_only_dir = tmp_path / "mirror_dir"
    read_only_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", log_path)
    monkeypatch.setattr(trustlog_signed, "PRIVATE_KEY_PATH", private_key)
    monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", public_key)
    monkeypatch.setenv("VERITAS_TRUSTLOG_WORM_MIRROR_PATH", str(read_only_dir))
    monkeypatch.setenv("VERITAS_TRUSTLOG_WORM_HARD_FAIL", "1")

    with pytest.raises(trustlog_signed.SignedTrustLogWriteError, match="worm_mirror_write_failed"):
        trustlog_signed.append_signed_decision({"request_id": "r-hard-fail", "decision": "allow"})


def test_aws_kms_signer_backend(monkeypatch, tmp_path):
    class FakeKmsClient:
        def __init__(self):
            self.private_key = Ed25519PrivateKey.generate()
            self.key_id = "arn:aws:kms:us-east-1:111122223333:key/example"

        def sign(self, *, KeyId, Message, MessageType, SigningAlgorithm):
            assert KeyId == self.key_id
            assert MessageType == "RAW"
            assert SigningAlgorithm == "EDDSA"
            return {"Signature": self.private_key.sign(Message)}

        def get_public_key(self, *, KeyId):
            assert KeyId == self.key_id
            public_der = self.private_key.public_key().public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            return {"PublicKey": public_der}

    class FakeBoto3:
        def __init__(self, client):
            self._client = client

        def client(self, service_name):
            assert service_name == "kms"
            return self._client

    log_path = tmp_path / "trustlog.jsonl"
    fake_kms = FakeKmsClient()
    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", log_path)
    monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "aws_kms")
    monkeypatch.setenv("VERITAS_TRUSTLOG_KMS_KEY_ID", fake_kms.key_id)
    monkeypatch.setattr(
        "veritas_os.security.signing.importlib.import_module",
        lambda module_name: FakeBoto3(fake_kms),
    )

    entry = trustlog_signed.append_signed_decision({"request_id": "r-kms", "decision": "allow"})
    assert entry["signer_type"] == "aws_kms"
    assert entry["signer_key_id"] == fake_kms.key_id
    assert trustlog_signed.verify_signature(entry) is True


def test_verify_signature_uses_entry_signer_metadata(monkeypatch):
    class FakeKmsClient:
        def __init__(self):
            self.private_key = Ed25519PrivateKey.generate()
            self.key_id = "arn:aws:kms:us-east-1:111122223333:key/verify"

        def sign(self, *, KeyId, Message, MessageType, SigningAlgorithm):
            assert KeyId == self.key_id
            assert MessageType == "RAW"
            assert SigningAlgorithm == "EDDSA"
            return {"Signature": self.private_key.sign(Message)}

        def get_public_key(self, *, KeyId):
            assert KeyId == self.key_id
            public_der = self.private_key.public_key().public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            return {"PublicKey": public_der}

    class FakeBoto3:
        def __init__(self, client):
            self._client = client

        def client(self, service_name):
            assert service_name == "kms"
            return self._client

    fake_kms = FakeKmsClient()
    monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "file")
    monkeypatch.setattr(
        "veritas_os.security.signing.importlib.import_module",
        lambda module_name: FakeBoto3(fake_kms),
    )

    payload_hash = "ab" * 32
    signature = fake_kms.sign(
        KeyId=fake_kms.key_id,
        Message=payload_hash.encode("utf-8"),
        MessageType="RAW",
        SigningAlgorithm="EDDSA",
    )["Signature"]
    entry = {
        "payload_hash": payload_hash,
        "signature": base64.urlsafe_b64encode(signature).decode("ascii"),
        "signer_type": "aws_kms",
        "signer_key_id": fake_kms.key_id,
    }
    assert trustlog_signed.verify_signature(entry) is True


def test_aws_kms_signer_requires_key_id(monkeypatch, tmp_path):
    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", tmp_path / "trustlog.jsonl")
    monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "aws_kms")
    monkeypatch.delenv("VERITAS_TRUSTLOG_KMS_KEY_ID", raising=False)

    with pytest.raises(trustlog_signed.SignedTrustLogWriteError, match="signed trust log append failed"):
        trustlog_signed.append_signed_decision({"request_id": "r-kms-missing", "decision": "allow"})
