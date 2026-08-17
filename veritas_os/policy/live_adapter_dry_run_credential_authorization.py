"""Evaluate credential-reference authorization without accessing credentials.

This module is deliberately limited to deterministic comparison of caller-
supplied metadata.  It has no credential resolution, I/O, adapter, Bind,
TrustLog, or dispatch capability.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.live_adapter_dry_run_endpoint_allowlist import (
    CanonicalLiveAdapterDryRunEndpointAllowlistEvaluationPacket,
    LiveAdapterDryRunEndpointAllowlistError,
    verify_live_adapter_dry_run_endpoint_allowlist_evaluation_packet,
)

FORMAT_VERSION = (
    "canonical-live-adapter-dry-run-credential-authorization-evaluation/v1"
)
EVALUATION_MECHANISM = (
    "evaluate_live_adapter_dry_run_credential_authorization_without_access/v1"
)
STATUS = "LIVE_ADAPTER_DRY_RUN_CREDENTIAL_AUTHORIZATION_EVALUATED_NOT_DISPATCHED"
CHECK_MODE = "deterministic_local_credential_authorization_evaluation_only"
REFERENCE_DOMAIN = (
    "veritas.live-adapter-dry-run-credential-authorization.reference/v1"
)
POLICY_SNAPSHOT_DOMAIN = (
    "veritas.live-adapter-dry-run-credential-authorization.policy-snapshot/v1"
)
RESULT_DOMAIN = "veritas.live-adapter-dry-run-credential-authorization.result/v1"
SCOPE_BINDING_DOMAIN = (
    "veritas.live-adapter-dry-run-credential-authorization.scope-binding/v1"
)
CHECKS_DOMAIN = "veritas.live-adapter-dry-run-credential-authorization.checks/v1"
FUTURE_REVIEW_DOMAIN = (
    "veritas.live-adapter-dry-run-credential-authorization."
    "future-dispatch-review-requirements/v1"
)
PACKET_DOMAIN = "veritas.live-adapter-dry-run-credential-authorization.packet/v1"

CHECK_NAMES = (
    "source_endpoint_allowlist_evaluation_verified",
    "source_request_not_dispatched",
    "source_endpoint_allowlist_matched",
    "credential_reference_closed_schema_valid",
    "credential_reference_contains_no_secret_value",
    "credential_reference_contains_no_api_key",
    "credential_reference_contains_no_bearer_token",
    "credential_reference_contains_no_authorization_header",
    "credential_reference_contains_no_cookie",
    "credential_reference_contains_no_password",
    "credential_reference_contains_no_private_key",
    "credential_policy_snapshot_closed_schema_valid",
    "credential_policy_snapshot_hash_verified",
    "credential_policy_entry_active_status_required",
    "credential_kind_exact_match",
    "credential_provider_type_exact_match",
    "credential_scope_exact_match",
    "credential_environment_exact_match",
    "adapter_contract_id_allowed",
    "endpoint_candidate_id_allowed",
    "target_system_allowed",
    "target_resource_scope_allowed",
    "credential_purpose_allowed",
    "credential_scope_binding_constructed",
    "credential_not_resolved",
    "credential_material_not_accessed",
    "authorization_header_not_constructed",
    "token_not_embedded",
    "secret_not_embedded",
    "network_not_used",
    "webhook_not_called",
    "live_adapter_not_instantiated",
    "bind_not_invoked",
    "bind_receipt_not_created",
    "trustlog_not_written",
    "future_operator_dispatch_review_required",
    "future_bind_pre_dispatch_review_required",
    "future_network_dispatch_boundary_required",
)
EFFECT_FIELDS = (
    "credential_resolved", "credential_material_accessed",
    "credential_material_embedded", "authorization_header_constructed",
    "token_embedded", "secret_embedded", "cookie_embedded",
    "password_embedded", "private_key_embedded", "credential_store_accessed",
    "endpoint_resolved", "dns_used", "network_used", "webhook_called",
    "live_adapter_instantiated", "live_adapter_method_called",
    "request_dispatched", "bind_invoked", "bind_receipt_created",
    "trustlog_written", "external_effect_used", "filesystem_used",
    "database_used", "provider_used", "subprocess_used", "operation_committed",
)
SCOPE_LIMITATIONS = (
    "NOT_DISPATCHED", "NOT_CREDENTIAL_RESOLUTION", "NOT_CREDENTIAL_ACCESS",
    "NOT_CREDENTIAL_STORE_ACCESS", "NOT_CREDENTIAL_EMBEDDING",
    "NOT_AUTHORIZATION_HEADER", "NOT_TOKEN", "NOT_SECRET", "NOT_COOKIE",
    "NOT_PASSWORD", "NOT_PRIVATE_KEY", "NOT_ENDPOINT_RESOLUTION",
    "NOT_DNS_RESOLUTION", "NOT_NETWORK_CALL", "NOT_WEBHOOK_CALL",
    "NOT_LIVE_ADAPTER_INSTANCE", "NOT_LIVE_ADAPTER_RESULT",
    "NOT_BIND_AUTHORIZATION", "NOT_BIND_RECEIPT", "NOT_TRUSTLOG_WRITE",
    "NOT_OPERATION_COMMIT", "NOT_PRODUCTION_CLAIM", "NOT_CUSTOMER_CLAIM",
    "NOT_REGULATORY_CERTIFICATION",
)
FUTURE_REQUIREMENT_NAMES = (
    "operator_human_dispatch_review", "bind_pre_dispatch_review",
    "endpoint_identity_recheck", "credential_material_resolution_boundary",
    "authorization_header_construction_boundary", "credential_redaction_boundary",
    "network_dispatch_boundary", "request_dispatch_receipt_boundary",
    "trustlog_write_boundary_after_proper_authorization",
    "bind_receipt_boundary_only_after_bind",
    "rollback_postcondition_requirements_for_later_apply_path",
)
EXACT_FIELDS = (
    "credential_kind", "credential_provider_type", "credential_scope",
    "credential_environment", "adapter_contract_id", "endpoint_candidate_id",
    "target_system", "target_resource_scope", "credential_purpose",
)
COPIED_FIELDS = (
    "request_descriptor", "execution_intent", "execution_intent_id",
    "execution_intent_hash", "adapter_contract_descriptor", "adapter_contract_id",
    "adapter_contract_hash", "adapter_contract_version", "endpoint_candidate",
    "endpoint_candidate_digest", "endpoint_identity_binding",
    "endpoint_identity_binding_digest", "source_to_execution_intent_mapping",
    "field_mapping_proof", "required_field_presence", "source_decision_identity",
    "candidate_identity", "evidence_lineage", "replay_summary",
)
PROHIBITED_KEYS = {
    "secret", "secret_value", "api_key", "bearer_token", "token",
    "authorization", "authorization_header", "cookie", "password",
    "private_key", "credential", "credentials", "credential_payload",
    "credential_material", "resolved_credential_material", "request_body", "body",
}


class LiveAdapterDryRunCredentialAuthorizationError(ValueError):
    """Stable fail-closed refusal for invalid credential evidence."""


class CredentialReference(BaseModel):
    """Closed metadata-only reference; never credential material."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    credential_reference_id: str = Field(min_length=1)
    credential_kind: str = Field(min_length=1)
    credential_provider_type: str = Field(min_length=1)
    credential_scope: str = Field(min_length=1)
    credential_environment: str = Field(min_length=1)
    credential_purpose: str = Field(min_length=1)
    adapter_contract_id: str = Field(min_length=1)
    endpoint_candidate_id: str = Field(min_length=1)
    target_system: str = Field(min_length=1)
    target_resource_scope: str = Field(min_length=1)
    declared_by: str = Field(min_length=1)
    declared_at: str


