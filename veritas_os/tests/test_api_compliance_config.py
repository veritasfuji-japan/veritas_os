from __future__ import annotations

from fastapi.testclient import TestClient

from veritas_os.api import server


def test_compliance_config_get_and_put() -> None:
    client = TestClient(server.app)
    headers = {"X-API-Key": "test-key"}

    original = server.API_KEY_DEFAULT
    server.API_KEY_DEFAULT = "test-key"
    try:
        put_resp = client.put(
            "/v1/compliance/config",
            headers=headers,
            json={"eu_ai_act_mode": True, "safety_threshold": 0.77},
        )
        assert put_resp.status_code == 200
        put_payload = put_resp.json()
        assert put_payload["config"]["eu_ai_act_mode"] is True
        assert put_payload["config"]["safety_threshold"] == 0.77

        get_resp = client.get("/v1/compliance/config", headers=headers)
        assert get_resp.status_code == 200
        get_payload = get_resp.json()
        assert get_payload["config"]["eu_ai_act_mode"] is True
    finally:
        server.API_KEY_DEFAULT = original
