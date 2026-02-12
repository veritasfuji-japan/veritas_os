# veritas_os/tests/test_governance_api.py
"""Tests for Governance Policy API endpoints."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("VERITAS_API_KEY", "test-governance-key")

from veritas_os.api import governance as gov_mod
from veritas_os.api import server as srv

client = TestClient(srv.app)
HEADERS = {"X-API-Key": "test-governance-key"}


@pytest.fixture(autouse=True)
def _temp_policy(tmp_path: Path):
    """Use a temporary governance.json for every test."""
    policy_path = tmp_path / "governance.json"
    default = gov_mod.GovernancePolicy()
    policy_path.write_text(json.dumps(default.model_dump(), ensure_ascii=False, indent=2))
    with patch.object(gov_mod, "_DEFAULT_POLICY_PATH", policy_path):
        yield policy_path


class TestGetPolicy:
    def test_get_returns_default_policy(self):
        resp = client.get("/v1/governance/policy", headers=HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert "policy" in body
        policy = body["policy"]
        assert "fuji_rules" in policy
        assert "risk_thresholds" in policy
        assert "auto_stop" in policy
        assert "log_retention" in policy

    def test_get_requires_api_key(self):
        resp = client.get("/v1/governance/policy")
        assert resp.status_code in (401, 500)

    def test_fuji_rules_defaults(self):
        resp = client.get("/v1/governance/policy", headers=HEADERS)
        rules = resp.json()["policy"]["fuji_rules"]
        assert rules["pii_check"] is True
        assert rules["self_harm_block"] is True
        assert rules["llm_safety_head"] is True


class TestPutPolicy:
    def test_put_updates_fuji_rules(self):
        resp = client.put(
            "/v1/governance/policy",
            headers=HEADERS,
            json={"fuji_rules": {"pii_check": False}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["policy"]["fuji_rules"]["pii_check"] is False
        # Other rules should remain default
        assert body["policy"]["fuji_rules"]["self_harm_block"] is True

    def test_put_updates_risk_thresholds(self):
        resp = client.put(
            "/v1/governance/policy",
            headers=HEADERS,
            json={"risk_thresholds": {"allow_upper": 0.50}},
        )
        assert resp.status_code == 200
        assert resp.json()["policy"]["risk_thresholds"]["allow_upper"] == 0.50

    def test_put_updates_auto_stop(self):
        resp = client.put(
            "/v1/governance/policy",
            headers=HEADERS,
            json={"auto_stop": {"enabled": False, "max_risk_score": 0.70}},
        )
        body = resp.json()
        assert body["policy"]["auto_stop"]["enabled"] is False
        assert body["policy"]["auto_stop"]["max_risk_score"] == 0.70

    def test_put_updates_log_retention(self):
        resp = client.put(
            "/v1/governance/policy",
            headers=HEADERS,
            json={"log_retention": {"retention_days": 180, "audit_level": "summary"}},
        )
        body = resp.json()
        assert body["policy"]["log_retention"]["retention_days"] == 180
        assert body["policy"]["log_retention"]["audit_level"] == "summary"

    def test_put_sets_updated_at(self):
        resp = client.put(
            "/v1/governance/policy",
            headers=HEADERS,
            json={"fuji_rules": {"pii_check": True}},
        )
        body = resp.json()
        assert body["policy"]["updated_at"] != ""
        assert body["policy"]["updated_by"] == "api"

    def test_put_requires_api_key(self):
        resp = client.put("/v1/governance/policy", json={})
        assert resp.status_code in (401, 500)

    def test_roundtrip_get_after_put(self):
        client.put(
            "/v1/governance/policy",
            headers=HEADERS,
            json={"risk_thresholds": {"warn_upper": 0.55}},
        )
        resp = client.get("/v1/governance/policy", headers=HEADERS)
        assert resp.json()["policy"]["risk_thresholds"]["warn_upper"] == 0.55


class TestGovernanceModule:
    def test_get_policy_returns_dict(self):
        result = gov_mod.get_policy()
        assert isinstance(result, dict)
        assert "fuji_rules" in result

    def test_update_policy_merges(self):
        result = gov_mod.update_policy({"fuji_rules": {"pii_check": False}})
        assert result["fuji_rules"]["pii_check"] is False
        assert result["fuji_rules"]["self_harm_block"] is True

    def test_pydantic_validation(self):
        policy = gov_mod.GovernancePolicy()
        assert policy.fuji_rules.pii_check is True
        assert policy.risk_thresholds.allow_upper == 0.40
        assert policy.auto_stop.enabled is True
        assert policy.log_retention.retention_days == 90
