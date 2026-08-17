"""Integrity and non-effect tests for credential authorization v1."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from veritas_os.policy.live_adapter_dry_run_credential_authorization import (
    CHECK_NAMES,
    EFFECT_FIELDS,
    FUTURE_REQUIREMENT_NAMES,
    SCOPE_LIMITATIONS,
    LiveAdapterDryRunCredentialAuthorizationError,
    _packet_hash,
    _policy_snapshot_hash,
    build_live_adapter_dry_run_credential_authorization_evaluation_packet,
    verify_live_adapter_dry_run_credential_authorization_evaluation_packet,
)
from veritas_os.policy.live_adapter_dry_run_endpoint_allowlist import (
    _snapshot_hash as endpoint_snapshot_hash,
    build_live_adapter_dry_run_endpoint_allowlist_evaluation_packet,
)
from veritas_os.policy.live_adapter_dry_run_dispatch_readiness import (
    build_live_adapter_dry_run_dispatch_readiness_packet,
)
from veritas_os.tests.test_live_adapter_dry_run_request import (
    REQUESTED_AT,
    _packet as request_packet,
)

EVALUATED_AT = REQUESTED_AT + timedelta(seconds=3)
MODULE = Path(
    "veritas_os/policy/live_adapter_dry_run_credential_authorization.py"
)
SCHEMA = Path(
    "schemas/live-adapter-dry-run-credential-authorization-v1.schema.json"
)


def _source(*, semantic_match: bool = False):
    readiness = build_live_adapter_dry_run_dispatch_readiness_packet(
        request_packet(semantic_match=semantic_match),
        REQUESTED_AT + timedelta(seconds=1),
    )
    candidate = {
        "endpoint_candidate_id": "endpoint:billing:v1",
        "endpoint_kind": "HTTPS_API", "endpoint_scheme": "https",
        "endpoint_host": "api.example.invalid", "endpoint_port": 443,
        "endpoint_path_prefix": "/v1/billing",
        "endpoint_environment": "staging", "endpoint_purpose": "dry-run",
        "adapter_contract_id": readiness.adapter_contract_id,
        "target_system": "billing",
        "target_resource_scope": "invoices:read",
        "declared_by": "operator:local",
        "declared_at": (REQUESTED_AT + timedelta(seconds=2)).isoformat(),
    }
    snapshot = {
        "allowlist_snapshot_id": "allowlist:local:v1",
        "allowlist_snapshot_hash": "0" * 64, "allowlist_version": "1",
        "allowlist_source": "local-reviewed-fixture",
        "allowlist_generated_at": (
            REQUESTED_AT + timedelta(seconds=2)
        ).isoformat(),
        "allowlist_entries": [{
            "entry_id": "allow:billing:v1", "endpoint_kind": "HTTPS_API",
            "endpoint_scheme": "https", "endpoint_host": "api.example.invalid",
            "endpoint_port": 443, "endpoint_path_prefix": "/v1/billing",
            "endpoint_environment": "staging",
            "allowed_adapter_contract_ids": [readiness.adapter_contract_id],
            "allowed_target_systems": ["billing"],
            "allowed_target_resource_scopes": ["invoices:read"],
            "allowed_purposes": ["dry-run"], "entry_status": "ACTIVE",
        }],
        "allowlist_scope_limitations": ["LOCAL_DECLARATIONS_ONLY"],
    }
    snapshot["allowlist_snapshot_hash"] = endpoint_snapshot_hash(snapshot)
    return build_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(
        readiness, candidate, snapshot, REQUESTED_AT + timedelta(seconds=2)
    )


def _reference(source=None, **changes):
    source = source or _source()
    value = {
        "credential_reference_id": "credential-ref:billing:v1",
        "credential_kind": "API_CREDENTIAL",
        "credential_provider_type": "LOCAL_REFERENCE",
        "credential_scope": "billing:invoices:read",
        "credential_environment": "staging",
        "credential_purpose": "dry-run",
        "adapter_contract_id": source.adapter_contract_id,
        "endpoint_candidate_id": source.endpoint_candidate.endpoint_candidate_id,
        "target_system": "billing",
        "target_resource_scope": "invoices:read",
        "declared_by": "operator:local", "declared_at": EVALUATED_AT.isoformat(),
    }
    value.update(changes)
    return value


def _snapshot(reference=None, *, active=True, entries=True):
    reference = reference or _reference()
    entry = {
        "entry_id": "credential-policy:billing:v1",
        "credential_kind": reference["credential_kind"],
        "credential_provider_type": reference["credential_provider_type"],
        "credential_scope": reference["credential_scope"],
        "credential_environment": reference["credential_environment"],
        "allowed_adapter_contract_ids": [reference["adapter_contract_id"]],
        "allowed_endpoint_candidate_ids": [reference["endpoint_candidate_id"]],
        "allowed_target_systems": [reference["target_system"]],
        "allowed_target_resource_scopes": [reference["target_resource_scope"]],
        "allowed_purposes": [reference["credential_purpose"]],
        "requires_operator_review": True,
        "requires_bind_pre_dispatch_review": True,
        "entry_status": "ACTIVE" if active else "INACTIVE",
    }
    value = {
        "credential_policy_snapshot_id": "credential-policy:local:v1",
        "credential_policy_snapshot_hash": "0" * 64,
        "credential_policy_version": "1",
        "credential_policy_source": "local-reviewed-fixture",
        "credential_policy_generated_at": EVALUATED_AT.isoformat(),
        "credential_policy_entries": [entry] if entries else [],
        "credential_policy_scope_limitations": ["LOCAL_METADATA_ONLY"],
    }
    value["credential_policy_snapshot_hash"] = _policy_snapshot_hash(value)
    return value


def _packet(reference=None, snapshot=None, *, semantic_match=False):
    source = _source(semantic_match=semantic_match)
    reference = reference or _reference(source)
    return build_live_adapter_dry_run_credential_authorization_evaluation_packet(
        source, reference, snapshot or _snapshot(reference), EVALUATED_AT
    )


def _rehash(raw):
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_credential_authorization_evaluation_hash"] = digest
    raw["live_adapter_dry_run_credential_authorization_evaluation_id"] = (
        f"ladrcr:v1:sha256:{digest}"
    )


def test_builder_verifier_exact_match_and_source_reverification(monkeypatch) -> None:
    import veritas_os.policy.live_adapter_dry_run_credential_authorization as module

    actual = module.verify_live_adapter_dry_run_endpoint_allowlist_evaluation_packet
    calls = []

    def recording(value):
        calls.append(value)
        return actual(value)

    monkeypatch.setattr(
        module, "verify_live_adapter_dry_run_endpoint_allowlist_evaluation_packet",
        recording,
    )
    source = _source()
    reference = _reference(source)
    packet = module.build_live_adapter_dry_run_credential_authorization_evaluation_packet(
        source, reference, _snapshot(reference), EVALUATED_AT
    )
    assert len(calls) == 2
    assert module.verify_live_adapter_dry_run_credential_authorization_evaluation_packet(
        packet
    ) == packet
    assert len(calls) == 3
    assert packet.credential_authorization_result.authorized
    assert not packet.fail_closed


@pytest.mark.parametrize(
    ("reference_field", "entry_field", "value"),
    [
        ("credential_kind", "credential_kind", "api_credential"),
        ("credential_provider_type", "credential_provider_type", "local_reference"),
        ("credential_scope", "credential_scope", "billing:invoices"),
        ("credential_environment", "credential_environment", "STAGING"),
        ("adapter_contract_id", "allowed_adapter_contract_ids", "other"),
        ("endpoint_candidate_id", "allowed_endpoint_candidate_ids", "other"),
        ("target_system", "allowed_target_systems", "other"),
        ("target_resource_scope", "allowed_target_resource_scopes", "other"),
        ("credential_purpose", "allowed_purposes", "other"),
    ],
)
def test_every_policy_comparison_is_exact_and_fail_closed(
    reference_field, entry_field, value,
) -> None:
    reference = _reference()
    snapshot = _snapshot(reference)
    snapshot["credential_policy_entries"][0][entry_field] = (
        [value] if entry_field.startswith("allowed_") else value
    )
    snapshot["credential_policy_snapshot_hash"] = _policy_snapshot_hash(snapshot)
    packet = _packet(reference, snapshot)
    assert not packet.credential_authorization_result.authorized
    assert packet.credential_authorization_result.semantic_match_used is False
    assert packet.fail_closed


@pytest.mark.parametrize("active,entries", [(False, True), (True, False)])
def test_inactive_or_missing_policy_entry_fails_closed(active, entries) -> None:
    packet = _packet(snapshot=_snapshot(active=active, entries=entries))
    assert packet.fail_closed
    assert not packet.credential_authorization_result.authorized


@pytest.mark.parametrize(
    "key",
    ["authorization_header", "token", "secret", "cookie", "password",
     "private_key", "credential_material", "api_key", "request_body"],
)
def test_sensitive_reference_fields_are_rejected(key) -> None:
    reference = _reference()
    reference[key] = "forbidden"
    with pytest.raises(LiveAdapterDryRunCredentialAuthorizationError):
        _packet(reference, _snapshot())


def test_closed_inputs_and_policy_hash_are_enforced() -> None:
    bad_reference = _reference(unexpected=True)
    bad_snapshot = _snapshot()
    bad_snapshot["unexpected"] = True
    for reference, snapshot in (
        (bad_reference, _snapshot()), (_reference(), bad_snapshot)
    ):
        with pytest.raises(LiveAdapterDryRunCredentialAuthorizationError):
            _packet(reference, snapshot)
    bad_hash = _snapshot()
    bad_hash["credential_policy_snapshot_hash"] = "0" * 64
    with pytest.raises(LiveAdapterDryRunCredentialAuthorizationError):
        _packet(snapshot=bad_hash)


def test_source_fields_lineage_endpoint_and_identity_are_preserved() -> None:
    source = _source()
    reference = _reference(source)
    packet = build_live_adapter_dry_run_credential_authorization_evaluation_packet(
        source, reference, _snapshot(reference), EVALUATED_AT
    )
    for field in (
        "request_descriptor", "execution_intent", "execution_intent_id",
        "execution_intent_hash", "adapter_contract_descriptor",
        "adapter_contract_id", "adapter_contract_hash", "adapter_contract_version",
        "endpoint_candidate", "endpoint_candidate_digest",
        "endpoint_identity_binding", "endpoint_identity_binding_digest",
        "source_to_execution_intent_mapping", "field_mapping_proof",
        "required_field_presence", "source_decision_identity", "candidate_identity",
        "evidence_lineage", "replay_summary",
    ):
        actual = getattr(packet, field)
        expected = getattr(source, field)
        assert actual == (expected.model_dump(mode="json")
                          if hasattr(expected, "model_dump") else expected)
    assert packet.source_dispatch_readiness_hash == source.source_dispatch_readiness_hash
    assert packet.source_live_adapter_dry_run_request_hash == (
        source.source_live_adapter_dry_run_request_hash
    )


def test_checks_requirements_scope_and_effects_are_exact() -> None:
    packet = _packet()
    assert [item.name for item in packet.credential_authorization_checks] == list(
        CHECK_NAMES
    )
    assert [item.ordinal for item in packet.credential_authorization_checks] == list(
        range(1, 39)
    )
    assert all(
        getattr(item, field) is False
        for item in packet.credential_authorization_checks for field in EFFECT_FIELDS
    )
    assert [item.name for item in packet.future_dispatch_review_requirements] == list(
        FUTURE_REQUIREMENT_NAMES
    )
    assert all(
        not item.satisfied_by_this_packet
        for item in packet.future_dispatch_review_requirements
    )
    assert packet.scope_limitations == SCOPE_LIMITATIONS


@pytest.mark.parametrize("semantic_match", [True, False])
def test_semantic_match_is_preserved_but_never_promoted(semantic_match) -> None:
    packet = _packet(semantic_match=semantic_match)
    assert packet.replay_summary["semantic_match"] is semantic_match
    assert packet.credential_authorization_result.semantic_match_used is False
    encoded = json.dumps(packet.model_dump(mode="json"))
    assert "Authority Evidence" not in encoded
    assert "Human Approval" not in encoded


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("live_adapter_dry_run_credential_authorization_evaluation_hash", "0" * 64),
        ("live_adapter_dry_run_credential_authorization_evaluation_id",
         "ladrcr:v1:sha256:" + "0" * 64),
        ("fail_closed", True), ("scope_limitations", ["NOT_DISPATCHED"]),
        ("request_descriptor", {}), ("execution_intent", {}),
        ("source_endpoint_allowlist_evaluation_hash", "0" * 64),
    ],
)
def test_top_level_tampering_is_rejected(field, value) -> None:
    raw = _packet().model_dump(mode="json")
    raw[field] = value
    if "hash" not in field and "id" not in field:
        _rehash(raw)
    with pytest.raises(LiveAdapterDryRunCredentialAuthorizationError):
        verify_live_adapter_dry_run_credential_authorization_evaluation_packet(raw)


@pytest.mark.parametrize(
    "target",
    ["credential_reference", "credential_policy_snapshot",
     "credential_authorization_result", "credential_authorization_checks",
     "future_dispatch_review_requirements", "credential_scope_binding"],
)
def test_nested_mutation_and_related_digest_changes_are_rejected(target) -> None:
    raw = _packet().model_dump(mode="json")
    if target == "credential_reference":
        raw[target]["declared_by"] = "forged"
    elif target == "credential_policy_snapshot":
        raw[target]["credential_policy_version"] = "forged"
    elif target == "credential_authorization_result":
        raw[target]["matched_policy_entry_id"] = "forged"
    elif target == "credential_scope_binding":
        raw[target]["credential_scope"] = "forged"
    else:
        raw[target].reverse()
    _rehash(raw)
    with pytest.raises(LiveAdapterDryRunCredentialAuthorizationError):
        verify_live_adapter_dry_run_credential_authorization_evaluation_packet(raw)


def test_source_packet_is_reverified_and_unmatched_source_is_rejected() -> None:
    raw = _packet().model_dump(mode="json")
    raw["source_endpoint_allowlist_evaluation_packet"][
        "live_adapter_dry_run_endpoint_allowlist_evaluation_hash"
    ] = "0" * 64
    _rehash(raw)
    with pytest.raises(LiveAdapterDryRunCredentialAuthorizationError):
        verify_live_adapter_dry_run_credential_authorization_evaluation_packet(raw)


def test_security_import_and_call_surface_is_absent() -> None:
    tree = ast.parse(MODULE.read_text())
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree) if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        (node.module or "").split(".")[0]
        for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    )
    assert imported.isdisjoint(
        {"requests", "httpx", "urllib", "socket", "dns", "subprocess", "os",
         "pathlib"}
    )
    source = MODULE.read_text()
    for forbidden in (
        "WebhookBindAdapter", "BindReceipt", "TrustLog", "credential_store",
        "verify_postconditions", "os.environ", ".read_text(", ".write_text(",
    ):
        assert forbidden not in source


def test_schema_accepts_packet_and_rejects_mutation() -> None:
    schema = json.loads(SCHEMA.read_text())
    raw = _packet().model_dump(mode="json")
    Draft202012Validator(schema).validate(raw)
    raw["unexpected"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(raw)
