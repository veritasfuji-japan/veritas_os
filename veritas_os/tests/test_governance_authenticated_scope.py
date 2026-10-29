"""Governance role/tenant claims must be backed by the authenticated key configuration."""

import json
import os

from fastapi.testclient import TestClient
import pytest

from veritas_os.api import server


KEY = "governance-scope-test-only"


@pytest.fixture
def scope_api(monkeypatch):
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.delenv("VERITAS_POSTURE", raising=False)
    monkeypatch.setenv("VERITAS_API_KEY", "unrelated-legacy-test-only")
    monkeypatch.setenv("VERITAS_GOVERNANCE_ENFORCE_RBAC", "1")
    monkeypatch.setenv("VERITAS_GOVERNANCE_ALLOWED_ROLES", "admin,compliance_owner")
    monkeypatch.delenv("VERITAS_GOVERNANCE_TENANT_ID", raising=False)
    monkeypatch.setattr(server.app.state, "security_startup_complete", True, raising=False)
    monkeypatch.setattr(server.app.state, "security_startup_pid", os.getpid(), raising=False)
    calls = []

    def read(**_kwargs):
        calls.append("read")
        return {"synthetic": True}

    def approval(_body):
        calls.append("approval")
        raise PermissionError("synthetic stop before any business mutation")

    monkeypatch.setattr(server, "get_value_drift", read)
    monkeypatch.setattr(server, "enforce_four_eyes_approval", approval)
    return TestClient(server.app), calls


@pytest.mark.parametrize("operation", ["read", "write"])
@pytest.mark.parametrize("case", [
    "forged-role", "forged-tenant", "unbound-key", "legacy-key",
    "wrong-header", "missing-header", "unallowed-actual-role",
])
def test_governance_rejects_untrusted_scope_before_handler(monkeypatch, scope_api, operation, case):
    client, calls = scope_api
    entry = {"key": KEY, "role": "auditor" if case == "forged-role" else "admin"}
    headers = {"X-API-Key": KEY, "X-Role": "admin"}
    if case == "unallowed-actual-role":
        monkeypatch.setenv("VERITAS_GOVERNANCE_ALLOWED_ROLES", "compliance_owner")
        headers["X-Role"] = "compliance_owner"
    elif case != "forged-role":
        monkeypatch.setenv("VERITAS_GOVERNANCE_TENANT_ID", "tenant-b")
        headers["X-Tenant-Id"] = "tenant-b"
        if case == "forged-tenant":
            entry["tenant_id"] = "tenant-a"
        elif case in {"wrong-header", "missing-header"}:
            entry["tenant_id"] = "tenant-b"
            if case == "wrong-header":
                headers["X-Tenant-Id"] = "tenant-a"
            else:
                headers.pop("X-Tenant-Id")
    monkeypatch.setenv("VERITAS_API_KEYS", json.dumps([entry]))
    if case == "legacy-key":
        monkeypatch.setenv("VERITAS_API_KEY", KEY)
        monkeypatch.setenv("VERITAS_API_KEYS", "[]")
    response = client.get("/v1/governance/value-drift", headers=headers) if operation == "read" else client.put(
        "/v1/governance/policy", headers=headers, json={},
    )
    assert response.status_code == 403
    assert calls == [], "untrusted role/tenant reached the governance handler"


@pytest.mark.parametrize("role,scoped,legacy", [
    ("admin", False, True), ("admin", True, False), ("auditor", True, False),
])
def test_governance_accepts_explicitly_authorized_key(monkeypatch, scope_api, role, scoped, legacy):
    client, calls = scope_api
    entry = {"key": KEY, "role": role}
    headers = {"X-API-Key": KEY, "X-Role": role}
    monkeypatch.setenv("VERITAS_GOVERNANCE_ALLOWED_ROLES", "admin,auditor")
    if scoped:
        entry["tenant_id"] = "tenant-b"
        monkeypatch.setenv("VERITAS_GOVERNANCE_TENANT_ID", "tenant-b")
        headers["X-Tenant-Id"] = "tenant-b"
    monkeypatch.setenv("VERITAS_API_KEYS", json.dumps([] if legacy else [entry]))
    if legacy:
        monkeypatch.setenv("VERITAS_API_KEY", KEY)
    response = client.get("/v1/governance/value-drift", headers=headers)
    assert response.status_code == 200
    assert response.json()["value_drift"] == {"synthetic": True}
    assert calls == ["read"]


@pytest.mark.parametrize("tenant", [None, False, 0, [], {}, "", "   "])
def test_key_tenant_config_rejects_invalid_values(monkeypatch, tenant):
    from veritas_os.api.auth import _parse_api_keys_config, resolve_tenant_for_key

    monkeypatch.setenv("VERITAS_API_KEYS", json.dumps([
        {"key": KEY, "role": "admin", "tenant_id": tenant},
    ]))
    with pytest.raises(ValueError, match="tenant_id"):
        _parse_api_keys_config()
    with pytest.raises(ValueError, match="tenant_id"):
        resolve_tenant_for_key(KEY)


def test_key_tenant_config_roundtrip_and_legacy_boundary(monkeypatch):
    from pathlib import Path

    from veritas_os.api.auth import _parse_api_keys_config, resolve_tenant_for_key

    sample = (Path(__file__).resolve().parents[2] / ".env.example").read_text()
    sample_json = next(line.split("=", 1)[1] for line in sample.splitlines()
                       if line.startswith("# VERITAS_API_KEYS="))
    monkeypatch.setenv("VERITAS_API_KEYS", sample_json)
    assert _parse_api_keys_config() == json.loads(sample_json)
    assert _parse_api_keys_config()[0]["tenant_id"] == "tenant-a"
    entries = [
        {"key": KEY, "role": "admin", "tenant_id": "tenant-a"},
        {"key": "unbound-test-only", "role": "auditor"},
    ]
    monkeypatch.setenv("VERITAS_API_KEYS", json.dumps(entries))
    assert json.loads(json.dumps(_parse_api_keys_config())) == entries
    assert resolve_tenant_for_key(KEY) == "tenant-a"
    assert resolve_tenant_for_key("unbound-test-only") is None
    monkeypatch.setenv("VERITAS_API_KEY", "legacy-test-only")
    monkeypatch.setenv("VERITAS_GOVERNANCE_TENANT_ID", "tenant-a")
    assert resolve_tenant_for_key("legacy-test-only") is None
    monkeypatch.setenv("VERITAS_API_KEYS", "{malformed")
    with pytest.raises(ValueError):
        resolve_tenant_for_key("legacy-test-only")


def test_governance_guard_requires_authenticated_context_even_with_bypass(monkeypatch):
    from fastapi import HTTPException
    from starlette.requests import Request

    from veritas_os.api.routes_governance import require_governance_access

    monkeypatch.setenv("VERITAS_API_KEY", KEY)
    monkeypatch.setenv("VERITAS_GOVERNANCE_ENFORCE_RBAC", "0")
    monkeypatch.setenv("VERITAS_GOVERNANCE_ALLOW_RBAC_BYPASS", "1")
    request = Request({"type": "http", "headers": [(b"x-api-key", KEY.encode())]})
    with pytest.raises(HTTPException) as caught:
        require_governance_access(request, x_role="admin", x_tenant_id=None)
    assert caught.value.status_code == 403