class CredentialPolicyEntry(BaseModel):
    """One exact local credential authorization rule."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    entry_id: str = Field(min_length=1)
    credential_kind: str
    credential_provider_type: str
    credential_scope: str
    credential_environment: str
    allowed_adapter_contract_ids: tuple[str, ...]
    allowed_endpoint_candidate_ids: tuple[str, ...]
    allowed_target_systems: tuple[str, ...]
    allowed_target_resource_scopes: tuple[str, ...]
    allowed_purposes: tuple[str, ...]
    requires_operator_review: bool
    requires_bind_pre_dispatch_review: bool
    entry_status: Literal["ACTIVE", "INACTIVE"]


class CredentialPolicySnapshot(BaseModel):
    """Closed deterministic policy snapshot supplied by the caller."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    credential_policy_snapshot_id: str = Field(min_length=1)
    credential_policy_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    credential_policy_version: str = Field(min_length=1)
    credential_policy_source: str = Field(min_length=1)
    credential_policy_generated_at: str
    credential_policy_entries: tuple[CredentialPolicyEntry, ...]
    credential_policy_scope_limitations: tuple[str, ...]


class CredentialAuthorizationResult(BaseModel):
    """Exact authorization outcome without semantic inference."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    authorized: bool
    matched_policy_entry_id: str | None
    authorization_reason: str
    rejection_reasons: tuple[str, ...]
    comparison_mode: Literal["exact_local_credential_policy_comparison_only"]
    exact_fields_compared: tuple[str, ...]
    semantic_match_used: Literal[False]
    credential_material_accessed: Literal[False]


class CredentialAuthorizationCheck(BaseModel):
    """One ordered deterministic check with explicit non-effect facts."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    check_id: str
    ordinal: int = Field(ge=1, le=38)
    name: Literal[*CHECK_NAMES]
    mode: Literal[CHECK_MODE]
    passed: bool
    evidence_ref: str
    credential_resolved: Literal[False]
    credential_material_accessed: Literal[False]
    credential_material_embedded: Literal[False]
    authorization_header_constructed: Literal[False]
    token_embedded: Literal[False]
    secret_embedded: Literal[False]
    cookie_embedded: Literal[False]
    password_embedded: Literal[False]
    private_key_embedded: Literal[False]
    credential_store_accessed: Literal[False]
    endpoint_resolved: Literal[False]
    dns_used: Literal[False]
    network_used: Literal[False]
    webhook_called: Literal[False]
    live_adapter_instantiated: Literal[False]
    live_adapter_method_called: Literal[False]
    request_dispatched: Literal[False]
    bind_invoked: Literal[False]
    bind_receipt_created: Literal[False]
    trustlog_written: Literal[False]
    external_effect_used: Literal[False]
    filesystem_used: Literal[False]
    database_used: Literal[False]
    provider_used: Literal[False]
    subprocess_used: Literal[False]
    operation_committed: Literal[False]


