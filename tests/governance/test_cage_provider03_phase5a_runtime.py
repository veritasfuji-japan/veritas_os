from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from veritas_os.governance.cage_provider03_phase5a_runtime import (
    PHASE5A_PROOF_ID,
    TOKEN_ENV,
    create_phase5a_app,
)


TOKEN = "phase5a-test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _client() -> TestClient:
    return TestClient(create_phase5a_app(bearer_token=TOKEN))


def test_runtime_requires_configured_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    with pytest.raises(RuntimeError, match=TOKEN_ENV):
        create_phase5a_app()


def test_missing_and_invalid_bearer_fail_closed() -> None:
    with _client() as client:
        missing = client.get("/baseline/US_FED")
        invalid = client.get(
            "/baseline/US_FED",
            headers={"Authorization": "Bearer wrong-token"},
        )

    assert missing.status_code == 401
    assert invalid.status_code == 401


def test_fetch_baseline_returns_profile_and_etag() -> None:
    with _client() as client:
        response = client.get("/baseline/US_FED", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["profile"]["provider"] == "VERITAS_OS"
    assert response.json()["profile"]["prototype_phase"] == "5A"
    assert response.json()["profile"]["execution_authority_created"] is False
    assert response.headers.get("etag")


def test_validate_runtime_covers_approved_escalate_and_rejected() -> None:
    cases = {
        "scenario_a_allowed_internal_escalation": "APPROVED",
        "scenario_d_stale_sanctions_screening": "ESCALATE",
        "scenario_b_prohibited_account_freeze": "REJECTED",
    }

    with _client() as client:
        for scenario_name, expected_verdict in cases.items():
            response = client.post(
                "/validate",
                headers=AUTH,
                json={
                    "action": "aml_kyc_regulated_action",
                    "veritas_scenario_name": scenario_name,
                    "action_context": {"amount": 1000, "symbol": "acct"},
                },
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["verdict"] == expected_verdict
            assert payload["findings"][0]["scenario_name"] == scenario_name
            assert payload["findings"][0]["external_effect_executed"] is False


def test_validate_missing_or_unknown_scenario_rejects() -> None:
    with _client() as client:
        missing = client.post("/validate", headers=AUTH, json={"action": "x"})
        unknown = client.post(
            "/validate",
            headers=AUTH,
            json={"veritas_scenario_name": "not-a-real-scenario"},
        )

    assert missing.status_code == 200
    assert missing.json()["verdict"] == "REJECTED"
    assert missing.json()["findings"][0]["severity"] == "blocked"
    assert unknown.status_code == 200
    assert unknown.json()["verdict"] == "REJECTED"
    assert unknown.json()["findings"][0]["code"] == "veritas.phase5a.scenario_unknown"


def test_submit_evidence_is_deterministic_and_not_witness_claim() -> None:
    body = {"evidence_hash": hashlib.sha256(b"phase5a-evidence").hexdigest()}
    with _client() as client:
        first = client.post("/evidence/thread-123", headers=AUTH, json=body)
        second = client.post("/evidence/thread-123", headers=AUTH, json=body)
        manifest = client.get("/phase5a/manifest", headers=AUTH)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["seal_hash"] == second.json()["seal_hash"]
    assert len(first.json()["seal_hash"]) == 64
    assert manifest.status_code == 200
    assert manifest.json()["proof_id"] == PHASE5A_PROOF_ID
    assert manifest.json()["live_external_effects"] is False
    assert manifest.json()["trustlog_witness_claim"] is False
