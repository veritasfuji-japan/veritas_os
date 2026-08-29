"""Fail-closed tests for promotion-native credential authorization evidence."""

from __future__ import annotations

import ast
from datetime import timedelta
from pathlib import Path

import pytest

from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_credential_authorization import (
    EFFECT_FIELDS,
    CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError,
    _packet_hash,
    _policy_snapshot_hash,
    build_canonical_promotion_live_adapter_dry_run_credential_authorization_evaluation_packet,
    verify_canonical_promotion_live_adapter_dry_run_credential_authorization_evaluation_packet,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_endpoint_allowlist import (
    EVALUATED_AT as ENDPOINT_AT,
    _candidate as endpoint_candidate,
    _packet as endpoint_packet,
    _snapshot as endpoint_snapshot,
)

EVALUATED_AT = ENDPOINT_AT + timedelta(seconds=1)
MODULE = Path(
    "veritas_os/policy/"
    "canonical_promotion_live_adapter_dry_run_credential_authorization.py"
)


def _reference(**changes: object) -> dict:
    source = endpoint_packet()
    value = {
        "credential_reference_id": "credential-ref:promotion:billing:v1",
        "credential_kind": "API_TOKEN_REFERENCE",
        "credential_provider_type": "LOCAL_SECRET_STORE_REFERENCE",
        "credential_scope": "invoice:write",
        "credential_environment": "staging",
        "credential_purpose": "promotion-dry-run",
        "adapter_contract_id": source.adapter_contract_id,
        "endpoint_candidate_id": source.endpoint_candidate.endpoint_candidate_id,
        "target_system": source.execution_intent["target_system"],
        "target_resource_scope": source.execution_intent["target_resource"],
        "declared_by": "operator:local",
        "declared_at": EVALUATED_AT.isoformat(),
    }
    value.update(changes)
    return value


def _snapshot(reference: dict | None = None, *, active: bool = True) -> dict:
    reference = reference or _reference()
    entry = {
        "entry_id": "credential-policy:promotion:billing:v1",
        **{field: reference[field] for field in (
            "credential_kind",
            "credential_provider_type",
            "credential_scope",
            "credential_environment",
        )},
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
        "credential_policy_source": "local-reviewed-snapshot",
        "credential_policy_generated_at": EVALUATED_AT.isoformat(),
        "credential_policy_entries": [entry],
        "credential_policy_scope_limitations": ["EXACT_LOCAL_METADATA_ONLY"],
    }
    value["credential_policy_snapshot_hash"] = _policy_snapshot_hash(value)
    return value


def _packet(reference: dict | None = None, snapshot: dict | None = None):
    reference = reference or _reference()
    return build_canonical_promotion_live_adapter_dry_run_credential_authorization_evaluation_packet(
        endpoint_packet(), reference, snapshot or _snapshot(reference), EVALUATED_AT
    )


def _rehash(raw: dict) -> None:
    digest = _packet_hash(raw)
    raw[
        "promotion_live_adapter_dry_run_credential_authorization_evaluation_hash"
    ] = digest
    raw[
        "promotion_live_adapter_dry_run_credential_authorization_evaluation_id"
    ] = f"pladrca:v1:sha256:{digest}"


def _set(raw: dict, path: str, value: object) -> None:
    target = raw
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    if isinstance(target, list):
        target[int(parts[-1])] = value
    else:
        target[parts[-1]] = value


def test_full_chain_authorized_preserves_exact_identity_and_lineage() -> None:
    source = endpoint_packet()
    packet = verify_canonical_promotion_live_adapter_dry_run_credential_authorization_evaluation_packet(
        _packet()
    )
    intent = ExecutionIntent(**packet.execution_intent)
    assert packet.execution_intent == source.execution_intent == intent.to_dict()
    assert packet.execution_intent_id == source.execution_intent_id
    assert packet.execution_intent_hash == hash_execution_intent(intent)
    assert packet.adapter_contract_id == source.adapter_contract_id
    assert packet.adapter_contract_hash == source.adapter_contract_hash
    assert packet.endpoint_candidate_digest == source.endpoint_candidate_digest
    assert (
        packet.endpoint_identity_binding_digest
        == source.endpoint_identity_binding_digest
    )
    assert packet.credential_authorization_result.authorized is True
    assert packet.fail_closed is False
    assert packet.ready_for_promotion_native_operator_dispatch_review is True
    assert packet.approval_context == source.approval_context
    assert packet.policy_lineage == source.policy_lineage
    assert packet.human_approval_proven is False
    assert packet.authority_evidence_proven is False
    assert packet.execution_authorized is False
    assert all(not getattr(packet, field) for field in EFFECT_FIELDS)


def test_policy_refusal_is_independently_verifiable_evidence() -> None:
    snapshot = _snapshot()
    snapshot["credential_policy_entries"][0]["credential_scope"] = "other"
    snapshot["credential_policy_snapshot_hash"] = _policy_snapshot_hash(snapshot)
    packet = _packet(snapshot=snapshot)
    assert packet.credential_authorization_result.authorized is False
    assert packet.credential_authorization_result.rejection_reasons == (
        "credential_scope_mismatch",
    )
    assert packet.fail_closed is True
    assert packet.ready_for_promotion_native_operator_dispatch_review is False
    assert verify_canonical_promotion_live_adapter_dry_run_credential_authorization_evaluation_packet(
        packet
    ) == packet


def test_endpoint_refusal_cannot_enter_credential_stage() -> None:
    refused_candidate = endpoint_candidate(endpoint_host="refused.invalid")
    refused = endpoint_packet(refused_candidate, endpoint_snapshot(endpoint_candidate()))
    assert refused.allowlist_evaluation_result.matched is False
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError
    ):
        build_canonical_promotion_live_adapter_dry_run_credential_authorization_evaluation_packet(
            refused, _reference(), _snapshot(), EVALUATED_AT
        )