class FutureDispatchReviewRequirement(BaseModel):
    """A later dispatch boundary not satisfied by this packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1, le=11)
    name: Literal[*FUTURE_REQUIREMENT_NAMES]
    separate_future_artifact_required: Literal[True]
    satisfied_by_this_packet: Literal[False]


class CanonicalLiveAdapterDryRunCredentialAuthorizationEvaluationPacket(BaseModel):
    """Closed content-addressed credential authorization packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    live_adapter_dry_run_credential_authorization_evaluation_id: str
    live_adapter_dry_run_credential_authorization_evaluation_hash: str
    credential_authorization_evaluation_mechanism: Literal[EVALUATION_MECHANISM]
    credential_authorization_evaluated_at: str
    source_endpoint_allowlist_evaluation_id: str
    source_endpoint_allowlist_evaluation_hash: str
    source_endpoint_allowlist_evaluation_packet: dict[str, Any]
    source_dispatch_readiness_hash: str
    source_live_adapter_dry_run_request_hash: str
    request_descriptor: dict[str, Any]
    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str
    adapter_contract_descriptor: dict[str, Any]
    adapter_contract_id: str
    adapter_contract_hash: str
    adapter_contract_version: str
    endpoint_candidate: dict[str, Any]
    endpoint_candidate_digest: str
    endpoint_identity_binding: dict[str, Any]
    endpoint_identity_binding_digest: str
    credential_reference: CredentialReference
    credential_reference_digest: str
    credential_policy_snapshot: CredentialPolicySnapshot
    credential_policy_snapshot_hash: str
    credential_authorization_result: CredentialAuthorizationResult
    credential_authorization_result_digest: str
    credential_scope_binding: dict[str, Any]
    credential_scope_binding_digest: str
    credential_authorization_checks: tuple[CredentialAuthorizationCheck, ...]
    credential_authorization_check_digest: str
    future_dispatch_review_requirements: tuple[FutureDispatchReviewRequirement, ...]
    future_dispatch_review_requirement_digest: str
    source_to_execution_intent_mapping: dict[str, Any]
    field_mapping_proof: dict[str, Any]
    required_field_presence: dict[str, str]
    source_decision_identity: dict[str, Any]
    candidate_identity: dict[str, Any]
    evidence_lineage: dict[str, Any]
    replay_summary: dict[str, Any]
    credential_authorization_status: Literal[STATUS]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    credential_resolved: Literal[False]
    credential_material_accessed: Literal[False]
    credential_material_embedded: Literal[False]
    authorization_header_constructed: Literal[False]
    token_embedded: Literal[False]
    secret_embedded: Literal[False]
    endpoint_resolved: Literal[False]
    network_used: Literal[False]
    live_adapter_instantiated: Literal[False]
    webhook_called: Literal[False]
    bind_invoked: Literal[False]
    bind_receipt_created: Literal[False]
    trustlog_written: Literal[False]
    fail_closed: bool
    scope_limitations: tuple[Literal[*SCOPE_LIMITATIONS], ...]


