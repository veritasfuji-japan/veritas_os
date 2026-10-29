"""Drift prevention tests for bind target catalog, coverage, and route markers."""

from __future__ import annotations

from collections import Counter
from copy import copy, deepcopy
from dataclasses import replace
import importlib
import json
from unittest.mock import Mock

import pytest
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient

from veritas_os.api import auth, governance, routes_governance, routes_system, server
from veritas_os.api.bind_target_catalog import CATALOG
from veritas_os.api.server import app
from veritas_os.core.eu_ai_act_oversight import SystemHaltController
from veritas_os.logging import trust_log
from veritas_os.policy import bind_boundary_adapters as adapters
from veritas_os.policy.bind_artifacts import BindReceipt, ExecutionIntent, find_bind_receipts
from veritas_os.policy import compliance_config_update, governance_policy_update
from veritas_os.policy import policy_bundle_promotion, system_halt_update
from veritas_os.policy.bind_coverage import (
    BindCoverageClass,
    classify_bind_coverage,
    get_bind_coverage_registry,
)
from veritas_os.policy.bind_route_markers import get_bind_boundary_metadata
from veritas_os.policy.bind_core import core as bind_core
from veritas_os.policy.compiler import compile_policy_to_bundle


# Deliberately independent of catalog discovery: losing all rows must not pass.
# Values: target type, path type, route module, helper, adapter, intent action.
MANAGEMENT = {
    ("PUT", "/v1/governance/policy"): (
        "governance_policy", "governance_policy_update", routes_governance,
        governance_policy_update.update_governance_policy_with_bind_boundary,
        adapters.GovernancePolicyUpdateAdapter, "update_governance_policy",
    ),
    ("POST", "/v1/governance/policy-bundles/promote"): (
        "policy_bundle", "policy_bundle_promotion", routes_governance,
        policy_bundle_promotion.promote_policy_bundle_with_bind_boundary,
        adapters.PolicyBundlePromotionAdapter, "promote_policy_bundle",
    ),
    ("PUT", "/v1/compliance/config"): (
        "compliance_config", "compliance_config_update", routes_system,
        compliance_config_update.update_compliance_config_with_bind_boundary,
        adapters.ComplianceConfigUpdateAdapter, "update_compliance_config",
    ),
    ("POST", "/v1/system/halt"): (
        "system_halt", "system_halt", routes_system,
        system_halt_update.halt_system_with_bind_boundary,
        adapters.SystemHaltAdapter, "halt_system",
    ),
    ("POST", "/v1/system/resume"): (
        "system_resume", "system_resume", routes_system,
        system_halt_update.resume_system_with_bind_boundary,
        adapters.SystemResumeAdapter, "resume_system",
    ),
}


def _mounted_routes():
    return [
        (context.path, context.route)
        for context in iter_route_contexts(app.routes)
        if isinstance(context.route, APIRoute)
    ]


def _assert_management_alignment(catalog, registry, routes) -> None:
    """Check exact membership/multiplicity, not only intersections of paths."""
    assert Counter(e.target_path for e in catalog) == Counter(p for _, p in MANAGEMENT)
    assert Counter(
        (e.method, e.path) for e in registry
        if e.coverage_class == BindCoverageClass.BIND_GOVERNED
    ) == Counter(MANAGEMENT.keys())
    mounted = []
    for path, route in routes:
        metadata = get_bind_boundary_metadata(route.endpoint)
        for method in route.methods - {"HEAD", "OPTIONS"}:
            key = (method, path)
            if metadata is None and key not in MANAGEMENT:
                continue
            assert key in MANAGEMENT, f"unexpected marked operation: {key}"
            mounted.append(key)
            expected_type, expected_path_type, *_ = MANAGEMENT[key]
            assert metadata is not None, f"missing marker: {key}"
            assert (metadata.target_path, metadata.target_type, metadata.target_path_type) == (
                path, expected_type, expected_path_type,
            )
            entry = next(e for e in catalog if e.target_path == path)
            assert (entry.target_type, entry.target_path_type) == (expected_type, expected_path_type)
    assert Counter(mounted) == Counter(MANAGEMENT.keys())


def test_management_catalog_registry_and_mounted_routes_match_exactly() -> None:
    _assert_management_alignment(CATALOG, get_bind_coverage_registry(), _mounted_routes())


