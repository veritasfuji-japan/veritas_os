# veritas_os/tests/test_rbac.py
"""Tests for RBAC: role definitions, permission resolution, and endpoint guards."""
from __future__ import annotations

import json
import os
from unittest import mock

import pytest

from veritas_os.api.rbac import Permission, Role, ROLE_PERMISSIONS, RBACPolicy
from veritas_os.api.auth import (
    _parse_api_keys_config,
    resolve_role_for_key,
    _resolve_role_from_request,
    require_permission,
    _record_auth_reject_reason,
    _snapshot_auth_reject_reason_metrics,
)


# ==============================
# rbac.py — Role & Permission definitions
# ==============================

class TestRoleEnum:
    def test_all_roles_defined(self):
        assert set(Role) == {Role.admin, Role.operator, Role.auditor}

    def test_role_values(self):
        assert Role.admin.value == "admin"
        assert Role.operator.value == "operator"
        assert Role.auditor.value == "auditor"


class TestPermissionEnum:
    def test_all_permissions_defined(self):
        expected = {
            "decide", "memory_read", "memory_write",
            "trust_log_read", "governance_read", "governance_write",
            "config_write", "compliance_read",
        }
        assert {p.value for p in Permission} == expected


class TestRolePermissions:
    def test_admin_has_all_permissions(self):
        assert ROLE_PERMISSIONS[Role.admin] == frozenset(Permission)

    def test_operator_permissions(self):
        expected = {
            Permission.decide,
            Permission.memory_read,
            Permission.memory_write,
            Permission.trust_log_read,
        }
        assert ROLE_PERMISSIONS[Role.operator] == frozenset(expected)

    def test_operator_cannot_write_governance(self):
        assert Permission.governance_write not in ROLE_PERMISSIONS[Role.operator]
        assert Permission.config_write not in ROLE_PERMISSIONS[Role.operator]

    def test_auditor_permissions(self):
        expected = {
            Permission.trust_log_read,
            Permission.governance_read,
            Permission.compliance_read,
        }
        assert ROLE_PERMISSIONS[Role.auditor] == frozenset(expected)

    def test_auditor_cannot_decide(self):
        assert Permission.decide not in ROLE_PERMISSIONS[Role.auditor]

    def test_auditor_cannot_write(self):
        assert Permission.memory_write not in ROLE_PERMISSIONS[Role.auditor]
        assert Permission.governance_write not in ROLE_PERMISSIONS[Role.auditor]
        assert Permission.config_write not in ROLE_PERMISSIONS[Role.auditor]


class TestRBACPolicy:
    def test_default_policy_admin(self):
        policy = RBACPolicy()
        assert policy.has_permission(Role.admin, Permission.config_write) is True

    def test_default_policy_auditor_denied(self):
        policy = RBACPolicy()
        assert policy.has_permission(Role.auditor, Permission.decide) is False

    def test_custom_policy(self):
        custom = RBACPolicy(mapping={
            Role.admin: frozenset({Permission.decide}),
            Role.operator: frozenset(),
            Role.auditor: frozenset(),
        })
        assert custom.has_permission(Role.admin, Permission.decide) is True
        assert custom.has_permission(Role.admin, Permission.config_write) is False


# ==============================
# auth.py — Multi-key parsing
# ==============================

class TestParseApiKeysConfig:
    def test_empty_env(self):
        with mock.patch.dict(os.environ, {"VERITAS_API_KEYS": ""}, clear=False):
            assert _parse_api_keys_config() == []

    def test_unset_env(self):
        env = {k: v for k, v in os.environ.items() if k != "VERITAS_API_KEYS"}
        with mock.patch.dict(os.environ, env, clear=True):
            assert _parse_api_keys_config() == []

    def test_valid_json(self):
        keys_json = json.dumps([
            {"key": "sk-admin-xxx", "role": "admin"},
            {"key": "sk-op-yyy", "role": "operator"},
        ])
        with mock.patch.dict(os.environ, {"VERITAS_API_KEYS": keys_json}, clear=False):
            result = _parse_api_keys_config()
            assert len(result) == 2
            assert result[0]["role"] == "admin"
            assert result[1]["role"] == "operator"

    def test_invalid_json_raises(self):
        with mock.patch.dict(os.environ, {"VERITAS_API_KEYS": "not-json"}, clear=False):
            with pytest.raises(ValueError, match="not valid JSON"):
                _parse_api_keys_config()

    def test_not_a_list_raises(self):
        with mock.patch.dict(os.environ, {"VERITAS_API_KEYS": '{"key":"x"}'}, clear=False):
            with pytest.raises(ValueError, match="must be a JSON array"):
                _parse_api_keys_config()

    def test_invalid_role_raises(self):
        keys_json = json.dumps([{"key": "sk-xxx", "role": "superuser"}])
        with mock.patch.dict(os.environ, {"VERITAS_API_KEYS": keys_json}, clear=False):
            with pytest.raises(ValueError, match="Invalid role"):
                _parse_api_keys_config()

    def test_missing_key_field_raises(self):
        keys_json = json.dumps([{"role": "admin"}])
        with mock.patch.dict(os.environ, {"VERITAS_API_KEYS": keys_json}, clear=False):
            with pytest.raises(ValueError, match="must have 'key' and 'role'"):
                _parse_api_keys_config()

    def test_empty_key_raises(self):
        keys_json = json.dumps([{"key": "", "role": "admin"}])
        with mock.patch.dict(os.environ, {"VERITAS_API_KEYS": keys_json}, clear=False):
            with pytest.raises(ValueError, match="Empty key"):
                _parse_api_keys_config()


