"""Fail-closed tests for promotion-native endpoint allowlist evidence."""
from __future__ import annotations

import ast
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest

from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_endpoint_allowlist import (
    EFFECT_FIELDS,
    CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError,
    _packet_hash,
    _snapshot_hash,
    build_canonical_promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_packet,
    verify_canonical_promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_packet,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_dispatch_readiness import (
    EVALUATED_AT as DISPATCH_AT,
    _packet as dispatch_packet,
)

EVALUATED_AT = DISPATCH_AT + timedelta(seconds=1)
MODULE = Path("veritas_os/policy/canonical_promotion_live_adapter_dry_run_endpoint_allowlist.py")


def _candidate(**changes: object) -> dict:
    source = dispatch_packet()
    value = {
        "endpoint_candidate_id": "endpoint:promotion:billing:v1",
        "endpoint_kind": "HTTPS_API",
        "endpoint_scheme": "https",
        "endpoint_host": "api.example.invalid",
        "endpoint_port": 443,
        "endpoint_path_prefix": "/v1/invoices",
        "endpoint_environment": "staging",
        "endpoint_purpose": "promotion-dry-run",
        "adapter_contract_id": source.adapter_contract_id,
        "target_system": source.execution_intent["target_system"],
        "target_resource_scope": source.execution_intent["target_resource"],
        "declared_by": "operator:local",
        "declared_at": EVALUATED_AT.isoformat(),
    }
    value.update(changes)
    return value


def _snapshot(candidate: dict | None = None, *, active: bool = True) -> dict:
    candidate = candidate or _candidate()
    entry = {
        "entry_id": "allow:promotion:billing:v1",
        "endpoint_kind": candidate["endpoint_kind"],
        "endpoint_scheme": candidate["endpoint_scheme"],
        "endpoint_host": candidate["endpoint_host"],
        "endpoint_port": candidate["endpoint_port"],
        "endpoint_path_prefix": candidate["endpoint_path_prefix"],
        "endpoint_environment": candidate["endpoint_environment"],
        "allowed_adapter_contract_ids": [candidate["adapter_contract_id"]],
        "allowed_target_systems": [candidate["target_system"]],
        "allowed_target_resource_scopes": [candidate["target_resource_scope"]],
        "allowed_purposes": [candidate["endpoint_purpose"]],
        "entry_status": "ACTIVE" if active else "INACTIVE",
    }
    value = {
        "allowlist_snapshot_id": "allowlist:promotion:local:v1",
        "allowlist_snapshot_hash": "0" * 64,
        "allowlist_version": "1",
        "allowlist_source": "local-reviewed-snapshot",
        "allowlist_generated_at": EVALUATED_AT.isoformat(),
        "allowlist_entries": [entry],
        "allowlist_scope_limitations": ["LOCAL_DECLARATIONS_ONLY"],
    }
    value["allowlist_snapshot_hash"] = _snapshot_hash(value)
    return value


def _packet(candidate: dict | None = None, snapshot: dict | None = None):
    candidate = candidate or _candidate()
    return build_canonical_promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(
        dispatch_packet(), candidate, snapshot or _snapshot(candidate), EVALUATED_AT
    )


def _rehash(raw: dict) -> None:
    digest = _packet_hash(raw)
    raw["promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_hash"] = digest
    raw["promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_id"] = (
        f"pladrea:v1:sha256:{digest}"
    )


def _set(raw: dict, path: str, value: object) -> None:
    target = raw
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    if isinstance(target, list):
        target[int(parts[-1])] = value
    else:
        target[parts[-1]] = value


def test_full_chain_exact_match_identity_lineage_and_no_effects() -> None:
    source = dispatch_packet()
    packet = verify_canonical_promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(
        _packet()
    )
    intent = ExecutionIntent(**packet.execution_intent)
    assert packet.execution_intent == source.execution_intent == intent.to_dict()
    assert packet.execution_intent_id == source.execution_intent_id == intent.execution_intent_id
    assert packet.execution_intent_hash == source.execution_intent_hash == hash_execution_intent(intent)
    assert packet.adapter_contract_id == source.adapter_contract_id
    assert packet.adapter_contract_hash == source.adapter_contract_hash
    assert packet.adapter_contract_descriptor == source.adapter_contract_descriptor
    assert packet.endpoint_candidate.adapter_contract_id == source.adapter_contract_id
    assert packet.endpoint_candidate.target_system == intent.target_system
    assert packet.endpoint_candidate.target_resource_scope == intent.target_resource
    assert packet.allowlist_evaluation_result.matched is True
    assert packet.fail_closed is False
    assert packet.ready_for_promotion_native_credential_authorization_evaluation is True
    assert packet.approval_context == source.approval_context
    assert packet.approval_context["required_human_approval"] is True
    assert packet.human_approval_proven is False
    assert packet.authority_evidence_proven is False
    assert packet.policy_lineage == source.policy_lineage
    assert all(not getattr(packet, field) for field in EFFECT_FIELDS)
    assert packet.endpoint_identity_binding["endpoint_candidate_digest"] == packet.endpoint_candidate_digest
    assert packet.endpoint_identity_binding["allowlist_evaluation_digest"] == packet.allowlist_evaluation_digest


def test_unmatched_packet_is_verifiable_refusal() -> None:
    candidate = _candidate(endpoint_host="refused.example.invalid")
    packet = _packet(candidate, _snapshot(_candidate()))
    assert packet.allowlist_evaluation_result.matched is False
    assert packet.allowlist_evaluation_result.mismatch_reasons == ("endpoint_host_mismatch",)
    assert packet.fail_closed is True
    assert packet.ready_for_promotion_native_credential_authorization_evaluation is False
    assert verify_canonical_promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(packet) == packet


@pytest.mark.parametrize("field", [
    "authorization", "authorization_header", "token", "secret", "cookie",
    "credential", "credentials", "request_body", "body", "verified",
])
def test_sensitive_and_unknown_candidate_fields_rejected(field: str) -> None:
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError):
        _packet(_candidate(**{field: "do-not-accept"}))