def _normalized_timestamp(value: Any) -> str:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_TIMESTAMP_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_TIMESTAMP_INVALID"
        )
    return parsed.astimezone(timezone.utc).isoformat()


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise LiveAdapterDryRunCredentialAuthorizationError(
                "LADRCR_PACKET_INVALID"
            )
        return value
    if isinstance(value, datetime):
        return _normalized_timestamp(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise LiveAdapterDryRunCredentialAuthorizationError("LADRCR_PACKET_INVALID")


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json_value(value)},
        allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _policy_snapshot_hash(raw: dict[str, Any]) -> str:
    """Return the domain-separated hash excluding the self-hash field."""
    return _digest(POLICY_SNAPSHOT_DOMAIN, {
        key: value for key, value in raw.items()
        if key != "credential_policy_snapshot_hash"
    })


def _packet_hash(raw: dict[str, Any]) -> str:
    """Return the packet hash excluding its content-addressed hash and ID."""
    omitted = {
        "live_adapter_dry_run_credential_authorization_evaluation_id",
        "live_adapter_dry_run_credential_authorization_evaluation_hash",
    }
    return _digest(PACKET_DOMAIN, {
        key: value for key, value in raw.items() if key not in omitted
    })


def _reject_sensitive_keys(value: Any) -> None:
    if not isinstance(value, dict):
        return
    for key in value:
        normalized = key.lower().replace("-", "_")
        if normalized in PROHIBITED_KEYS:
            raise LiveAdapterDryRunCredentialAuthorizationError(
                "LADRCR_SENSITIVE_INPUT"
            )


def _evaluation(
    reference: CredentialReference, snapshot: CredentialPolicySnapshot,
) -> dict[str, Any]:
    failures: set[str] = set()
    active_seen = False
    for entry in snapshot.credential_policy_entries:
        if entry.entry_status != "ACTIVE":
            continue
        active_seen = True
        comparisons = {
            "credential_kind": reference.credential_kind == entry.credential_kind,
            "credential_provider_type": (
                reference.credential_provider_type == entry.credential_provider_type
            ),
            "credential_scope": reference.credential_scope == entry.credential_scope,
            "credential_environment": (
                reference.credential_environment == entry.credential_environment
            ),
            "adapter_contract_id": (
                reference.adapter_contract_id in entry.allowed_adapter_contract_ids
            ),
            "endpoint_candidate_id": (
                reference.endpoint_candidate_id in entry.allowed_endpoint_candidate_ids
            ),
            "target_system": reference.target_system in entry.allowed_target_systems,
            "target_resource_scope": (
                reference.target_resource_scope
                in entry.allowed_target_resource_scopes
            ),
            "credential_purpose": reference.credential_purpose in entry.allowed_purposes,
        }
        if all(comparisons.values()):
            return {
                "authorized": True, "matched_policy_entry_id": entry.entry_id,
                "authorization_reason": "active_entry_exact_match",
                "rejection_reasons": [],
                "comparison_mode": "exact_local_credential_policy_comparison_only",
                "exact_fields_compared": list(EXACT_FIELDS),
                "semantic_match_used": False, "credential_material_accessed": False,
            }
        failures.update(name for name, passed in comparisons.items() if not passed)
    reasons = (["no_active_credential_policy_entry"] if not active_seen else [
        f"{name}_mismatch" for name in EXACT_FIELDS if name in failures
    ])
    return {
        "authorized": False, "matched_policy_entry_id": None,
        "authorization_reason": "no_active_exact_match",
        "rejection_reasons": reasons,
        "comparison_mode": "exact_local_credential_policy_comparison_only",
        "exact_fields_compared": list(EXACT_FIELDS),
        "semantic_match_used": False, "credential_material_accessed": False,
    }


