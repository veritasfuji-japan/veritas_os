from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from veritas_os.api import server
from veritas_os.api.pipeline_orchestrator import (
    get_runtime_config,
    update_runtime_config,
)
from veritas_os.policy.bind_artifacts import BindReceipt, FinalOutcome


def test_compliance_config_get_and_put(monkeypatch) -> None:
    """Compliance config endpoint should be authenticated and state-safe.

    This test restores global runtime config after execution so it does not
    affect other API tests that expect EU mode to be disabled by default.
    """
    client = TestClient(server.app)
    headers = {"X-API-Key": "test-key"}

    original = server.API_KEY_DEFAULT
    original_cfg = get_runtime_config()
    server.API_KEY_DEFAULT = "test-key"
    monkeypatch.setenv("VERITAS_API_KEY", "test-key")
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
        assert put_payload["bind_outcome"] == "COMMITTED"
        assert put_payload["bind_receipt_id"]
        assert put_payload["execution_intent_id"]
        assert put_payload["bind_receipt"]["final_outcome"] == "COMMITTED"

        get_resp = client.get("/v1/compliance/config", headers=headers)
        assert get_resp.status_code == 200
        get_payload = get_resp.json()
        assert get_payload["config"]["eu_ai_act_mode"] is True
        assert get_payload.get("bind_outcome") is None
    finally:
        server.API_KEY_DEFAULT = original
        update_runtime_config(
            eu_ai_act_mode=bool(original_cfg["eu_ai_act_mode"]),
            safety_threshold=float(original_cfg["safety_threshold"]),
        )


def test_compliance_config_put_bind_blocked(monkeypatch) -> None:
    """Bind BLOCKED outcome should preserve route-level error semantics."""
    client = TestClient(server.app)
    headers = {"X-API-Key": "test-key"}

    original = server.API_KEY_DEFAULT
    server.API_KEY_DEFAULT = "test-key"
    monkeypatch.setenv("VERITAS_API_KEY", "test-key")

    blocked_receipt = replace(
        BindReceipt(
            bind_receipt_id="br-comp-blocked",
            execution_intent_id="ei-comp-blocked",
            decision_id="dec-comp-blocked",
            final_outcome=FinalOutcome.BLOCKED,
        ),
        admissibility_result={
            "admissible": False,
            "reason_codes": ["BIND_AUTHORITY_DENIED"],
            "reason": "authority denied",
        },
    )
    monkeypatch.setattr(
        "veritas_os.api.routes_system.update_compliance_config_with_bind_boundary",
        lambda **kwargs: blocked_receipt,
    )
    try:
        resp = client.put(
            "/v1/compliance/config",
            headers=headers,
            json={"eu_ai_act_mode": True, "safety_threshold": 0.77},
        )
        assert resp.status_code == 403
        body = resp.json()
        assert body["ok"] is False
        assert body["bind_outcome"] == "BLOCKED"
        assert body["bind_receipt_id"] == "br-comp-blocked"
    finally:
        server.API_KEY_DEFAULT = original