@pytest.mark.parametrize(("field", "value"), [
    ("adapter_contract_id", "other-adapter"),
    ("target_system", "other-system"),
    ("target_resource_scope", "other-resource"),
])
def test_candidate_must_bind_authoritative_request(field: str, value: str) -> None:
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError):
        _packet(_candidate(**{field: value}))


@pytest.mark.parametrize(("path", "value"), [
    ("execution_intent_id", "ei:v1:sha256:" + "0" * 64),
    ("execution_intent_hash", "0" * 64),
    ("adapter_contract_id", "adapter-contract:v1:sha256:" + "0" * 64),
    ("adapter_contract_hash", "0" * 64),
    ("endpoint_candidate.endpoint_host", "tampered.invalid"),
    ("endpoint_candidate_digest", "0" * 64),
    ("allowlist_snapshot_hash", "0" * 64),
    ("allowlist_snapshot.allowlist_entries.0.entry_status", "INACTIVE"),
    ("allowlist_evaluation_result.matched", False),
    ("allowlist_evaluation_result.matched_entry_id", "other"),
    ("allowlist_evaluation_digest", "0" * 64),
    ("endpoint_identity_binding.endpoint_candidate_id", "other"),
    ("endpoint_identity_binding_digest", "0" * 64),
    ("source_promotion_hash", "0" * 64),
    ("approval_context.required_human_approval", False),
    ("policy_lineage", {}),
    ("endpoint_allowlist_checks.0.ordinal", 2),
    ("endpoint_allowlist_checks.0.network_used", True),
    ("endpoint_allowlist_check_digest", "0" * 64),
    ("future_requirements.0.satisfied_by_this_packet", True),
    ("future_requirement_digest", "0" * 64),
    ("fail_closed", True),
    ("ready_for_promotion_native_credential_authorization_evaluation", False),
    ("endpoint_resolved", True), ("dns_used", True), ("network_used", True),
    ("credential_accessed", True), ("request_dispatched", True),
    ("bind_invoked", True), ("human_approval_proven", True),
    ("authority_evidence_proven", True),
])
def test_tampering_fails_closed(path: str, value: object) -> None:
    raw = _packet().model_dump(mode="json")
    _set(raw, path, value)
    _rehash(raw)
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError):
        verify_canonical_promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(raw)


def test_snapshot_source_time_packet_and_shortcut_tampering() -> None:
    snapshot = _snapshot()
    snapshot["allowlist_entries"][0]["endpoint_host"] = "mutated.invalid"
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError):
        _packet(snapshot=snapshot)
    for timestamp in ("declared_at",):
        with pytest.raises(CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError):
            _packet(_candidate(**{timestamp: (EVALUATED_AT + timedelta(seconds=1)).isoformat()}))
    future_snapshot = _snapshot()
    future_snapshot["allowlist_generated_at"] = (EVALUATED_AT + timedelta(seconds=1)).isoformat()
    future_snapshot["allowlist_snapshot_hash"] = _snapshot_hash(future_snapshot)
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError):
        _packet(snapshot=future_snapshot)
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError):
        build_canonical_promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(
            dispatch_packet(), _candidate(), _snapshot(), DISPATCH_AT - timedelta(seconds=1)
        )
    for field, value in (("verified", True), ("authorized", True)):
        raw = _packet().model_dump(mode="json")
        raw[field] = value
        with pytest.raises(CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError):
            verify_canonical_promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(raw)
    raw = _packet().model_dump(mode="json")
    raw["source_dispatch_readiness_packet"] = {}
    _rehash(raw)
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError):
        verify_canonical_promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(raw)


def test_production_has_no_effect_or_test_imports() -> None:
    tree = ast.parse(MODULE.read_text())
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    text = MODULE.read_text()
    assert all("tests" not in ast.unparse(node) for node in imports)
    assert all(term not in text for term in ("requests", "httpx", "socket", "subprocess.run"))
    legacy = __import__(
        "veritas_os.policy.live_adapter_dry_run_endpoint_allowlist", fromlist=["FORMAT_VERSION"]
    )
    assert legacy.FORMAT_VERSION == "canonical-live-adapter-dry-run-endpoint-allowlist-evaluation/v1"
