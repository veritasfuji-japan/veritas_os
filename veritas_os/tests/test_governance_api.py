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
from pydantic import ValidationError

os.environ["VERITAS_API_KEY"] = "test-governance-key"

from veritas_os.api import governance as gov_mod
from veritas_os.api import server as srv

client = TestClient(srv.app)
HEADERS = {"X-API-Key": "test-governance-key"}


@pytest.fixture(autouse=True)
def _temp_policy(tmp_path: Path, monkeypatch):
    """Use a temporary governance.json for every test."""
    monkeypatch.setenv("VERITAS_API_KEY", "test-governance-key")
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

    def test_load_returns_defaults_when_file_missing(self, tmp_path, monkeypatch):
        """When governance file does not exist, return defaults."""
        missing = tmp_path / "does_not_exist.json"
        with patch.object(gov_mod, "_DEFAULT_POLICY_PATH", missing):
            policy = gov_mod.get_policy()
        assert policy["version"] == "governance_v1"
        assert policy["fuji_rules"]["pii_check"] is True

    def test_load_handles_corrupt_json(self, tmp_path):
        """When governance file has bad JSON, return defaults."""
        bad = tmp_path / "bad.json"
        bad.write_text("NOT-VALID-JSON!!!")
        with patch.object(gov_mod, "_DEFAULT_POLICY_PATH", bad):
            policy = gov_mod.get_policy()
        assert policy["version"] == "governance_v1"

    def test_update_creates_missing_nested_key(self, tmp_path):
        """When nested key is non-dict, update_policy creates it."""
        p = tmp_path / "gov.json"
        p.write_text(json.dumps({"fuji_rules": "broken", "version": "v0"}))
        with patch.object(gov_mod, "_DEFAULT_POLICY_PATH", p):
            result = gov_mod.update_policy({"fuji_rules": {"pii_check": False}})
        assert result["fuji_rules"]["pii_check"] is False

    def test_get_value_drift_with_no_data(self, tmp_path):
        """When no value history exists, endpoint helper returns no_data."""
        with patch.object(gov_mod, "_VALUE_HISTORY_PATHS", (tmp_path / "missing.json",)):
            result = gov_mod.get_value_drift()
        assert result["status"] == "no_data"
        assert result["baseline"] == 0.5
        assert result["latest_ema"] == 0.5

    def test_get_value_drift_with_history(self, tmp_path):
        """Value drift is calculated from the latest EMA and baseline."""
        value_file = tmp_path / "value_stats.json"
        value_file.write_text(json.dumps({"history": [{"ema": 0.4, "timestamp": "t1"}, {"ema": 0.6, "timestamp": "t2"}]}))
        with patch.object(gov_mod, "_VALUE_HISTORY_PATHS", (value_file,)):
            result = gov_mod.get_value_drift(telos_baseline=0.5)
        assert result["status"] == "ok"
        assert result["latest_ema"] == 0.6
        assert result["drift_percent"] == 20.0

    def test_update_overrides_version(self, tmp_path):
        """version scalar key is overridden by patch."""
        p = tmp_path / "gov.json"
        p.write_text(json.dumps(gov_mod.GovernancePolicy().model_dump()))
        with patch.object(gov_mod, "_DEFAULT_POLICY_PATH", p):
            result = gov_mod.update_policy({"version": "custom_v9"})
        assert result["version"] == "custom_v9"

    def test_update_policy_rejects_non_object_nested_patch(self):
        """Nested governance sections must be provided as objects."""
        with pytest.raises(ValueError, match="fuji_rules must be an object"):
            gov_mod.update_policy({"fuji_rules": True})

    def test_update_policy_validates_merged_nested_patch(self):
        """Merged nested section is validated before assignment and save."""
        with pytest.raises(ValidationError):
            gov_mod.update_policy({"risk_thresholds": {"allow_upper": 1.5}})



# ----------------------------------------------------------------
# Server governance endpoint error paths
# ----------------------------------------------------------------


class TestGovernanceValueDriftEndpoint:
    def test_get_value_drift_success(self, monkeypatch):
        monkeypatch.setattr(srv, "get_value_drift", lambda telos_baseline=0.5: {
            "baseline": telos_baseline,
            "latest_ema": 0.55,
            "drift_percent": 10.0,
            "history": [{"ema": 0.55, "timestamp": "t1"}],
            "status": "ok",
        })
        resp = client.get("/v1/governance/value-drift", headers=HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["value_drift"]["status"] == "ok"

    def test_get_value_drift_error(self, monkeypatch):
        def boom(telos_baseline=0.5):
            raise RuntimeError("unavailable")

        monkeypatch.setattr(srv, "get_value_drift", boom)
        resp = client.get("/v1/governance/value-drift", headers=HEADERS)
        assert resp.status_code == 500
        body = resp.json()
        assert body["ok"] is False

class TestGovernanceServerErrors:
    def test_get_policy_internal_error(self, monkeypatch):
        """GET /v1/governance/policy returns 500 on internal error."""
        def boom():
            raise RuntimeError("db down")
        monkeypatch.setattr(srv, "get_policy", boom)
        resp = client.get("/v1/governance/policy", headers=HEADERS)
        assert resp.status_code == 500
        body = resp.json()
        assert body["ok"] is False
        assert "error" in body

    def test_put_policy_internal_error(self, monkeypatch):
        """PUT /v1/governance/policy returns 500 on internal error."""
        def boom(body):
            raise RuntimeError("write fail")
        monkeypatch.setattr(srv, "update_policy", boom)
        resp = client.put(
            "/v1/governance/policy",
            headers=HEADERS,
            json={"fuji_rules": {}},
        )
        assert resp.status_code == 500
        body = resp.json()
        assert body["ok"] is False


# ----------------------------------------------------------------
# fuji_validate error-path coverage
# ----------------------------------------------------------------

class TestFujiValidateErrorPaths:
    def test_runtime_error_returns_error_structure(self, monkeypatch):
        """Non-impl RuntimeError in fuji_validate → 200 with error."""
        fake = type("F", (), {"validate_action": None, "validate": None})()
        monkeypatch.setattr(srv, "get_fuji_core", lambda: fake)
        monkeypatch.setattr(
            srv, "_call_fuji",
            lambda fc, action, ctx: (_ for _ in ()).throw(RuntimeError("random")),
        )
        resp = client.post("/v1/fuji/validate", headers=HEADERS, json={"action": "x"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "error"
        assert body["reasons"] == ["Validation failed"]

    def test_general_exception_returns_error_structure(self, monkeypatch):
        """General exception in fuji_validate → 200 with error."""
        fake = type("F", (), {"validate_action": None, "validate": None})()
        monkeypatch.setattr(srv, "get_fuji_core", lambda: fake)
        monkeypatch.setattr(
            srv, "_call_fuji",
            lambda fc, action, ctx: (_ for _ in ()).throw(ValueError("oops")),
        )
        resp = client.post("/v1/fuji/validate", headers=HEADERS, json={"action": "x"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "error"