@pytest.mark.parametrize(
    "field",
    [
        "secret",
        "secret_value",
        "api_key",
        "bearer_token",
        "token",
        "authorization",
        "authorization_header",
        "cookie",
        "password",
        "private_key",
        "credential",
        "credentials",
        "credential_payload",
        "credential_material",
        "resolved_credential_material",
        "request_body",
        "body",
        "verified",
    ],
)
def test_sensitive_and_unknown_reference_fields_rejected(field: str) -> None:
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError
    ):
        _packet(_reference(**{field: "must-not-enter"}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("adapter_contract_id", "other-adapter"),
        ("endpoint_candidate_id", "other-endpoint"),
        ("target_system", "other-system"),
        ("target_resource_scope", "other-resource"),
    ],
)
def test_reference_must_bind_authoritative_source(field: str, value: str) -> None:
    reference = _reference(**{field: value})
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError
    ):
        _packet(reference, _snapshot(reference))


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("execution_intent_id", "ei:v1:sha256:" + "0" * 64),
        ("execution_intent_hash", "0" * 64),
        ("adapter_contract_hash", "0" * 64),
        ("endpoint_candidate.endpoint_host", "tampered.invalid"),
        ("endpoint_candidate_digest", "0" * 64),
        ("endpoint_identity_binding_digest", "0" * 64),
        ("allowlist_snapshot_hash", "0" * 64),
        ("allowlist_evaluation_result.matched", False),
        ("credential_reference.credential_scope", "other"),
        ("credential_reference_digest", "0" * 64),
        ("credential_policy_snapshot_hash", "0" * 64),
        ("credential_policy_snapshot.credential_policy_entries.0.entry_status", "INACTIVE"),
        ("credential_authorization_result.authorized", False),
        ("credential_authorization_result.matched_policy_entry_id", "other"),
        ("credential_authorization_result_digest", "0" * 64),
        ("credential_scope_binding.credential_scope", "other"),
        ("credential_scope_binding_digest", "0" * 64),
        ("source_promotion_hash", "0" * 64),
        ("approval_context.required_human_approval", False),
        ("policy_lineage", {}),
        ("credential_authorization_checks.0.ordinal", 2),
        ("credential_authorization_checks.0.network_used", True),
        ("credential_authorization_check_digest", "0" * 64),
        ("future_requirements.0.satisfied_by_this_packet", True),
        ("future_requirement_digest", "0" * 64),
        ("fail_closed", True),
        ("ready_for_promotion_native_operator_dispatch_review", False),
        ("credential_resolved", True),
        ("credential_material_accessed", True),
        ("credential_store_accessed", True),
        ("authorization_header_constructed", True),
        ("network_used", True),
        ("request_dispatched", True),
        ("bind_invoked", True),
        ("human_approval_proven", True),
        ("authority_evidence_proven", True),
        ("execution_authorized", True),
    ],
)
def test_packet_tampering_fails_closed(path: str, value: object) -> None:
    raw = _packet().model_dump(mode="json")
    _set(raw, path, value)
    _rehash(raw)
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError
    ):
        verify_canonical_promotion_live_adapter_dry_run_credential_authorization_evaluation_packet(
            raw
        )


def test_policy_timestamp_packet_and_shortcut_tampering() -> None:
    snapshot = _snapshot()
    snapshot["credential_policy_entries"][0]["credential_kind"] = "mutated"
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError
    ):
        _packet(snapshot=snapshot)
    future_reference = _reference(
        declared_at=(EVALUATED_AT + timedelta(seconds=1)).isoformat()
    )
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError
    ):
        _packet(future_reference, _snapshot(future_reference))
    future_snapshot = _snapshot()
    future_snapshot["credential_policy_generated_at"] = (
        EVALUATED_AT + timedelta(seconds=1)
    ).isoformat()
    future_snapshot["credential_policy_snapshot_hash"] = _policy_snapshot_hash(
        future_snapshot
    )
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError
    ):
        _packet(snapshot=future_snapshot)
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError
    ):
        build_canonical_promotion_live_adapter_dry_run_credential_authorization_evaluation_packet(
            endpoint_packet(), _reference(), _snapshot(), ENDPOINT_AT - timedelta(seconds=1)
        )
    for field in ("verified", "safe", "authorized"):
        raw = _packet().model_dump(mode="json")
        raw[field] = True
        with pytest.raises(
            CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError
        ):
            verify_canonical_promotion_live_adapter_dry_run_credential_authorization_evaluation_packet(
                raw
            )
    malformed = _packet().model_dump(mode="json")
    malformed["source_endpoint_allowlist_evaluation_packet"] = {}
    _rehash(malformed)
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError
    ):
        verify_canonical_promotion_live_adapter_dry_run_credential_authorization_evaluation_packet(
            malformed
        )


def test_production_has_no_capabilities_test_imports_or_legacy_dependency() -> None:
    tree = ast.parse(MODULE.read_text())
    imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert all("tests" not in ast.unparse(node) for node in imports)
    imported_modules = {
        node.module
        for node in imports
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert (
        "veritas_os.policy.live_adapter_dry_run_credential_authorization"
        not in imported_modules
    )
    forbidden_modules = {"requests", "httpx", "socket", "subprocess"}
    assert all(
        not (
            isinstance(node, ast.Import)
            and any(alias.name.split(".")[0] in forbidden_modules for alias in node.names)
        )
        and not (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.split(".")[0] in forbidden_modules
        )
        for node in imports
    )
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert all(
        not (isinstance(node.func, ast.Name) and node.func.id == "open")
        and not (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
            and node.func.attr == "run"
        )
        for node in calls
    )
