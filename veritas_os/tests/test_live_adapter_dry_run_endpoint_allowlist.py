"""Integrity and non-effect tests for endpoint allowlist evaluation v1."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from veritas_os.policy.live_adapter_dry_run_endpoint_allowlist import (
    CHECK_NAMES,
    EFFECT_FIELDS,
    FUTURE_REQUIREMENT_NAMES,
    SCOPE_LIMITATIONS,
    LiveAdapterDryRunEndpointAllowlistError,
    _packet_hash,
    _snapshot_hash,
    build_live_adapter_dry_run_endpoint_allowlist_evaluation_packet,
    verify_live_adapter_dry_run_endpoint_allowlist_evaluation_packet,
)
from veritas_os.policy.live_adapter_dry_run_dispatch_readiness import (
    build_live_adapter_dry_run_dispatch_readiness_packet,
)
from veritas_os.tests.test_live_adapter_dry_run_request import (
    REQUESTED_AT,
    _packet as request_packet,
)

EVALUATED_AT = REQUESTED_AT + timedelta(seconds=2)
MODULE = Path("veritas_os/policy/live_adapter_dry_run_endpoint_allowlist.py")
SCHEMA = Path("schemas/live-adapter-dry-run-endpoint-allowlist-v1.schema.json")


def _source(*, semantic_match: bool = False):
    return build_live_adapter_dry_run_dispatch_readiness_packet(
        request_packet(semantic_match=semantic_match), REQUESTED_AT + timedelta(seconds=1)
    )


def _candidate(**changes):
    value = {
        "endpoint_candidate_id": "endpoint:billing:v1", "endpoint_kind": "HTTPS_API",
        "endpoint_scheme": "https", "endpoint_host": "api.example.invalid",
        "endpoint_port": 443, "endpoint_path_prefix": "/v1/billing",
        "endpoint_environment": "staging", "endpoint_purpose": "dry-run",
        "adapter_contract_id": _source().adapter_contract_id,
        "target_system": "billing", "target_resource_scope": "invoices:read",
        "declared_by": "operator:local", "declared_at": EVALUATED_AT.isoformat(),
    }
    value.update(changes)
    return value


def _snapshot(candidate=None, *, active=True, entries=True):
    candidate = candidate or _candidate()
    entry = {
        "entry_id": "allow:billing:v1", "endpoint_kind": candidate["endpoint_kind"],
        "endpoint_scheme": candidate["endpoint_scheme"],
        "endpoint_host": candidate["endpoint_host"], "endpoint_port": candidate["endpoint_port"],
        "endpoint_path_prefix": candidate["endpoint_path_prefix"],
        "endpoint_environment": candidate["endpoint_environment"],
        "allowed_adapter_contract_ids": [candidate["adapter_contract_id"]],
        "allowed_target_systems": [candidate["target_system"]],
        "allowed_target_resource_scopes": [candidate["target_resource_scope"]],
        "allowed_purposes": [candidate["endpoint_purpose"]],
        "entry_status": "ACTIVE" if active else "INACTIVE",
    }
    value = {
        "allowlist_snapshot_id": "allowlist:local:v1", "allowlist_snapshot_hash": "0" * 64,
        "allowlist_version": "1", "allowlist_source": "local-reviewed-fixture",
        "allowlist_generated_at": EVALUATED_AT.isoformat(),
        "allowlist_entries": [entry] if entries else [],
        "allowlist_scope_limitations": ["LOCAL_DECLARATIONS_ONLY"],
    }
    value["allowlist_snapshot_hash"] = _snapshot_hash(value)
    return value


def _packet(candidate=None, snapshot=None, *, semantic_match=False):
    candidate = candidate or _candidate()
    return build_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(
        _source(semantic_match=semantic_match), candidate,
        snapshot or _snapshot(candidate), EVALUATED_AT,
    )


def _rehash(raw):
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_endpoint_allowlist_evaluation_hash"] = digest
    raw["live_adapter_dry_run_endpoint_allowlist_evaluation_id"] = f"ladrea:v1:sha256:{digest}"


def test_builder_verifier_exact_match_and_preservation(monkeypatch) -> None:
    import veritas_os.policy.live_adapter_dry_run_endpoint_allowlist as module

    actual = module.verify_live_adapter_dry_run_dispatch_readiness_packet
    calls = []

    def recording(value):
        calls.append(value)
        return actual(value)

    monkeypatch.setattr(module, "verify_live_adapter_dry_run_dispatch_readiness_packet", recording)
    source = _source()
    candidate = _candidate()
    packet = module.build_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(
        source, candidate, _snapshot(candidate), EVALUATED_AT)
    assert len(calls) == 2
    assert module.verify_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(packet) == packet
    assert len(calls) == 3
    assert packet.allowlist_evaluation_result.matched
    assert not packet.fail_closed
    for field in ("request_descriptor", "execution_intent", "execution_intent_id",
                  "execution_intent_hash", "adapter_contract_descriptor",
                  "adapter_contract_id", "adapter_contract_hash", "adapter_contract_version",
                  "source_to_execution_intent_mapping", "field_mapping_proof",
                  "required_field_presence", "source_decision_identity", "candidate_identity",
                  "evidence_lineage", "replay_summary"):
        assert getattr(packet, field) == getattr(source, field)


@pytest.mark.parametrize(
    ("candidate_field", "entry_field", "value"),
    [("endpoint_host", "endpoint_host", "API.example.invalid"),
     ("endpoint_scheme", "endpoint_scheme", "HTTPS"),
     ("endpoint_port", "endpoint_port", 8443),
     ("endpoint_path_prefix", "endpoint_path_prefix", "/v1/billing/"),
     ("endpoint_environment", "endpoint_environment", "production"),
     ("adapter_contract_id", "allowed_adapter_contract_ids", "other"),
     ("target_system", "allowed_target_systems", "other"),
     ("target_resource_scope", "allowed_target_resource_scopes", "other"),
     ("endpoint_purpose", "allowed_purposes", "other")],
)
def test_every_comparison_is_exact_and_fail_closed(candidate_field, entry_field, value) -> None:
    candidate = _candidate()
    snapshot = _snapshot(candidate)
    snapshot["allowlist_entries"][0][entry_field] = [value] if entry_field.startswith("allowed_") else value
    snapshot["allowlist_snapshot_hash"] = _snapshot_hash(snapshot)
    packet = _packet(candidate, snapshot)
    assert not packet.allowlist_evaluation_result.matched
    assert packet.allowlist_evaluation_result.semantic_match_used is False
    assert packet.fail_closed


@pytest.mark.parametrize("active,entries", [(False, True), (True, False)])
def test_inactive_or_missing_entry_fails_closed(active, entries) -> None:
    packet = _packet(snapshot=_snapshot(active=active, entries=entries))
    assert packet.fail_closed and not packet.allowlist_evaluation_result.matched


@pytest.mark.parametrize("key", ["authorization_header", "token", "secret", "cookie", "credential"])
def test_sensitive_candidate_fields_are_rejected(key) -> None:
    candidate = _candidate()
    candidate[key] = "forbidden"
    with pytest.raises(LiveAdapterDryRunEndpointAllowlistError):
        _packet(candidate, _snapshot())


def test_closed_inputs_and_snapshot_hash_are_enforced() -> None:
    candidate = _candidate(unexpected=True)
    snapshot = _snapshot()
    snapshot["unexpected"] = True
    for bad_candidate, bad_snapshot in ((candidate, _snapshot()), (_candidate(), snapshot)):
        with pytest.raises(LiveAdapterDryRunEndpointAllowlistError):
            _packet(bad_candidate, bad_snapshot)
    bad_hash = _snapshot()
    bad_hash["allowlist_snapshot_hash"] = "0" * 64
    with pytest.raises(LiveAdapterDryRunEndpointAllowlistError):
        _packet(snapshot=bad_hash)


def test_checks_requirements_scope_and_effects_are_exact() -> None:
    packet = _packet()
    assert [item.name for item in packet.endpoint_allowlist_checks] == list(CHECK_NAMES)
    assert [item.ordinal for item in packet.endpoint_allowlist_checks] == list(range(1, 31))
    assert all(getattr(item, field) is False for item in packet.endpoint_allowlist_checks
               for field in EFFECT_FIELDS)
    assert [item.name for item in packet.future_credential_requirements] == list(FUTURE_REQUIREMENT_NAMES)
    assert all(not item.satisfied_by_this_packet for item in packet.future_credential_requirements)
    assert packet.scope_limitations == SCOPE_LIMITATIONS


@pytest.mark.parametrize("semantic_match", [True, False])
def test_semantic_match_is_preserved_but_never_used_as_authority(semantic_match) -> None:
    packet = _packet(semantic_match=semantic_match)
    assert packet.replay_summary["semantic_match"] is semantic_match
    assert packet.allowlist_evaluation_result.semantic_match_used is False
    assert "Authority Evidence" not in json.dumps(packet.model_dump(mode="json"))


@pytest.mark.parametrize(
    ("field", "value"),
    [("live_adapter_dry_run_endpoint_allowlist_evaluation_hash", "0" * 64),
     ("live_adapter_dry_run_endpoint_allowlist_evaluation_id", "ladrea:v1:sha256:" + "0" * 64),
     ("fail_closed", True), ("scope_limitations", ["NOT_DISPATCHED"]),
     ("request_descriptor", {}), ("execution_intent", {}),
     ("source_dispatch_readiness_hash", "0" * 64)],
)
def test_top_level_tampering_is_rejected(field, value) -> None:
    raw = _packet().model_dump(mode="json")
    raw[field] = value
    if "hash" not in field and "id" not in field:
        _rehash(raw)
    with pytest.raises(LiveAdapterDryRunEndpointAllowlistError):
        verify_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(raw)


@pytest.mark.parametrize("target", ["allowlist_evaluation_result", "endpoint_allowlist_checks", "future_credential_requirements"])
def test_nested_mutation_is_rejected(target) -> None:
    raw = _packet().model_dump(mode="json")
    if target == "allowlist_evaluation_result":
        raw[target]["matched_entry_id"] = "forged"
    else:
        raw[target].reverse()
    _rehash(raw)
    with pytest.raises(LiveAdapterDryRunEndpointAllowlistError):
        verify_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(raw)


def test_source_mutation_is_reverified() -> None:
    raw = _packet().model_dump(mode="json")
    raw["source_dispatch_readiness_packet"]["live_adapter_dry_run_dispatch_readiness_hash"] = "0" * 64
    _rehash(raw)
    with pytest.raises(LiveAdapterDryRunEndpointAllowlistError):
        verify_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(raw)


def test_schema_accepts_packet_and_rejects_mutation() -> None:
    schema = json.loads(SCHEMA.read_text())
    raw = _packet().model_dump(mode="json")
    Draft202012Validator(schema).validate(raw)
    raw["unexpected"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(raw)


def test_module_has_no_forbidden_imports_or_effect_calls() -> None:
    tree = ast.parse(MODULE.read_text())
    imports = {alias.name.split(".")[0] for node in ast.walk(tree)
               if isinstance(node, (ast.Import, ast.ImportFrom))
               for alias in node.names}
    assert imports.isdisjoint({"requests", "httpx", "urllib", "socket", "dns",
                               "subprocess", "os", "pathlib"})
    source = MODULE.read_text()
    for forbidden in ("WebhookBindAdapter", "BindReceipt", "TrustLog", "verify_postconditions",
                      "credential_store", "provider_client"):
        assert forbidden not in source
