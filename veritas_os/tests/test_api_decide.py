# tests/test_api_decide.py
import hmac
import json
import secrets
import time

from fastapi.testclient import TestClient

from veritas_os.api.server import app


def test_decide_minimal(monkeypatch):
    # APIキーを設定
    monkeypatch.setenv("VERITAS_API_KEY", "test-key")
    monkeypatch.setenv("VERITAS_API_SECRET", "test-secret")
    client = TestClient(app)

    payload = {
        "query": "テスト用の簡単な質問",
        "context": {
            "user_id": "test_user"
        }
    }

    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    ts = str(int(time.time()))
    nonce = secrets.token_hex(8)
    secret = b"test-secret"
    signature_payload = f"{ts}\n{nonce}\n{body}"
    signature = hmac.new(
        secret,
        signature_payload.encode("utf-8"),
        "sha256",
    ).hexdigest()

    res = client.post(
        "/v1/decide",
        headers={
            "X-API-Key": "test-key",
            "X-Timestamp": ts,
            "X-Nonce": nonce,
            "X-Signature": signature,
            "Content-Type": "application/json",
        },
        content=body,
    )

    assert res.status_code == 200
    data = res.json()

    # 最低限のフィールドがあるか
    assert "chosen" in data
    assert "alternatives" in data
    assert "fuji" in data
    assert "gate" in data
    assert "trust_log" in data