def _scope_binding(
    source: CanonicalLiveAdapterDryRunEndpointAllowlistEvaluationPacket,
    reference: CredentialReference,
) -> dict[str, Any]:
    return {
        "credential_reference_id": reference.credential_reference_id,
        "adapter_contract_id": source.adapter_contract_id,
        "endpoint_candidate_id": source.endpoint_candidate.endpoint_candidate_id,
        "target_system": reference.target_system,
        "target_resource_scope": reference.target_resource_scope,
        "credential_scope": reference.credential_scope,
        "credential_purpose": reference.credential_purpose,
    }


def _requirements() -> list[dict[str, Any]]:
    return [{
        "ordinal": ordinal, "name": name,
        "separate_future_artifact_required": True,
        "satisfied_by_this_packet": False,
    } for ordinal, name in enumerate(FUTURE_REQUIREMENT_NAMES, 1)]


def _checks(source_hash: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    comparison_checks = set(CHECK_NAMES[13:23])
    return [{
        "check_id": f"ladrcr-check:v1:{ordinal}:{name.replace('_', '-')}",
        "ordinal": ordinal, "name": name, "mode": CHECK_MODE,
        "passed": result["authorized"] if name in comparison_checks else True,
        "evidence_ref": f"source_endpoint_allowlist_hash:{source_hash}:{name}",
        **{field: False for field in EFFECT_FIELDS},
    } for ordinal, name in enumerate(CHECK_NAMES, 1)]


def _source(
    value: Any,
) -> CanonicalLiveAdapterDryRunEndpointAllowlistEvaluationPacket:
    try:
        return verify_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(value)
    except (LiveAdapterDryRunEndpointAllowlistError, TypeError, ValueError) as exc:
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_SOURCE_INVALID"
        ) from exc


def _validate_source(
    source: CanonicalLiveAdapterDryRunEndpointAllowlistEvaluationPacket,
) -> None:
    if source.request_dispatch_state != "NOT_DISPATCHED":
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_SOURCE_DISPATCHED"
        )
    if source.endpoint_allowlist_status != (
        "LIVE_ADAPTER_DRY_RUN_ENDPOINT_ALLOWLIST_EVALUATED_NOT_DISPATCHED"
    ):
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_SOURCE_STATUS_INVALID"
        )
    if not source.allowlist_evaluation_result.matched:
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_SOURCE_ENDPOINT_NOT_ALLOWED"
        )