# ==============================
# auth.py — Role resolution
# ==============================

class TestResolveRoleForKey:
    def test_multi_key_admin(self):
        keys_json = json.dumps([
            {"key": "sk-admin-abc", "role": "admin"},
            {"key": "sk-op-def", "role": "operator"},
        ])
        with mock.patch.dict(os.environ, {"VERITAS_API_KEYS": keys_json}, clear=False):
            assert resolve_role_for_key("sk-admin-abc") == Role.admin

    def test_multi_key_operator(self):
        keys_json = json.dumps([
            {"key": "sk-admin-abc", "role": "admin"},
            {"key": "sk-op-def", "role": "operator"},
        ])
        with mock.patch.dict(os.environ, {"VERITAS_API_KEYS": keys_json}, clear=False):
            assert resolve_role_for_key("sk-op-def") == Role.operator

    def test_multi_key_auditor(self):
        keys_json = json.dumps([{"key": "sk-audit-ghi", "role": "auditor"}])
        with mock.patch.dict(os.environ, {"VERITAS_API_KEYS": keys_json}, clear=False):
            assert resolve_role_for_key("sk-audit-ghi") == Role.auditor

    def test_legacy_single_key_becomes_admin(self):
        """Backward compat: VERITAS_API_KEY-only config resolves to admin."""
        env = {k: v for k, v in os.environ.items() if k != "VERITAS_API_KEYS"}
        env["VERITAS_API_KEY"] = "legacy-key-123"
        with mock.patch.dict(os.environ, env, clear=True):
            assert resolve_role_for_key("legacy-key-123") == Role.admin

    def test_unknown_key_raises(self):
        env = {k: v for k, v in os.environ.items() if k != "VERITAS_API_KEYS"}
        env["VERITAS_API_KEY"] = "real-key"
        with mock.patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="does not match"):
                resolve_role_for_key("wrong-key")

    def test_empty_key_raises(self):
        with pytest.raises(ValueError, match="empty api key"):
            resolve_role_for_key("")


# ==============================
# auth.py — require_permission dependency
# ==============================

