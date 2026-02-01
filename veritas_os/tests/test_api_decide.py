# tests/test_api_decide.py
from fastapi.testclient import TestClient

import veritas_os.api.server as server


def test_decide_minimal(monkeypatch):
    # APIキーを設定
    monkeypatch.setenv("VERITAS_API_KEY", "test-key")
    monkeypatch.setenv("VERITAS_API_SECRET", "test-api-secret")

    class DummyPipeline:
        """Minimal pipeline stub for API decide tests."""

        async def run_decide_pipeline(self, req, request):  # noqa: ANN001
            return {
                "chosen": {"action": "test"},
                "alternatives": [],
                "fuji": {"status": "allow"},
                "gate": {"decision_status": "allow"},
                "trust_log": {"id": "test"},
            }

    monkeypatch.setattr(server, "get_decision_pipeline", lambda: DummyPipeline())

    client = TestClient(server.app)

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
