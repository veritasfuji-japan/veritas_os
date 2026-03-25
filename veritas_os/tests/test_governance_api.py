# veritas_os/tests/test_governance_api.py
"""Tests for Governance Policy API endpoints."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from veritas_os.api import governance as gov_mod
from veritas_os.api import server as srv

client = TestClient(srv.app)
HEADERS = {"X-API-Key": "test-governance-key", "X-Role": "admin"}


def _approved(payload: dict | None = None) -> dict:
    """Attach a valid 4-eyes approval block to a governance payload."""
    base = payload.copy() if payload else {}
    base["approvals"] = [
        {"reviewer": "alice", "signature": "sig-alice"},
        {"reviewer": "bob", "signature": "sig-bob"},
    ]
    return base


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
            json=_approved({"fuji_rules": {"pii_check": False}}),
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
            json=_approved({"risk_thresholds": {"allow_upper": 0.50}}),
        )
        assert resp.status_code == 200
        assert resp.json()["policy"]["risk_thresholds"]["allow_upper"] == 0.50

    def test_put_updates_auto_stop(self):
        resp = client.put(
            "/v1/governance/policy",
            headers=HEADERS,
            json=_approved({"auto_stop": {"enabled": False, "max_risk_score": 0.70}}),
        )
        body = resp.json()
        assert body["policy"]["auto_stop"]["enabled"] is False
        assert body["policy"]["auto_stop"]["max_risk_score"] == 0.70

    def test_put_updates_log_retention(self):
        resp = client.put(
            "/v1/governance/policy",
            headers=HEADERS,
            json=_approved({"log_retention": {"retention_days": 180, "audit_level": "summary"}}),
        )
        body = resp.json()
        assert body["policy"]["log_retention"]["retention_days"] == 180
        assert body["policy"]["log_retention"]["audit_level"] == "summary"

    def test_put_sets_updated_at(self):
        resp = client.put(
            "/v1/governance/policy",
            headers=HEADERS,
            json=_approved({"fuji_rules": {"pii_check": True}}),
        )
        body = resp.json()
        assert body["policy"]["updated_at"] != ""
        assert body["policy"]["updated_by"] == "api"



    def test_put_rejects_without_four_eyes_approval(self):
        resp = client.put(
            "/v1/governance/policy",
            headers=HEADERS,
            json={"fuji_rules": {"pii_check": False}},
        )
        assert resp.status_code == 403
        assert resp.json()["ok"] is False

    def test_put_rejects_duplicate_reviewer_in_approvals(self):
        resp = client.put(
            "/v1/governance/policy",
            headers=HEADERS,
            json={
                "fuji_rules": {"pii_check": False},
                "approvals": [
                    {"reviewer": "alice", "signature": "sig-a"},
                    {"reviewer": "alice", "signature": "sig-b"},
                ],
            },
        )
        assert resp.status_code == 403
        assert resp.json()["ok"] is False

    def test_put_does_not_expose_permission_error_detail(self, monkeypatch):
        """Permission errors are sanitized before returning to API clients."""

        def sensitive_error(_body):
            raise PermissionError("secret stack trace details")

        monkeypatch.setattr(srv, "enforce_four_eyes_approval", sensitive_error)
        resp = client.put(
            "/v1/governance/policy",
            headers=HEADERS,
            json={"fuji_rules": {"pii_check": False}},
        )
        assert resp.status_code == 403
        body = resp.json()
        assert body["ok"] is False
        assert body["error"] == "governance approval validation failed"
        assert "secret" not in json.dumps(body)

    def test_put_requires_api_key(self):
        resp = client.put("/v1/governance/policy", json={})
        assert resp.status_code in (401, 500)

    def test_roundtrip_get_after_put(self):
        client.put(
            "/v1/governance/policy",
            headers=HEADERS,
            json=_approved({"risk_thresholds": {"warn_upper": 0.55}}),
        )
        resp = client.get("/v1/governance/policy", headers=HEADERS)
        assert resp.json()["policy"]["risk_thresholds"]["warn_upper"] == 0.55


class TestGovernanceModule:
    def test_get_policy_returns_dict(self):
        result = gov_mod.get_policy()
        assert isinstance(result, dict)
        assert "fuji_rules" in result

    def test_update_policy_merges(self):
        result = gov_mod.update_policy(_approved({"fuji_rules": {"pii_check": False}}))
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
            result = gov_mod.update_policy(_approved({"fuji_rules": {"pii_check": False}}))
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
            result = gov_mod.update_policy(_approved({"version": "custom_v9"}))
        assert result["version"] == "custom_v9"

    def test_update_policy_rejects_non_object_nested_patch(self):
        """Nested governance sections must be provided as objects."""
        with pytest.raises(ValueError, match="fuji_rules must be an object"):
            gov_mod.update_policy(_approved({"fuji_rules": True}))

    def test_update_policy_validates_merged_nested_patch(self):
        """Merged nested section is validated before assignment and save."""
        with pytest.raises(ValidationError):
            gov_mod.update_policy(_approved({"risk_thresholds": {"allow_upper": 1.5}}))



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
            json=_approved({"fuji_rules": {}}),
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
        monkeypatch.setenv("VERITAS_ENABLE_DIRECT_FUJI_API", "1")
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
        monkeypatch.setenv("VERITAS_ENABLE_DIRECT_FUJI_API", "1")
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



def test_get_rejects_without_governance_role() -> None:
    """Governance API should reject requests without RBAC role header."""
    resp = client.get("/v1/governance/policy", headers={"X-API-Key": "test-governance-key"})
    assert resp.status_code == 403


def test_put_rejects_tenant_mismatch(monkeypatch) -> None:
    """Governance API should enforce tenant ABAC when configured."""
    monkeypatch.setenv("VERITAS_GOVERNANCE_TENANT_ID", "tenant-a")
    headers = {"X-API-Key": "test-governance-key", "X-Role": "admin", "X-Tenant-Id": "tenant-b"}
    resp = client.put(
        "/v1/governance/policy",
        headers=headers,
        json=_approved({"fuji_rules": {"pii_check": False}}),
    )
    assert resp.status_code == 403


class TestGovernanceHardeningBranches:
    """Focused branch tests for governance core defensive paths."""

    def test_enforce_four_eyes_rejects_insufficient_approvals(self):
        with pytest.raises(PermissionError, match="exactly two approvals"):
            gov_mod.enforce_four_eyes_approval({
                "approvals": [{"reviewer": "alice", "signature": "sig-a"}]
            })

    def test_enforce_four_eyes_rejects_duplicate_signatures(self):
        with pytest.raises(PermissionError, match="two distinct signatures"):
            gov_mod.enforce_four_eyes_approval(
                {
                    "approvals": [
                        {"reviewer": "alice", "signature": "shared"},
                        {"reviewer": "bob", "signature": "shared"},
                    ]
                }
            )

    def test_enforce_four_eyes_can_be_disabled(self, monkeypatch):
        monkeypatch.setenv("VERITAS_GOVERNANCE_REQUIRE_FOUR_EYES", "0")
        gov_mod.enforce_four_eyes_approval({})

    def test_update_policy_hot_reload_callback_failure_is_degraded(self, tmp_path):
        policy_path = tmp_path / "gov.json"
        history_path = tmp_path / "history.jsonl"
        policy_path.write_text(json.dumps(gov_mod.GovernancePolicy().model_dump()))

        observed = []

        def failing_cb(_policy):
            raise RuntimeError("reload failed")

        def success_cb(policy):
            observed.append(policy["fuji_rules"]["pii_check"])

        with patch.object(gov_mod, "_DEFAULT_POLICY_PATH", policy_path), patch.object(
            gov_mod, "_POLICY_HISTORY_PATH", history_path
        ), patch.object(gov_mod, "_policy_update_callbacks", [failing_cb, success_cb]):
            updated = gov_mod.update_policy(
                _approved({"fuji_rules": {"pii_check": False}, "updated_by": "x" * 500})
            )

        assert updated["fuji_rules"]["pii_check"] is False
        assert observed == [False]
        assert len(updated["updated_by"]) == 200

    def test_get_policy_history_returns_empty_when_missing(self, tmp_path):
        with patch.object(gov_mod, "_POLICY_HISTORY_PATH", tmp_path / "missing.jsonl"):
            assert gov_mod.get_policy_history(limit=10) == []

    def test_get_policy_history_skips_invalid_lines_and_applies_limit(self, tmp_path):
        history_path = tmp_path / "history.jsonl"
        history_path.write_text(
            "\n".join(
                [
                    '{"new_version": "v1"}',
                    'NOT-JSON',
                    '{"new_version": "v2"}',
                    '{"new_version": "v3"}',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        with patch.object(gov_mod, "_POLICY_HISTORY_PATH", history_path):
            records = gov_mod.get_policy_history(limit=2)

        assert [record["new_version"] for record in records] == ["v3", "v2"]

    def test_get_policy_history_read_error_returns_empty(self, monkeypatch, tmp_path):
        history_path = tmp_path / "history.jsonl"
        history_path.write_text('{"new_version": "v1"}\n', encoding="utf-8")

        def _boom(*_args, **_kwargs):
            raise OSError("disk error")

        monkeypatch.setattr(Path, "read_text", _boom)
        with patch.object(gov_mod, "_POLICY_HISTORY_PATH", history_path):
            assert gov_mod.get_policy_history(limit=5) == []

    def test_get_value_drift_zero_baseline_edge_case(self, tmp_path):
        value_file = tmp_path / "value_stats.json"
        value_file.write_text(
            json.dumps({"history": [{"ema": 0.9, "timestamp": "t1"}]}),
            encoding="utf-8",
        )
        with patch.object(gov_mod, "_VALUE_HISTORY_PATHS", (value_file,)):
            result = gov_mod.get_value_drift(telos_baseline=0.0)

        assert result["latest_ema"] == 0.9
        assert result["drift_percent"] == 0.0

    def test_get_value_drift_caps_extreme_drift(self, tmp_path):
        value_file = tmp_path / "value_stats.json"
        value_file.write_text(
            json.dumps({"history": [{"ema": 1.0, "timestamp": "t1"}]}),
            encoding="utf-8",
        )
        with patch.object(gov_mod, "_VALUE_HISTORY_PATHS", (value_file,)):
            result = gov_mod.get_value_drift(telos_baseline=0.001)

        assert result["drift_percent"] == 1000.0

    def test_load_value_history_fallback_to_secondary_path(self, tmp_path):
        broken = tmp_path / "broken.json"
        valid = tmp_path / "valid.json"
        broken.write_text("{not-json}", encoding="utf-8")
        valid.write_text(
            json.dumps([{"ema": 0.2, "created_at": "2026-01-01T00:00:00Z"}]),
            encoding="utf-8",
        )

        with patch.object(gov_mod, "_VALUE_HISTORY_PATHS", (broken, valid)):
            result = gov_mod.get_value_drift(telos_baseline=0.5)

        assert result["status"] == "ok"
        assert result["history"][0]["timestamp"] == "2026-01-01T00:00:00Z"

    def test_load_value_history_coerces_and_filters_invalid_points(self, tmp_path):
        value_file = tmp_path / "value_stats.json"
        value_file.write_text(
            json.dumps(
                {
                    "history": [
                        {"ema": -3, "ts": "first"},
                        {"ema": 2, "timestamp": "second"},
                        {"ema": "bad"},
                        "invalid",
                        {"ema": 0.55},
                    ]
                }
            ),
            encoding="utf-8",
        )

        with patch.object(gov_mod, "_VALUE_HISTORY_PATHS", (value_file,)):
            result = gov_mod.get_value_drift(telos_baseline=0.5)

        assert [point["ema"] for point in result["history"]] == [0.0, 1.0, 0.55]
        assert result["history"][-1]["timestamp"] == "point-4"