@pytest.mark.parametrize("current, metadata, expected", [
    ("other", {"target_path_type": "compliance_config_update"}, "compliance_config_update"),
    ("", {"target_path_type": "compliance_config_update"}, "compliance_config_update"),
    ("explicit_type", {"target_path_type": "compliance_config_update"}, "explicit_type"),
    ("other", {}, "other"),
])
def test_receipt_backfill_preserves_concrete_metadata(current, metadata, expected) -> None:
    receipt = BindReceipt(target_path="/explicit", target_path_type=current)
    result = bind_core._apply_bind_target_metadata_from_lineage(
        receipt,
        execution_intent=ExecutionIntent(policy_lineage={"bind_target_metadata": {
            "target_path": "/different", **metadata,
        }}),
    )
    assert result.target_path_type == expected
    assert result.target_path == "/explicit"
    assert receipt.target_path_type == current


@pytest.mark.parametrize("fault", [
    "catalog_missing", "catalog_extra", "catalog_duplicate", "catalog_type",
    "registry_missing", "registry_extra", "registry_method", "registry_duplicate",
    "route_missing", "route_duplicate", "marker_missing", "marker_type",
])
def test_management_alignment_detects_inventory_and_marker_drift(fault) -> None:
    """Corrupt copies only; every detector must reject a concrete drift."""
    catalog, registry, routes = list(CATALOG), list(get_bind_coverage_registry()), _mounted_routes()
    key = next(iter(MANAGEMENT))
    row = next(e for e in registry if (e.method, e.path) == key)
    route_row = next(row for row in routes if row[0] == key[1] and key[0] in row[1].methods)
    route = route_row[1]
    if fault.startswith("catalog_"):
        if fault == "catalog_missing":
            catalog.remove(catalog[0])
        else:
            changed = replace(catalog[0], **(
                {"target_path": "/v1/unexpected"} if fault == "catalog_extra" else
                {"target_type": "wrong"} if fault == "catalog_type" else {}
            ))
            if fault == "catalog_type":
                catalog[0] = changed
            else:
                catalog.append(changed)
    elif fault.startswith("registry_"):
        if fault == "registry_missing":
            registry.remove(row)
        elif fault == "registry_method":
            registry[registry.index(row)] = replace(row, method="DELETE")
        else:
            registry.append(replace(row, path="/v1/unexpected") if fault == "registry_extra" else row)
    elif fault == "route_missing":
        routes.remove(route_row)
    elif fault == "route_duplicate":
        routes.append(route_row)
    else:
        changed = copy(route)
        def endpoint():
            pass
        if fault == "marker_type":
            endpoint._bind_boundary_metadata = replace(get_bind_boundary_metadata(route.endpoint), target_type="wrong")
        changed.endpoint = endpoint
        routes[routes.index(route_row)] = (route_row[0], changed)
    with pytest.raises(AssertionError):
        _assert_management_alignment(catalog, registry, routes)


