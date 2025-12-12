# tests/test_api_decide.py
from fastapi.testclient import TestClient

from veritas_os.api.server import app


def test_decide_minimal(monkeypatch):
    # APIキーを設定
    monkeypatch.setenv("VERITAS_API_KEY", "test-key")
    client = TestClient(app)

    payload = {
        "query": "テスト用の簡単な質問",
        "context": {
            "user_id": "test_user"
        }
    }

    res = client.post(
        "/v1/decide",
        headers={"X-API-Key": "test-key"},
        json=payload,
    )

    assert res.status_code == 200
    data = res.json()

    # 最低限のフィールドがあるか
    assert "chosen" in data
    assert "alternatives" in data
    assert "fuji" in data
    assert "gate" in data
    assert "trust_log" in data

