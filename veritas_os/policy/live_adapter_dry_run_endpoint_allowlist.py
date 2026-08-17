"""Create deterministic endpoint-allowlist evidence without external effects.

This module compares declared data only.  It intentionally has no endpoint
resolution, credential, adapter, network, persistence, or dispatch capability.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.live_adapter_dry_run_dispatch_readiness import (
    CanonicalLiveAdapterDryRunDispatchReadinessPacket,
    LiveAdapterDryRunDispatchReadinessError,
    verify_live_adapter_dry_run_dispatch_readiness_packet,
)

FORMAT_VERSION = "canonical-live-adapter-dry-run-endpoint-allowlist-evaluation/v1"
EVALUATION_MECHANISM = (
    "evaluate_live_adapter_dry_run_endpoint_allowlist_without_resolution/v1"
)
STATUS = "LIVE_ADAPTER_DRY_RUN_ENDPOINT_ALLOWLIST_EVALUATED_NOT_DISPATCHED"
CHECK_MODE = "deterministic_local_endpoint_allowlist_evaluation_only"
CANDIDATE_DOMAIN = "veritas.live-adapter-dry-run-endpoint-allowlist.candidate/v1"
SNAPSHOT_DOMAIN = "veritas.live-adapter-dry-run-endpoint-allowlist.snapshot/v1"
EVALUATION_DOMAIN = "veritas.live-adapter-dry-run-endpoint-allowlist.evaluation/v1"
IDENTITY_DOMAIN = "veritas.live-adapter-dry-run-endpoint-allowlist.identity-binding/v1"
CHECKS_DOMAIN = "veritas.live-adapter-dry-run-endpoint-allowlist.checks/v1"
FUTURE_CREDENTIAL_REQUIREMENTS_DOMAIN = (
    "veritas.live-adapter-dry-run-endpoint-allowlist.future-credential-requirements/v1"
)
PACKET_DOMAIN = "veritas.live-adapter-dry-run-endpoint-allowlist.packet/v1"

CHECK_NAMES = (
    "source_dispatch_readiness_verified", "source_request_not_dispatched",
    "endpoint_candidate_closed_schema_valid",
    "endpoint_candidate_contains_no_credentials",
    "endpoint_candidate_contains_no_authorization_headers",
    "endpoint_candidate_contains_no_tokens", "endpoint_candidate_contains_no_secrets",
    "allowlist_snapshot_closed_schema_valid", "allowlist_snapshot_hash_verified",
    "allowlist_entry_active_status_required", "endpoint_scheme_exact_match",
    "endpoint_host_exact_match", "endpoint_port_exact_match",
    "endpoint_path_prefix_exact_match", "endpoint_environment_exact_match",
    "adapter_contract_id_allowed", "target_system_allowed",
    "target_resource_scope_allowed", "endpoint_purpose_allowed",
    "endpoint_identity_binding_constructed", "endpoint_not_resolved",
    "dns_not_used", "network_not_used", "credential_not_accessed",
    "webhook_not_called", "live_adapter_not_instantiated", "bind_not_invoked",
    "bind_receipt_not_created", "trustlog_not_written",
    "future_credential_gate_required",
)
EFFECT_FIELDS = (
    "endpoint_resolved", "dns_used", "network_used", "credential_material_accessed",
    "credential_material_embedded", "authorization_header_embedded", "token_embedded",
    "secret_embedded", "webhook_called", "live_adapter_instantiated",
    "live_adapter_method_called", "request_dispatched", "bind_invoked",
    "bind_receipt_created", "trustlog_written", "external_effect_used",
    "filesystem_used", "database_used", "provider_used", "subprocess_used",
    "operation_committed",
)
SCOPE_LIMITATIONS = (
    "NOT_DISPATCHED", "NOT_ENDPOINT_RESOLUTION", "NOT_DNS_RESOLUTION",
    "NOT_NETWORK_CALL", "NOT_WEBHOOK_CALL", "NOT_CREDENTIAL_RESOLUTION",
    "NOT_CREDENTIAL_ACCESS", "NOT_CREDENTIAL_EMBEDDING",
    "NOT_AUTHORIZATION_HEADER", "NOT_TOKEN", "NOT_SECRET",
    "NOT_LIVE_ADAPTER_INSTANCE", "NOT_LIVE_ADAPTER_RESULT",
    "NOT_BIND_AUTHORIZATION", "NOT_BIND_RECEIPT", "NOT_TRUSTLOG_WRITE",
    "NOT_OPERATION_COMMIT", "NOT_PRODUCTION_CLAIM", "NOT_CUSTOMER_CLAIM",
    "NOT_REGULATORY_CERTIFICATION",
)
FUTURE_REQUIREMENT_NAMES = (
    "credential_resolution_authorization", "credential_source_identity",
    "credential_scope_binding", "credential_material_non_embedding",
    "authorization_header_construction_boundary", "credential_redaction_boundary",
    "operator_human_credential_review", "bind_pre_dispatch_review",
    "network_dispatch_boundary_remains_separate",
)
COPIED_FIELDS = (
    "request_descriptor", "execution_intent", "execution_intent_id",
    "execution_intent_hash", "adapter_contract_descriptor", "adapter_contract_id",
    "adapter_contract_hash", "adapter_contract_version",
    "source_to_execution_intent_mapping", "field_mapping_proof",
    "required_field_presence", "source_decision_identity", "candidate_identity",
    "evidence_lineage", "replay_summary",
)
EXACT_FIELDS = (
    "endpoint_kind", "endpoint_scheme", "endpoint_host", "endpoint_port",
    "endpoint_path_prefix", "endpoint_environment", "adapter_contract_id",
    "target_system", "target_resource_scope", "endpoint_purpose",
)
PROHIBITED_KEYS = (
    "authorization", "authorization_header", "token", "secret", "cookie",
    "credential", "credentials", "request_body", "body",
)


class LiveAdapterDryRunEndpointAllowlistError(ValueError):
    """Stable fail-closed refusal for invalid endpoint-allowlist evidence."""


class EndpointCandidate(BaseModel):
    """Closed, data-only endpoint declaration."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    endpoint_candidate_id: str = Field(min_length=1)
    endpoint_kind: str = Field(min_length=1)
    endpoint_scheme: str = Field(min_length=1)
    endpoint_host: str = Field(min_length=1)
    endpoint_port: int = Field(ge=1, le=65535)
    endpoint_path_prefix: str
    endpoint_environment: str = Field(min_length=1)
    endpoint_purpose: str = Field(min_length=1)
    adapter_contract_id: str = Field(min_length=1)
    target_system: str = Field(min_length=1)
    target_resource_scope: str = Field(min_length=1)
    declared_by: str = Field(min_length=1)
    declared_at: str


