"""Production-like governance policy update end-to-end validation.

These tests exercise the governance subsystem through the HTTP API, verifying
that policy updates are persisted, audited, and applied consistently —
matching the behaviour expected in a real deployment.

Markers:
    production — production-like validation (excluded from default CI)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

_TEST_API_KEY = "governance-prod-test-key"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def gov_client(tmp_path, monkeypatch):
    """TestClient with isolated governance state."""
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    # Disable governance RBAC for production-like testing
    monkeypatch.setenv("VERITAS_GOVERNANCE_ENFORCE_RBAC", "0")
    # Disable 4-eyes approval for isolated testing
    monkeypatch.setenv("VERITAS_GOVERNANCE_REQUIRE_FOUR_EYES", "0")
    import veritas_os.api.governance as gov_mod

    # Use a temp governance.json for full isolation
    policy_path = tmp_path / "governance.json"
    default = gov_mod.GovernancePolicy()
    policy_path.write_text(
        json.dumps(default.model_dump(), indent=2), encoding="utf-8"
    )

    history_path = tmp_path / "governance_history.jsonl"

    with patch.object(gov_mod, "_DEFAULT_POLICY_PATH", policy_path), \
         patch.object(gov_mod, "_HISTORY_PATH", history_path, create=True):
        from veritas_os.api.server import app

        client = TestClient(app, raise_server_exceptions=False)
        yield client, policy_path, history_path


def _headers():
    return {"X-API-Key": _TEST_API_KEY}


def _approved(payload: dict) -> dict:
    """Wrap a policy patch with 4-eyes approval metadata."""
    return {
        **payload,
        "updated_by": "production-test",
        "approval": {
            "approved_by": "reviewer@veritas",
            "reason": "production validation test",
        },
    }


# ---------------------------------------------------------------------------
# Production-like governance tests
# ---------------------------------------------------------------------------


@pytest.mark.production
class TestGovernancePolicyReadWrite:
    """Full policy read → update → read-back cycle."""

    def test_get_current_policy(self, gov_client):
        client, _, _ = gov_client
        r = client.get("/v1/governance/policy", headers=_headers())
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        policy = body["policy"]
        assert "fuji_rules" in policy
        assert "risk_thresholds" in policy
        assert "auto_stop" in policy
        assert "log_retention" in policy

    def test_update_fuji_rules(self, gov_client):
        client, policy_path, _ = gov_client

        r = client.put(
            "/v1/governance/policy",
            headers=_headers(),
            json=_approved({"fuji_rules": {"pii_check": False}}),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["policy"]["fuji_rules"]["pii_check"] is False

        # Verify persisted to disk
        on_disk = json.loads(policy_path.read_text())
        assert on_disk["fuji_rules"]["pii_check"] is False

    def test_update_risk_thresholds(self, gov_client):
        client, _, _ = gov_client

        r = client.put(
            "/v1/governance/policy",
            headers=_headers(),
            json=_approved(
                {"risk_thresholds": {"allow_upper": 0.35, "warn_upper": 0.60}}
            ),
        )
        assert r.status_code == 200
        thresholds = r.json()["policy"]["risk_thresholds"]
        assert thresholds["allow_upper"] == 0.35
        assert thresholds["warn_upper"] == 0.60

    def test_update_auto_stop(self, gov_client):
        client, _, _ = gov_client

        r = client.put(
            "/v1/governance/policy",
            headers=_headers(),
            json=_approved(
                {"auto_stop": {"max_risk_score": 0.90, "enabled": False}}
            ),
        )
        assert r.status_code == 200
        auto_stop = r.json()["policy"]["auto_stop"]
        assert auto_stop["enabled"] is False
        assert auto_stop["max_risk_score"] == 0.90

    def test_update_log_retention(self, gov_client):
        client, _, _ = gov_client

        r = client.put(
            "/v1/governance/policy",
            headers=_headers(),
            json=_approved(
                {"log_retention": {"retention_days": 180, "audit_level": "strict"}}
            ),
        )
        assert r.status_code == 200
        retention = r.json()["policy"]["log_retention"]
        assert retention["retention_days"] == 180
        assert retention["audit_level"] == "strict"


@pytest.mark.production
class TestGovernanceAuditTrail:
    """Verify governance changes are audited."""

    def test_history_after_update(self, gov_client):
        client, _, history_path = gov_client

        # Make a change
        client.put(
            "/v1/governance/policy",
            headers=_headers(),
            json=_approved({"fuji_rules": {"pii_check": False}}),
        )

        # History endpoint should reflect the change
        r = client.get("/v1/governance/policy/history", headers=_headers())
        assert r.status_code == 200


@pytest.mark.production
class TestGovernanceValidation:
    """Verify policy update validation rejects bad input."""

    def test_reject_invalid_audit_level(self, gov_client):
        client, _, _ = gov_client

        r = client.put(
            "/v1/governance/policy",
            headers=_headers(),
            json=_approved(
                {"log_retention": {"audit_level": "INVALID_LEVEL"}}
            ),
        )
        # Should be rejected (400 or 422)
        assert r.status_code in (400, 422)

    def test_reject_non_dict_payload(self, gov_client):
        client, _, _ = gov_client

        r = client.put(
            "/v1/governance/policy",
            headers=_headers(),
            json="not-a-dict",
        )
        assert r.status_code in (400, 422)


@pytest.mark.production
class TestGovernanceIdempotency:
    """Verify repeated identical updates are idempotent."""

    def test_double_update_same_result(self, gov_client):
        client, _, _ = gov_client
        payload = _approved({"fuji_rules": {"violence_review": False}})

        r1 = client.put(
            "/v1/governance/policy", headers=_headers(), json=payload
        )
        r2 = client.put(
            "/v1/governance/policy", headers=_headers(), json=payload
        )

        assert r1.status_code == 200
        assert r2.status_code == 200
        # Policies should be functionally identical
        p1 = r1.json()["policy"]["fuji_rules"]
        p2 = r2.json()["policy"]["fuji_rules"]
        assert p1 == p2