@pytest.mark.parametrize("key", MANAGEMENT)
@pytest.mark.parametrize("mode", ["commit", "block", "escalate", "no_key", "auditor"])
def test_management_http_reaches_expected_bind_and_preserves_state_on_refusal(
    monkeypatch, tmp_path, key, mode,
) -> None:
    """Real mounted HTTP routes/helpers/core/adapters; local effects only."""
    method, path = key
    target_type, path_type, _, helper, adapter_type, action = MANAGEMENT[key]
    api_key = f"management-bind-{tmp_path.name}"
    monkeypatch.setenv("VERITAS_API_KEY", api_key)
    monkeypatch.setenv("VERITAS_API_KEYS", json.dumps([
        {"key": api_key, "role": "admin"}, {"key": api_key + "-read", "role": "auditor"},
    ]))
    monkeypatch.setenv("VERITAS_GOVERNANCE_ALLOWED_ROLES", "admin")
    policy_path = tmp_path / "governance.json"
    policy = governance.GovernancePolicy().model_dump()
    if mode in {"block", "escalate"}:
        policy["bind_adjudication"].update(ttl_required=True, missing_signal_default=mode)
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    monkeypatch.setattr(governance, "_DEFAULT_POLICY_PATH", policy_path)
    monkeypatch.setattr(server, "SystemHaltController", SystemHaltController)
    for name, value in {
        "_halted": path.endswith("/resume"), "_halted_by": None,
        "_halted_at": None, "_halt_reason": None, "_history": [],
    }.items():
        monkeypatch.setattr(SystemHaltController, name, value)
    config = {"eu_ai_act_mode": False, "safety_threshold": 0.8}
    def update_config(**patch):
        config.update(patch)
        return dict(config)
    monkeypatch.setattr(routes_system, "get_runtime_config", lambda: dict(config))
    monkeypatch.setattr(routes_system, "update_runtime_config", update_config)
    pointer = tmp_path / "active.json"
    pointer.write_text('{"active_bundle_dir":"previous"}', encoding="utf-8")
    monkeypatch.setenv("VERITAS_POLICY_ACTIVE_POINTER_PATH", str(pointer))
    bundles = tmp_path / "bundles"
    monkeypatch.setenv("VERITAS_POLICY_BUNDLES_ROOT", str(bundles))
    if target_type == "policy_bundle":
        compiled = compile_policy_to_bundle(
            "policies/examples/low_risk_route_allow.yaml", tmp_path / "compiled",
        )
        # Use the real compiler output under the same configured allowed root.
        bundles.mkdir()
        compiled.bundle_dir.rename(bundles / "fixture-bundle")
    body = {
        "governance_policy": {"risk_thresholds": {"allow_upper": 0.45}, "approvals": [
            {"reviewer": "alice", "signature": "sig-alice"},
            {"reviewer": "bob", "signature": "sig-bob"},
        ]},
        "policy_bundle": {"bundle_id": "fixture-bundle", "decision_id": "bind-matrix",
                          "request_id": "bind-matrix", "policy_snapshot_id": "fixture",
                          "decision_hash": "a" * 64},
        "compliance_config": {"eu_ai_act_mode": True, "safety_threshold": 0.77},
        "system_halt": {"reason": "test-only halt", "operator": "untrusted-label"},
        "system_resume": {"comment": "test-only resume", "operator": "untrusted-label"},
    }[target_type]
    # Suppress publication/alerts, retaining real core and state mutations.
    monkeypatch.setattr(server, "_publish_event", lambda *a, **k: None)
    monkeypatch.setattr(routes_governance, "_emit_governance_change_alert", lambda **k: None)
    for name, value in {
        "LOG_DIR": tmp_path, "LOG_JSON": tmp_path / "trust_log.json",
        "LOG_JSONL": tmp_path / "trust_log.jsonl",
        "_append_stats": {"success": 0, "failure": 0},
    }.items():
        monkeypatch.setattr(trust_log, name, value)
    monkeypatch.setattr(trust_log, "open_trust_log_for_append", lambda: open(
        trust_log.LOG_JSONL, "a", encoding="utf-8",
    ))
    intents, receipts, applies = [], [], []
    real_append_intent = bind_core.append_execution_intent_trustlog
    real_append_receipt = bind_core.append_bind_receipt_trustlog
    def append_intent(intent):
        intents.append(intent)
        return real_append_intent(intent)
    def append_receipt(receipt):
        persisted = real_append_receipt(receipt)
        receipts.append(persisted)
        return persisted
    monkeypatch.setattr(bind_core, "append_execution_intent_trustlog", append_intent)
    monkeypatch.setattr(bind_core, "append_bind_receipt_trustlog", append_receipt)
    helpers = {}
    for route_key, (_, _, route_module, real_helper, _, _) in MANAGEMENT.items():
        helpers[route_key] = Mock(wraps=real_helper)
        monkeypatch.setattr(route_module, real_helper.__name__, helpers[route_key])
    core_spy = Mock(wraps=bind_core.execute_bind_adjudication)
    monkeypatch.setattr(importlib.import_module(helper.__module__), "execute_bind_adjudication", core_spy)
    real_apply = adapter_type.apply
    def apply(self, intent, snapshot):
        applies.append(intent.execution_intent_id)
        return real_apply(self, intent, snapshot)
    monkeypatch.setattr(adapter_type, "apply", apply)
    def state():
        return (policy_path.read_bytes(), pointer.read_bytes(), dict(config),
                deepcopy(SystemHaltController.status()), deepcopy(SystemHaltController._history))
    before = state()
    headers = {} if mode == "no_key" else {
        "X-API-Key": api_key + ("-read" if mode == "auditor" else ""), "X-Role": "admin",
    }
    client = TestClient(app)
    try:
        response = client.request(method, path, headers=headers, json=body)
    finally:
        client.close()
    for route_key, spy in helpers.items():
        assert spy.call_count == int(route_key == key and mode not in {"no_key", "auditor"}), (response.status_code, response.json())
    if mode in {"no_key", "auditor"}:
        assert response.status_code == (401 if mode == "no_key" else 403)
        core_spy.assert_not_called()
        assert intents == receipts == applies == []
        assert state() == before
        return
    core_spy.assert_called_once()
    intent = core_spy.call_args.kwargs["execution_intent"]
    assert type(core_spy.call_args.kwargs["adapter"]) is adapter_type
    assert intent.intended_action == action
    assert intent.actor_identity == auth._derive_api_user_id(api_key)
    assert len(intents) == len(receipts) == 1
    assert intents[0] is intent
    payload = response.json()
    expected = {"commit": "COMMITTED", "block": "BLOCKED", "escalate": "ESCALATED"}[mode]
    # Promotion retains its existing HTTP 200 + explicit non-commit outcome.
    assert response.status_code == (200 if mode == "commit" or target_type == "policy_bundle" else 403)
    assert payload["bind_outcome"] == expected == receipts[0].final_outcome.value
    assert payload["execution_intent_id"] == intent.execution_intent_id
    assert payload["bind_receipt_id"] == receipts[0].bind_receipt_id
    if mode != "commit":
        assert applies == []
        assert state() == before
    else:
        assert applies == [intent.execution_intent_id]
        if target_type == "governance_policy":
            assert json.loads(policy_path.read_text())["risk_thresholds"]["allow_upper"] == 0.45
        elif target_type == "policy_bundle":
            assert json.loads(pointer.read_text())["active_bundle_dir"] == str((bundles / "fixture-bundle").resolve())
        elif target_type == "compliance_config":
            assert config == body
        else:
            assert SystemHaltController.is_halted() is (target_type == "system_halt")
            assert len(SystemHaltController._history) == 1
    assert payload["bind_receipt"]["target_path"] == path
    assert payload["target_metadata"]["target_type"] == target_type
    assert payload["target_metadata"]["target_path_type"] == path_type
    assert (receipts[0].target_path, receipts[0].target_type, receipts[0].target_path_type) == (
        path, target_type, path_type,
    )
    reloaded = find_bind_receipts(bind_receipt_id=receipts[0].bind_receipt_id)
    assert len(reloaded) == 1
    assert (reloaded[0].target_path, reloaded[0].target_type, reloaded[0].target_path_type) == (
        path, target_type, path_type,
    )
    assert reloaded[0].final_outcome.value == expected