class AllowlistEntry(BaseModel):
    """One exact local allowlist entry."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    entry_id: str = Field(min_length=1)
    endpoint_kind: str
    endpoint_scheme: str
    endpoint_host: str
    endpoint_port: int = Field(ge=1, le=65535)
    endpoint_path_prefix: str
    endpoint_environment: str
    allowed_adapter_contract_ids: tuple[str, ...]
    allowed_target_systems: tuple[str, ...]
    allowed_target_resource_scopes: tuple[str, ...]
    allowed_purposes: tuple[str, ...]
    entry_status: Literal["ACTIVE", "INACTIVE"]


class EndpointAllowlistSnapshot(BaseModel):
    """Closed deterministic snapshot supplied by the caller."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    allowlist_snapshot_id: str = Field(min_length=1)
    allowlist_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    allowlist_version: str = Field(min_length=1)
    allowlist_source: str = Field(min_length=1)
    allowlist_generated_at: str
    allowlist_entries: tuple[AllowlistEntry, ...]
    allowlist_scope_limitations: tuple[str, ...]


class AllowlistEvaluationResult(BaseModel):
    """Exact comparison outcome; never a semantic safety inference."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    matched: bool
    matched_entry_id: str | None
    match_reason: str
    mismatch_reasons: tuple[str, ...]
    comparison_mode: Literal["exact_local_allowlist_comparison_only"]
    exact_fields_compared: tuple[str, ...]
    semantic_match_used: Literal[False]


class EndpointAllowlistCheck(BaseModel):
    """One ordered local check with explicit non-effect claims."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    check_id: str
    ordinal: int = Field(ge=1, le=30)
    name: Literal[*CHECK_NAMES]
    mode: Literal[CHECK_MODE]
    passed: bool
    evidence_ref: str
    endpoint_resolved: Literal[False]
    dns_used: Literal[False]
    network_used: Literal[False]
    credential_material_accessed: Literal[False]
    credential_material_embedded: Literal[False]
    authorization_header_embedded: Literal[False]
    token_embedded: Literal[False]
    secret_embedded: Literal[False]
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