def build_live_adapter_dry_run_credential_authorization_evaluation_packet(
    source_endpoint_allowlist_evaluation_packet: Any,
    credential_reference: Any,
    credential_policy_snapshot: Any,
    credential_authorization_evaluated_at: datetime,
) -> CanonicalLiveAdapterDryRunCredentialAuthorizationEvaluationPacket:
    """Build and self-verify a local credential authorization evaluation."""
    evaluated_at = _normalized_timestamp(credential_authorization_evaluated_at)
    source = _source(_json_value(source_endpoint_allowlist_evaluation_packet))
    _validate_source(source)
    reference_input = _json_value(credential_reference)
    _reject_sensitive_keys(reference_input)
    try:
        reference = CredentialReference.model_validate(reference_input)
        snapshot = CredentialPolicySnapshot.model_validate(
            _json_value(credential_policy_snapshot)
        )
    except ValidationError as exc:
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_INPUT_INVALID"
        ) from exc
    reference_raw = reference.model_dump(mode="json")
    snapshot_raw = snapshot.model_dump(mode="json")
    _normalized_timestamp(reference.declared_at)
    _normalized_timestamp(snapshot.credential_policy_generated_at)
    if snapshot.credential_policy_snapshot_hash != _policy_snapshot_hash(snapshot_raw):
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_POLICY_HASH_INVALID"
        )
    if (
        reference.adapter_contract_id != source.adapter_contract_id
        or reference.endpoint_candidate_id
        != source.endpoint_candidate.endpoint_candidate_id
    ):
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_SOURCE_REFERENCE_MISMATCH"
        )
    if datetime.fromisoformat(evaluated_at) < datetime.fromisoformat(
        _normalized_timestamp(source.endpoint_allowlist_evaluated_at)
    ):
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_EVALUATED_TOO_EARLY"
        )
    result = _evaluation(reference, snapshot)
    binding = _scope_binding(source, reference)
    checks = _checks(source.live_adapter_dry_run_endpoint_allowlist_evaluation_hash,
                     result)
    requirements = _requirements()
    source_raw = source.model_dump(mode="json")
    raw = {
        "format_version": FORMAT_VERSION,
        "credential_authorization_evaluation_mechanism": EVALUATION_MECHANISM,
        "credential_authorization_evaluated_at": evaluated_at,
        "source_endpoint_allowlist_evaluation_id": (
            source.live_adapter_dry_run_endpoint_allowlist_evaluation_id
        ),
        "source_endpoint_allowlist_evaluation_hash": (
            source.live_adapter_dry_run_endpoint_allowlist_evaluation_hash
        ),
        "source_endpoint_allowlist_evaluation_packet": source_raw,
        "source_dispatch_readiness_hash": source.source_dispatch_readiness_hash,
        "source_live_adapter_dry_run_request_hash": (
            source.source_live_adapter_dry_run_request_hash
        ),
        **{field: source_raw[field] for field in COPIED_FIELDS},
        "credential_reference": reference_raw,
        "credential_reference_digest": _digest(REFERENCE_DOMAIN, reference_raw),
        "credential_policy_snapshot": snapshot_raw,
        "credential_policy_snapshot_hash": snapshot.credential_policy_snapshot_hash,
        "credential_authorization_result": result,
        "credential_authorization_result_digest": _digest(RESULT_DOMAIN, result),
        "credential_scope_binding": binding,
        "credential_scope_binding_digest": _digest(SCOPE_BINDING_DOMAIN, binding),
        "credential_authorization_checks": checks,
        "credential_authorization_check_digest": _digest(CHECKS_DOMAIN, checks),
        "future_dispatch_review_requirements": requirements,
        "future_dispatch_review_requirement_digest": _digest(
            FUTURE_REVIEW_DOMAIN, requirements
        ),
        "credential_authorization_status": STATUS,
        "request_dispatch_state": "NOT_DISPATCHED",
        **{field: False for field in (
            "credential_resolved", "credential_material_accessed",
            "credential_material_embedded", "authorization_header_constructed",
            "token_embedded", "secret_embedded", "endpoint_resolved",
            "network_used", "live_adapter_instantiated", "webhook_called",
            "bind_invoked", "bind_receipt_created", "trustlog_written",
        )},
        "fail_closed": not result["authorized"],
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_credential_authorization_evaluation_hash"] = digest
    raw["live_adapter_dry_run_credential_authorization_evaluation_id"] = (
        f"ladrcr:v1:sha256:{digest}"
    )
    return verify_live_adapter_dry_run_credential_authorization_evaluation_packet(raw)


def verify_live_adapter_dry_run_credential_authorization_evaluation_packet(
    raw: Any,
) -> CanonicalLiveAdapterDryRunCredentialAuthorizationEvaluationPacket:
    """Recompute every source binding, result, check, digest, hash, and ID."""
    try:
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw
        packet = (
            CanonicalLiveAdapterDryRunCredentialAuthorizationEvaluationPacket
            .model_validate(_json_value(value))
        )
    except (ValidationError, TypeError,
            LiveAdapterDryRunCredentialAuthorizationError) as exc:
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_PACKET_INVALID"
        ) from exc
    actual = packet.model_dump(mode="json")
    source = _source(packet.source_endpoint_allowlist_evaluation_packet)
    _validate_source(source)
    source_raw = source.model_dump(mode="json")
    if packet.source_endpoint_allowlist_evaluation_id != (
        source.live_adapter_dry_run_endpoint_allowlist_evaluation_id
    ):
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_SOURCE_ID_MISMATCH"
        )
    if packet.source_endpoint_allowlist_evaluation_hash != (
        source.live_adapter_dry_run_endpoint_allowlist_evaluation_hash
    ):
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_SOURCE_HASH_MISMATCH"
        )
    if packet.request_dispatch_state != "NOT_DISPATCHED":
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_SOURCE_DISPATCHED"
        )
    for field in COPIED_FIELDS:
        if _json_value(getattr(packet, field)) != _json_value(source_raw[field]):
            raise LiveAdapterDryRunCredentialAuthorizationError(
                "LADRCR_SOURCE_FIELD_MISMATCH"
            )
    if (
        packet.source_dispatch_readiness_hash
        != source.source_dispatch_readiness_hash
        or packet.source_live_adapter_dry_run_request_hash
        != source.source_live_adapter_dry_run_request_hash
    ):
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_LINEAGE_MISMATCH"
        )
    reference_raw = packet.credential_reference.model_dump(mode="json")
    snapshot_raw = packet.credential_policy_snapshot.model_dump(mode="json")
    _normalized_timestamp(packet.credential_reference.declared_at)
    _normalized_timestamp(packet.credential_policy_snapshot
                          .credential_policy_generated_at)
    if packet.credential_reference_digest != _digest(
        REFERENCE_DOMAIN, reference_raw
    ):
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_REFERENCE_DIGEST_MISMATCH"
        )
    snapshot_hash = _policy_snapshot_hash(snapshot_raw)
    if (
        packet.credential_policy_snapshot_hash != snapshot_hash
        or packet.credential_policy_snapshot.credential_policy_snapshot_hash
        != snapshot_hash
    ):
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_POLICY_HASH_MISMATCH"
        )
    result = _evaluation(packet.credential_reference,
                         packet.credential_policy_snapshot)
    if (
        _json_value(packet.credential_authorization_result) != result
        or packet.credential_authorization_result_digest
        != _digest(RESULT_DOMAIN, result)
    ):
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_RESULT_MISMATCH"
        )
    binding = _scope_binding(source, packet.credential_reference)
    if (
        packet.credential_scope_binding != binding
        or packet.credential_scope_binding_digest
        != _digest(SCOPE_BINDING_DOMAIN, binding)
    ):
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_SCOPE_BINDING_MISMATCH"
        )
    checks = _checks(source.live_adapter_dry_run_endpoint_allowlist_evaluation_hash,
                     result)
    if (
        _json_value(packet.credential_authorization_checks) != checks
        or packet.credential_authorization_check_digest
        != _digest(CHECKS_DOMAIN, checks)
    ):
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_CHECKS_MISMATCH"
        )
    requirements = _requirements()
    if (
        _json_value(packet.future_dispatch_review_requirements) != requirements
        or packet.future_dispatch_review_requirement_digest
        != _digest(FUTURE_REVIEW_DOMAIN, requirements)
    ):
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_REQUIREMENTS_MISMATCH"
        )
    if packet.fail_closed is result["authorized"]:
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_FAIL_CLOSED_MISMATCH"
        )
    if packet.scope_limitations != SCOPE_LIMITATIONS:
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_SCOPE_LIMITATIONS_MISMATCH"
        )
    if datetime.fromisoformat(
        _normalized_timestamp(packet.credential_authorization_evaluated_at)
    ) < datetime.fromisoformat(
        _normalized_timestamp(source.endpoint_allowlist_evaluated_at)
    ):
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_EVALUATED_TOO_EARLY"
        )
    digest = _packet_hash(actual)
    if packet.live_adapter_dry_run_credential_authorization_evaluation_hash != digest:
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_PACKET_HASH_MISMATCH"
        )
    if packet.live_adapter_dry_run_credential_authorization_evaluation_id != (
        f"ladrcr:v1:sha256:{digest}"
    ):
        raise LiveAdapterDryRunCredentialAuthorizationError(
            "LADRCR_PACKET_ID_MISMATCH"
        )
    return packet