def test_bind_governed_registry_paths_match_catalog_paths() -> None:
    """bind_governed coverage entries must match canonical catalog targets."""
    governed_paths = {
        entry.path
        for entry in get_bind_coverage_registry()
        if entry.coverage_class == BindCoverageClass.BIND_GOVERNED
    }
    catalog_paths = {entry.target_path for entry in CATALOG}
    assert governed_paths == catalog_paths


def test_bind_governed_routes_declare_marker_metadata() -> None:
    """bind_governed runtime routes should declare bind marker metadata."""
    for path, route in _mounted_routes():
        for method in route.methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            coverage = classify_bind_coverage(path, method)
            if coverage is None or coverage.coverage_class != BindCoverageClass.BIND_GOVERNED:
                continue
            metadata = get_bind_boundary_metadata(route.endpoint)
            assert metadata is not None, f"missing marker for {method} {path}"
            assert metadata.target_path == path


def test_bind_route_markers_align_with_catalog_metadata() -> None:
    """Route marker metadata should align with catalog definitions."""
    catalog_by_path = {entry.target_path: entry for entry in CATALOG}

    for _, route in _mounted_routes():
        metadata = get_bind_boundary_metadata(route.endpoint)
        if metadata is None:
            continue
        catalog_entry = catalog_by_path.get(metadata.target_path)
        assert catalog_entry is not None
        assert catalog_entry.target_type == metadata.target_type
        assert catalog_entry.target_path_type == metadata.target_path_type