class FutureCredentialRequirement(BaseModel):
    """A credential gate explicitly not satisfied by this packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1, le=9)
    name: Literal[*FUTURE_REQUIREMENT_NAMES]
    separate_future_artifact_required: Literal[True]
    satisfied_by_this_packet: Literal[False]


class CanonicalLiveAdapterDryRunEndpointAllowlistEvaluationPacket(BaseModel):
    """Closed content-addressed endpoint allowlist evaluation packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    live_adapter_dry_run_endpoint_allowlist_evaluation_id: str
    live_adapter_dry_run_endpoint_allowlist_evaluation_hash: str
    endpoint_allowlist_evaluation_mechanism: Literal[EVALUATION_MECHANISM]
    endpoint_allowlist_evaluated_at: str
    source_dispatch_readiness_id: str
    source_dispatch_readiness_hash: str
    source_dispatch_readiness_packet: dict[str, Any]
    source_live_adapter_dry_run_request_id: str
    source_live_adapter_dry_run_request_hash: str
    request_descriptor: dict[str, Any]
    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str
    adapter_contract_descriptor: dict[str, Any]
    adapter_contract_id: str
    adapter_contract_hash: str
    adapter_contract_version: str
    endpoint_candidate: EndpointCandidate
    endpoint_candidate_digest: str
    allowlist_snapshot: EndpointAllowlistSnapshot
    allowlist_snapshot_hash: str
    allowlist_evaluation_result: AllowlistEvaluationResult
    allowlist_evaluation_digest: str
    endpoint_identity_binding: dict[str, Any]
    endpoint_identity_binding_digest: str
    endpoint_allowlist_checks: tuple[EndpointAllowlistCheck, ...]
    endpoint_allowlist_check_digest: str
    future_credential_requirements: tuple[FutureCredentialRequirement, ...]
    future_credential_requirement_digest: str
    source_to_execution_intent_mapping: dict[str, Any]
    field_mapping_proof: dict[str, Any]
    required_field_presence: dict[str, str]
    source_decision_identity: dict[str, Any]
    candidate_identity: dict[str, Any]
    evidence_lineage: dict[str, Any]
    replay_summary: dict[str, Any]
    endpoint_allowlist_status: Literal[STATUS]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    endpoint_resolved: Literal[False]
    network_used: Literal[False]
    credential_material_accessed: Literal[False]
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
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc).isoformat()


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise LiveAdapterDryRunEndpointAllowlistError("LADREA_PACKET_INVALID")
        return value
    if isinstance(value, datetime):
        return _normalized_timestamp(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise LiveAdapterDryRunEndpointAllowlistError("LADREA_PACKET_INVALID")


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json_value(value)}, allow_nan=False,
        ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _snapshot_hash(raw: dict[str, Any]) -> str:
    return _digest(SNAPSHOT_DOMAIN, {
        key: value for key, value in raw.items() if key != "allowlist_snapshot_hash"
    })


def _packet_hash(raw: dict[str, Any]) -> str:
    omitted = {
        "live_adapter_dry_run_endpoint_allowlist_evaluation_id",
        "live_adapter_dry_run_endpoint_allowlist_evaluation_hash",
    }
    return _digest(PACKET_DOMAIN, {key: value for key, value in raw.items()
                                   if key not in omitted})


def _reject_sensitive_keys(value: Any) -> None:
    if not isinstance(value, dict):
        return
    for key in value:
        normalized = key.lower().replace("-", "_")
        if normalized in PROHIBITED_KEYS:
            raise LiveAdapterDryRunEndpointAllowlistError("LADREA_SENSITIVE_INPUT")