class TestRequirePermission:
    """Test the require_permission factory returns a callable that checks RBAC."""

    def _make_request_stub(self, api_key: str):
        """Create a minimal request-like object for testing."""

        class _State:
            rbac_role = None

        class _Req:
            state = _State()

        return _Req()

    def test_admin_allowed_decide(self):
        keys_json = json.dumps([{"key": "sk-admin", "role": "admin"}])
        with mock.patch.dict(os.environ, {"VERITAS_API_KEYS": keys_json}, clear=False):
            checker = require_permission(Permission.decide)
            req = self._make_request_stub("sk-admin")
            result = checker(request=req, x_api_key="sk-admin")
            assert result is True
            assert req.state.rbac_role == "admin"

    def test_operator_allowed_decide(self):
        keys_json = json.dumps([{"key": "sk-op", "role": "operator"}])
        with mock.patch.dict(os.environ, {"VERITAS_API_KEYS": keys_json}, clear=False):
            checker = require_permission(Permission.decide)
            req = self._make_request_stub("sk-op")
            result = checker(request=req, x_api_key="sk-op")
            assert result is True

    def test_auditor_denied_decide(self):
        from fastapi import HTTPException

        keys_json = json.dumps([{"key": "sk-audit", "role": "auditor"}])
        with mock.patch.dict(os.environ, {"VERITAS_API_KEYS": keys_json}, clear=False):
            checker = require_permission(Permission.decide)
            req = self._make_request_stub("sk-audit")
            with pytest.raises(HTTPException) as exc_info:
                checker(request=req, x_api_key="sk-audit")
            assert exc_info.value.status_code == 403
            assert "permission" in exc_info.value.detail.lower()

    def test_auditor_allowed_trust_log_read(self):
        keys_json = json.dumps([{"key": "sk-audit", "role": "auditor"}])
        with mock.patch.dict(os.environ, {"VERITAS_API_KEYS": keys_json}, clear=False):
            checker = require_permission(Permission.trust_log_read)
            req = self._make_request_stub("sk-audit")
            result = checker(request=req, x_api_key="sk-audit")
            assert result is True

    def test_auditor_denied_governance_write(self):
        from fastapi import HTTPException

        keys_json = json.dumps([{"key": "sk-audit", "role": "auditor"}])
        with mock.patch.dict(os.environ, {"VERITAS_API_KEYS": keys_json}, clear=False):
            checker = require_permission(Permission.governance_write)
            req = self._make_request_stub("sk-audit")
            with pytest.raises(HTTPException) as exc_info:
                checker(request=req, x_api_key="sk-audit")
            assert exc_info.value.status_code == 403

    def test_operator_denied_config_write(self):
        from fastapi import HTTPException

        keys_json = json.dumps([{"key": "sk-op", "role": "operator"}])
        with mock.patch.dict(os.environ, {"VERITAS_API_KEYS": keys_json}, clear=False):
            checker = require_permission(Permission.config_write)
            req = self._make_request_stub("sk-op")
            with pytest.raises(HTTPException) as exc_info:
                checker(request=req, x_api_key="sk-op")
            assert exc_info.value.status_code == 403

    def test_insufficient_permission_records_metric(self):
        from fastapi import HTTPException

        keys_json = json.dumps([{"key": "sk-audit", "role": "auditor"}])
        with mock.patch.dict(os.environ, {"VERITAS_API_KEYS": keys_json}, clear=False):
            checker = require_permission(Permission.decide)
            req = self._make_request_stub("sk-audit")
            with pytest.raises(HTTPException):
                checker(request=req, x_api_key="sk-audit")
            snap = _snapshot_auth_reject_reason_metrics()
            assert snap.get("insufficient_permission", 0) >= 1


# ==============================
# Backward compatibility
# ==============================

class TestBackwardCompat:
    """VERITAS_API_KEY (single key) still works as admin."""

    def test_single_key_resolves_admin(self):
        env = {k: v for k, v in os.environ.items() if k != "VERITAS_API_KEYS"}
        env["VERITAS_API_KEY"] = "compat-key-456"
        with mock.patch.dict(os.environ, env, clear=True):
            assert resolve_role_for_key("compat-key-456") == Role.admin

    def test_single_key_passes_permission_check(self):
        env = {k: v for k, v in os.environ.items() if k != "VERITAS_API_KEYS"}
        env["VERITAS_API_KEY"] = "compat-key-456"
        with mock.patch.dict(os.environ, env, clear=True):
            checker = require_permission(Permission.config_write)

            class _State:
                rbac_role = None

            class _Req:
                state = _State()

            req = _Req()
            result = checker(request=req, x_api_key="compat-key-456")
            assert result is True
            assert req.state.rbac_role == "admin"


# ==============================
# Error handling edge cases
# ==============================

class TestErrorHandling:
    def test_malformed_json_env_gracefully_handled_in_role_resolution(self):
        """When VERITAS_API_KEYS is malformed, resolve_role_for_key falls back to single key."""
        env = dict(os.environ)
        env["VERITAS_API_KEYS"] = "{bad json"
        env["VERITAS_API_KEY"] = "fallback-key"
        with mock.patch.dict(os.environ, env, clear=True):
            # Should fall back to single-key match
            assert resolve_role_for_key("fallback-key") == Role.admin

    def test_malformed_json_env_still_rejects_wrong_key(self):
        env = dict(os.environ)
        env["VERITAS_API_KEYS"] = "{bad json"
        env["VERITAS_API_KEY"] = "fallback-key"
        with mock.patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="does not match"):
                resolve_role_for_key("wrong-key")

    def test_parse_api_keys_non_dict_entry_raises(self):
        keys_json = json.dumps(["not-a-dict"])
        with mock.patch.dict(os.environ, {"VERITAS_API_KEYS": keys_json}, clear=False):
            with pytest.raises(ValueError, match="must have 'key' and 'role'"):
                _parse_api_keys_config()