def _evaluation(candidate: EndpointCandidate, snapshot: EndpointAllowlistSnapshot) -> dict[str, Any]:
    field_failures: set[str] = set()
    active_seen = False
    for entry in snapshot.allowlist_entries:
        if entry.entry_status != "ACTIVE":
            continue
        active_seen = True
        comparisons = {
            "endpoint_kind": candidate.endpoint_kind == entry.endpoint_kind,
            "endpoint_scheme": candidate.endpoint_scheme == entry.endpoint_scheme,
            "endpoint_host": candidate.endpoint_host == entry.endpoint_host,
            "endpoint_port": candidate.endpoint_port == entry.endpoint_port,
            "endpoint_path_prefix": candidate.endpoint_path_prefix == entry.endpoint_path_prefix,
            "endpoint_environment": candidate.endpoint_environment == entry.endpoint_environment,
            "adapter_contract_id": candidate.adapter_contract_id in entry.allowed_adapter_contract_ids,
            "target_system": candidate.target_system in entry.allowed_target_systems,
            "target_resource_scope": candidate.target_resource_scope in entry.allowed_target_resource_scopes,
            "endpoint_purpose": candidate.endpoint_purpose in entry.allowed_purposes,
        }
        if all(comparisons.values()):
            return {"matched": True, "matched_entry_id": entry.entry_id,
                    "match_reason": "active_entry_exact_match", "mismatch_reasons": [],
                    "comparison_mode": "exact_local_allowlist_comparison_only",
                    "exact_fields_compared": list(EXACT_FIELDS), "semantic_match_used": False}
        field_failures.update(name for name, passed in comparisons.items() if not passed)
    reasons = (["no_active_allowlist_entry"] if not active_seen else
               [f"{name}_mismatch" for name in EXACT_FIELDS if name in field_failures])
    return {"matched": False, "matched_entry_id": None,
            "match_reason": "no_active_exact_match", "mismatch_reasons": reasons,
            "comparison_mode": "exact_local_allowlist_comparison_only",
            "exact_fields_compared": list(EXACT_FIELDS), "semantic_match_used": False}


def _identity(source: CanonicalLiveAdapterDryRunDispatchReadinessPacket,
              candidate: EndpointCandidate, snapshot: EndpointAllowlistSnapshot) -> dict[str, Any]:
    return {
        "source_dispatch_readiness_id": source.live_adapter_dry_run_dispatch_readiness_id,
        "endpoint_candidate_id": candidate.endpoint_candidate_id,
        "adapter_contract_id": candidate.adapter_contract_id,
        "allowlist_snapshot_id": snapshot.allowlist_snapshot_id,
    }


def _requirements() -> list[dict[str, Any]]:
    return [{"ordinal": ordinal, "name": name,
             "separate_future_artifact_required": True,
             "satisfied_by_this_packet": False}
            for ordinal, name in enumerate(FUTURE_REQUIREMENT_NAMES, 1)]


def _checks(source_hash: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    match_checks = set(CHECK_NAMES[9:19])
    return [{
        "check_id": f"ladrea-check:v1:{ordinal}:{name.replace('_', '-')}",
        "ordinal": ordinal, "name": name, "mode": CHECK_MODE,
        "passed": result["matched"] if name in match_checks else True,
        "evidence_ref": f"source_dispatch_readiness_hash:{source_hash}:{name}",
        **{field: False for field in EFFECT_FIELDS},
    } for ordinal, name in enumerate(CHECK_NAMES, 1)]


def _source(value: Any) -> CanonicalLiveAdapterDryRunDispatchReadinessPacket:
    try:
        return verify_live_adapter_dry_run_dispatch_readiness_packet(value)
    except (LiveAdapterDryRunDispatchReadinessError, TypeError, ValueError) as exc:
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_SOURCE_INVALID") from exc


def build_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(
    source_dispatch_readiness_packet: Any, endpoint_candidate: Any,
    allowlist_snapshot: Any, endpoint_allowlist_evaluated_at: datetime,
) -> CanonicalLiveAdapterDryRunEndpointAllowlistEvaluationPacket:
    """Build and self-verify a purely local exact allowlist evaluation."""
    evaluated_at = _normalized_timestamp(endpoint_allowlist_evaluated_at)
    source = _source(_json_value(source_dispatch_readiness_packet))
    if source.request_dispatch_state != "NOT_DISPATCHED":
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_SOURCE_DISPATCHED")
    if source.dispatch_readiness_status != (
        "LIVE_ADAPTER_DRY_RUN_DISPATCH_READINESS_EVALUATED_NOT_DISPATCHED"
    ):
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_SOURCE_STATUS_INVALID")
    candidate_input = _json_value(endpoint_candidate)
    _reject_sensitive_keys(candidate_input)
    try:
        candidate = EndpointCandidate.model_validate(candidate_input)
        snapshot = EndpointAllowlistSnapshot.model_validate(_json_value(allowlist_snapshot))
    except ValidationError as exc:
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_INPUT_INVALID") from exc
    candidate_raw = candidate.model_dump(mode="json")
    snapshot_raw = snapshot.model_dump(mode="json")
    _normalized_timestamp(candidate.declared_at)
    _normalized_timestamp(snapshot.allowlist_generated_at)
    if snapshot.allowlist_snapshot_hash != _snapshot_hash(snapshot_raw):
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_SNAPSHOT_HASH_INVALID")
    if datetime.fromisoformat(evaluated_at) < datetime.fromisoformat(
        _normalized_timestamp(source.dispatch_readiness_evaluated_at)
    ):
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_EVALUATED_TOO_EARLY")
    result = _evaluation(candidate, snapshot)
    identity = _identity(source, candidate, snapshot)
    checks = _checks(source.live_adapter_dry_run_dispatch_readiness_hash, result)
    requirements = _requirements()
    source_raw = source.model_dump(mode="json")
    raw = {
        "format_version": FORMAT_VERSION,
        "endpoint_allowlist_evaluation_mechanism": EVALUATION_MECHANISM,
        "endpoint_allowlist_evaluated_at": evaluated_at,
        "source_dispatch_readiness_id": source.live_adapter_dry_run_dispatch_readiness_id,
        "source_dispatch_readiness_hash": source.live_adapter_dry_run_dispatch_readiness_hash,
        "source_dispatch_readiness_packet": source_raw,
        "source_live_adapter_dry_run_request_id": source.source_live_adapter_dry_run_request_id,
        "source_live_adapter_dry_run_request_hash": source.source_live_adapter_dry_run_request_hash,
        **{field: source_raw[field] for field in COPIED_FIELDS},
        "endpoint_candidate": candidate_raw,
        "endpoint_candidate_digest": _digest(CANDIDATE_DOMAIN, candidate_raw),
        "allowlist_snapshot": snapshot_raw,
        "allowlist_snapshot_hash": snapshot.allowlist_snapshot_hash,
        "allowlist_evaluation_result": result,
        "allowlist_evaluation_digest": _digest(EVALUATION_DOMAIN, result),
        "endpoint_identity_binding": identity,
        "endpoint_identity_binding_digest": _digest(IDENTITY_DOMAIN, identity),
        "endpoint_allowlist_checks": checks,
        "endpoint_allowlist_check_digest": _digest(CHECKS_DOMAIN, checks),
        "future_credential_requirements": requirements,
        "future_credential_requirement_digest": _digest(
            FUTURE_CREDENTIAL_REQUIREMENTS_DOMAIN, requirements),
        "endpoint_allowlist_status": STATUS, "request_dispatch_state": "NOT_DISPATCHED",
        **{field: False for field in ("endpoint_resolved", "network_used",
           "credential_material_accessed", "live_adapter_instantiated", "webhook_called",
           "bind_invoked", "bind_receipt_created", "trustlog_written")},
        "fail_closed": not result["matched"], "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_endpoint_allowlist_evaluation_hash"] = digest
    raw["live_adapter_dry_run_endpoint_allowlist_evaluation_id"] = f"ladrea:v1:sha256:{digest}"
    return verify_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(raw)


def verify_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(
    raw: Any,
) -> CanonicalLiveAdapterDryRunEndpointAllowlistEvaluationPacket:
    """Recompute every source binding, outcome, check, digest, hash, and ID."""
    try:
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else _json_value(raw)
        packet = CanonicalLiveAdapterDryRunEndpointAllowlistEvaluationPacket.model_validate(value)
    except (ValidationError, TypeError, LiveAdapterDryRunEndpointAllowlistError) as exc:
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_PACKET_INVALID") from exc
    actual = packet.model_dump(mode="json")
    source = _source(packet.source_dispatch_readiness_packet)
    source_raw = source.model_dump(mode="json")
    if packet.source_dispatch_readiness_id != source.live_adapter_dry_run_dispatch_readiness_id:
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_SOURCE_ID_MISMATCH")
    if packet.source_dispatch_readiness_hash != source.live_adapter_dry_run_dispatch_readiness_hash:
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_SOURCE_HASH_MISMATCH")
    if source.request_dispatch_state != "NOT_DISPATCHED" or packet.request_dispatch_state != "NOT_DISPATCHED":
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_SOURCE_DISPATCHED")
    if source.dispatch_readiness_status != "LIVE_ADAPTER_DRY_RUN_DISPATCH_READINESS_EVALUATED_NOT_DISPATCHED":
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_SOURCE_STATUS_INVALID")
    for field in COPIED_FIELDS:
        if _json_value(getattr(packet, field)) != _json_value(source_raw[field]):
            raise LiveAdapterDryRunEndpointAllowlistError("LADREA_SOURCE_FIELD_MISMATCH")
    if packet.source_live_adapter_dry_run_request_id != source.source_live_adapter_dry_run_request_id or packet.source_live_adapter_dry_run_request_hash != source.source_live_adapter_dry_run_request_hash:
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_LINEAGE_MISMATCH")
    candidate_raw = packet.endpoint_candidate.model_dump(mode="json")
    snapshot_raw = packet.allowlist_snapshot.model_dump(mode="json")
    _normalized_timestamp(packet.endpoint_candidate.declared_at)
    _normalized_timestamp(packet.allowlist_snapshot.allowlist_generated_at)
    if packet.endpoint_candidate_digest != _digest(CANDIDATE_DOMAIN, candidate_raw):
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_CANDIDATE_DIGEST_MISMATCH")
    snapshot_hash = _snapshot_hash(snapshot_raw)
    if packet.allowlist_snapshot_hash != snapshot_hash or packet.allowlist_snapshot.allowlist_snapshot_hash != snapshot_hash:
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_SNAPSHOT_HASH_MISMATCH")
    result = _evaluation(packet.endpoint_candidate, packet.allowlist_snapshot)
    if _json_value(packet.allowlist_evaluation_result) != result or packet.allowlist_evaluation_digest != _digest(EVALUATION_DOMAIN, result):
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_EVALUATION_MISMATCH")
    identity = _identity(source, packet.endpoint_candidate, packet.allowlist_snapshot)
    if packet.endpoint_identity_binding != identity or packet.endpoint_identity_binding_digest != _digest(IDENTITY_DOMAIN, identity):
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_IDENTITY_MISMATCH")
    checks = _checks(source.live_adapter_dry_run_dispatch_readiness_hash, result)
    if _json_value(packet.endpoint_allowlist_checks) != checks or packet.endpoint_allowlist_check_digest != _digest(CHECKS_DOMAIN, checks):
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_CHECKS_MISMATCH")
    requirements = _requirements()
    if _json_value(packet.future_credential_requirements) != requirements or packet.future_credential_requirement_digest != _digest(FUTURE_CREDENTIAL_REQUIREMENTS_DOMAIN, requirements):
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_REQUIREMENTS_MISMATCH")
    if packet.fail_closed is result["matched"] or packet.scope_limitations != SCOPE_LIMITATIONS:
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_FAIL_CLOSED_MISMATCH")
    if datetime.fromisoformat(_normalized_timestamp(packet.endpoint_allowlist_evaluated_at)) < datetime.fromisoformat(_normalized_timestamp(source.dispatch_readiness_evaluated_at)):
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_EVALUATED_TOO_EARLY")
    digest = _packet_hash(actual)
    if packet.live_adapter_dry_run_endpoint_allowlist_evaluation_hash != digest:
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_PACKET_HASH_MISMATCH")
    if packet.live_adapter_dry_run_endpoint_allowlist_evaluation_id != f"ladrea:v1:sha256:{digest}":
        raise LiveAdapterDryRunEndpointAllowlistError("LADREA_PACKET_ID_MISMATCH")
    return packet
