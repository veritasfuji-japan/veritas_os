"""Evaluate a promotion-native endpoint allowlist without external effects.

The builder and verifier operate exclusively on caller-supplied canonical data.
They never resolve or contact an endpoint, access credentials, instantiate an
adapter, invoke Bind, persist evidence, or perform another external effect.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.bind_adapter_contract_selection import (
    BindAdapterContractSelectionError,
    verify_bind_adapter_contract_descriptor,
)
from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_dispatch_readiness import (
    CanonicalPromotionLiveAdapterDryRunDispatchReadinessError,
    CanonicalPromotionLiveAdapterDryRunDispatchReadinessPacket,
    verify_canonical_promotion_live_adapter_dry_run_dispatch_readiness_packet,
)

FORMAT_VERSION = "canonical-promotion-live-adapter-dry-run-endpoint-allowlist-evaluation/v1"
EVALUATION_MECHANISM = "evaluate_promotion_live_adapter_dry_run_endpoint_allowlist_without_resolution/v1"
STATUS = "PROMOTION_NATIVE_ENDPOINT_ALLOWLIST_EVALUATED_NOT_DISPATCHED"
CHECK_MODE = "deterministic_local_endpoint_allowlist_evaluation_only"
PREFIX = "veritas.promotion-live-adapter-dry-run-endpoint-allowlist"
CANDIDATE_DOMAIN = PREFIX + ".candidate/v1"
SNAPSHOT_DOMAIN = PREFIX + ".snapshot/v1"
EVALUATION_DOMAIN = PREFIX + ".evaluation/v1"
IDENTITY_DOMAIN = PREFIX + ".identity-binding/v1"
CHECKS_DOMAIN = PREFIX + ".checks/v1"
FUTURE_REQUIREMENTS_DOMAIN = PREFIX + ".future-requirements/v1"
PACKET_DOMAIN = PREFIX + ".packet/v1"
EXACT_FIELDS = (
    "endpoint_kind", "endpoint_scheme", "endpoint_host", "endpoint_port",
    "endpoint_path_prefix", "endpoint_environment", "adapter_contract_id",
    "target_system", "target_resource_scope", "endpoint_purpose",
)
PROHIBITED_KEYS = frozenset({
    "authorization", "authorization_header", "token", "secret", "cookie",
    "credential", "credentials", "request_body", "body",
})
LINEAGE_FIELDS = (
    "source_live_adapter_dry_run_readiness_id", "source_live_adapter_dry_run_readiness_hash",
    "source_reference_rehearsal_id", "source_reference_rehearsal_hash",
    "source_adapter_dry_run_fixture_result_id", "source_adapter_dry_run_fixture_result_hash",
    "source_adapter_dry_run_plan_id", "source_adapter_dry_run_plan_hash",
    "source_adapter_contract_selection_id", "source_adapter_contract_selection_hash",
    "source_bind_preflight_adjudication_id", "source_bind_preflight_adjudication_hash",
    "source_pre_bind_validation_id", "source_pre_bind_validation_hash",
    "source_readiness_id", "source_readiness_hash", "source_promotion_id",
    "source_promotion_hash", "source_decision_identity", "candidate_identity",
    "selected_action_lineage", "policy_snapshot_lineage", "approval_context", "policy_lineage",
)
CHECK_NAMES = (
    "source_promotion_native_dispatch_readiness_verified", "source_request_not_dispatched",
    "endpoint_candidate_closed_schema_valid", "candidate_contains_no_credentials_tokens_secrets",
    "candidate_binds_exact_adapter", "candidate_binds_exact_target_system_resource",
    "allowlist_snapshot_closed_schema_valid", "allowlist_snapshot_hash_verified",
    "active_entry_required", "all_exact_endpoint_dimensions_compared",
    "endpoint_identity_binding_constructed", "endpoint_not_resolved", "dns_not_used",
    "network_not_used", "credential_not_accessed", "webhook_not_called",
    "adapter_not_instantiated", "bind_not_invoked", "trustlog_not_written",
    "future_promotion_native_credential_gate_required",
)
FUTURE_REQUIREMENT_NAMES = (
    "promotion_native_credential_authorization_evaluation", "credential_source_identity_verification",
    "credential_scope_binding", "credential_material_non_embedding", "operator_review",
    "bind_pre_dispatch_review", "fresh_source_gate", "gate_bound_human_approval",
    "authority_evidence_verification", "real_bind_authorization", "network_dispatch",
    "external_effect", "postcondition_and_reconciliation",
)
EFFECT_FIELDS = (
    "endpoint_resolved", "endpoint_contacted", "dns_used", "network_used",
    "credential_resolved", "credential_accessed", "credential_material_embedded",
    "authorization_header_constructed", "token_embedded", "secret_embedded",
    "webhook_invoked", "live_adapter_instantiated", "live_adapter_method_invoked",
    "request_dispatched", "bind_invoked", "bind_authorization_issued",
    "bind_receipt_created", "trustlog_written", "filesystem_used", "database_used",
    "provider_called", "subprocess_used", "external_effect_used", "operation_committed",
    "apply_performed", "postcondition_verified", "rollback_or_revert_performed",
)

class CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError(ValueError):
    """Stable fail-closed error for invalid promotion-native endpoint evidence."""

class EndpointCandidate(BaseModel):
    """Closed metadata-only endpoint candidate."""
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
    """Closed content-addressed local allowlist snapshot."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    allowlist_snapshot_id: str = Field(min_length=1)
    allowlist_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    allowlist_version: str = Field(min_length=1)
    allowlist_source: str = Field(min_length=1)
    allowlist_generated_at: str
    allowlist_entries: tuple[AllowlistEntry, ...]
    allowlist_scope_limitations: tuple[str, ...]

class AllowlistEvaluationResult(BaseModel):
    """Exact comparison result, including deterministic refusal reasons."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    matched: bool
    matched_entry_id: str | None
    match_reason: str
    mismatch_reasons: tuple[str, ...]
    comparison_mode: Literal["exact_local_allowlist_comparison_only"]
    exact_fields_compared: tuple[Literal[*EXACT_FIELDS], ...]
    semantic_match_used: Literal[False]

class EndpointAllowlistCheck(BaseModel):
    """One reconstructed ordered check with explicit no-effect state."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    check_id: str
    ordinal: int = Field(ge=1, le=len(CHECK_NAMES))
    name: Literal[*CHECK_NAMES]
    mode: Literal[CHECK_MODE]
    passed: bool
    evidence_ref: str
    endpoint_resolved: Literal[False]
    endpoint_contacted: Literal[False]
    dns_used: Literal[False]
    network_used: Literal[False]
    credential_resolved: Literal[False]
    credential_accessed: Literal[False]
    credential_material_embedded: Literal[False]
    authorization_header_constructed: Literal[False]
    token_embedded: Literal[False]
    secret_embedded: Literal[False]
    webhook_invoked: Literal[False]
    live_adapter_instantiated: Literal[False]
    live_adapter_method_invoked: Literal[False]
    request_dispatched: Literal[False]
    bind_invoked: Literal[False]
    bind_authorization_issued: Literal[False]
    bind_receipt_created: Literal[False]
    trustlog_written: Literal[False]
    filesystem_used: Literal[False]
    database_used: Literal[False]
    provider_called: Literal[False]
    subprocess_used: Literal[False]
    external_effect_used: Literal[False]
    operation_committed: Literal[False]
    apply_performed: Literal[False]
    postcondition_verified: Literal[False]
    rollback_or_revert_performed: Literal[False]

class FutureRequirement(BaseModel):
    """A security boundary explicitly left unsatisfied."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1, le=len(FUTURE_REQUIREMENT_NAMES))
    name: Literal[*FUTURE_REQUIREMENT_NAMES]
    separate_future_artifact_required: Literal[True]
    satisfied_by_this_packet: Literal[False]

class CanonicalPromotionLiveAdapterDryRunEndpointAllowlistEvaluationPacket(BaseModel):
    """Content-addressed promotion-native endpoint evaluation evidence."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_id: str = Field(pattern=r"^pladrea:v1:sha256:[0-9a-f]{64}$")
    promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
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
    source_live_adapter_dry_run_readiness_id: str
    source_live_adapter_dry_run_readiness_hash: str
    source_reference_rehearsal_id: str
    source_reference_rehearsal_hash: str
    source_adapter_dry_run_fixture_result_id: str
    source_adapter_dry_run_fixture_result_hash: str
    source_adapter_dry_run_plan_id: str
    source_adapter_dry_run_plan_hash: str
    source_adapter_contract_selection_id: str
    source_adapter_contract_selection_hash: str
    source_bind_preflight_adjudication_id: str
    source_bind_preflight_adjudication_hash: str
    source_pre_bind_validation_id: str
    source_pre_bind_validation_hash: str
    source_readiness_id: str
    source_readiness_hash: str
    source_promotion_id: str
    source_promotion_hash: str
    source_decision_identity: dict[str, Any]
    candidate_identity: dict[str, Any]
    selected_action_lineage: dict[str, Any]
    policy_snapshot_lineage: dict[str, Any]
    approval_context: dict[str, Any]
    policy_lineage: dict[str, Any]
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
    future_requirements: tuple[FutureRequirement, ...]
    future_requirement_digest: str
    endpoint_allowlist_status: Literal[STATUS]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    ready_for_promotion_native_credential_authorization_evaluation: bool
    fail_closed: bool
    human_approval_proven: Literal[False]
    authority_evidence_proven: Literal[False]
    endpoint_resolved: Literal[False]
    endpoint_contacted: Literal[False]
    dns_used: Literal[False]
    network_used: Literal[False]
    credential_resolved: Literal[False]
    credential_accessed: Literal[False]
    credential_material_embedded: Literal[False]
    authorization_header_constructed: Literal[False]
    token_embedded: Literal[False]
    secret_embedded: Literal[False]
    webhook_invoked: Literal[False]
    live_adapter_instantiated: Literal[False]
    live_adapter_method_invoked: Literal[False]
    request_dispatched: Literal[False]
    bind_invoked: Literal[False]
    bind_authorization_issued: Literal[False]
    bind_receipt_created: Literal[False]
    trustlog_written: Literal[False]
    filesystem_used: Literal[False]
    database_used: Literal[False]
    provider_called: Literal[False]
    subprocess_used: Literal[False]
    external_effect_used: Literal[False]
    operation_committed: Literal[False]
    apply_performed: Literal[False]
    postcondition_verified: Literal[False]
    rollback_or_revert_performed: Literal[False]

def _fail(code: str) -> None:
    raise CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError(code)

def _aware(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(code)
    return parsed

def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            _fail("PLADREA_PACKET_INVALID")
        return value
    if isinstance(value, datetime):
        return _aware(value, "PLADREA_TIMESTAMP_INVALID").isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    _fail("PLADREA_PACKET_INVALID")

def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps({"domain": domain, "value": _json_value(value)}, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()

def _snapshot_hash(raw: dict[str, Any]) -> str:
    return _digest(SNAPSHOT_DOMAIN, {key: value for key, value in raw.items() if key != "allowlist_snapshot_hash"})

def _packet_hash(raw: dict[str, Any]) -> str:
    omitted = {"promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_id", "promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_hash"}
    return _digest(PACKET_DOMAIN, {key: value for key, value in raw.items() if key not in omitted})

def _source(value: Any) -> CanonicalPromotionLiveAdapterDryRunDispatchReadinessPacket:
    try:
        source = verify_canonical_promotion_live_adapter_dry_run_dispatch_readiness_packet(value)
    except (CanonicalPromotionLiveAdapterDryRunDispatchReadinessError, TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError("PLADREA_SOURCE_INVALID") from exc
    if not source.ready_for_promotion_native_endpoint_allowlist_evaluation or source.request_dispatch_state != "NOT_DISPATCHED":
        _fail("PLADREA_SOURCE_NOT_READY")
    return source

def _validate_intent_adapter(source: CanonicalPromotionLiveAdapterDryRunDispatchReadinessPacket) -> ExecutionIntent:
    try:
        intent = ExecutionIntent(**source.execution_intent)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError("PLADREA_INTENT_INVALID") from exc
    if intent.to_dict() != source.execution_intent or intent.execution_intent_id != source.execution_intent_id or hash_execution_intent(intent) != source.execution_intent_hash:
        _fail("PLADREA_INTENT_MISMATCH")
    try:
        descriptor = verify_bind_adapter_contract_descriptor(source.adapter_contract_descriptor, intent)
    except BindAdapterContractSelectionError as exc:
        raise CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError("PLADREA_ADAPTER_INVALID") from exc
    if (descriptor.model_dump(mode="json") != source.adapter_contract_descriptor or descriptor.adapter_contract_id != source.adapter_contract_id or descriptor.adapter_contract_hash != source.adapter_contract_hash or descriptor.adapter_contract_version != source.adapter_contract_version):
        _fail("PLADREA_ADAPTER_MISMATCH")
    return intent

def _candidate(value: Any) -> EndpointCandidate:
    raw = _json_value(value)
    if isinstance(raw, dict) and any(key.lower().replace("-", "_") in PROHIBITED_KEYS for key in raw):
        _fail("PLADREA_SENSITIVE_INPUT")
    try:
        return EndpointCandidate.model_validate(raw)
    except ValidationError as exc:
        raise CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError("PLADREA_CANDIDATE_INVALID") from exc

def _snapshot(value: Any) -> EndpointAllowlistSnapshot:
    try:
        snapshot = EndpointAllowlistSnapshot.model_validate(_json_value(value))
    except ValidationError as exc:
        raise CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError("PLADREA_SNAPSHOT_INVALID") from exc
    if snapshot.allowlist_snapshot_hash != _snapshot_hash(snapshot.model_dump(mode="json")):
        _fail("PLADREA_SNAPSHOT_HASH_INVALID")
    return snapshot

def _bind_candidate(candidate: EndpointCandidate, source: CanonicalPromotionLiveAdapterDryRunDispatchReadinessPacket, intent: ExecutionIntent) -> None:
    descriptor_scope = source.request_descriptor.get("target_resource_scope")
    if candidate.adapter_contract_id != source.adapter_contract_id:
        _fail("PLADREA_CANDIDATE_ADAPTER_MISMATCH")
    if candidate.target_system != intent.target_system:
        _fail("PLADREA_CANDIDATE_TARGET_SYSTEM_MISMATCH")
    if candidate.target_resource_scope != intent.target_resource or descriptor_scope != intent.target_resource:
        _fail("PLADREA_CANDIDATE_TARGET_RESOURCE_MISMATCH")

def _evaluation(candidate: EndpointCandidate, snapshot: EndpointAllowlistSnapshot) -> dict[str, Any]:
    failures: set[str] = set()
    active = False
    for entry in snapshot.allowlist_entries:
        if entry.entry_status != "ACTIVE":
            continue
        active = True
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
            return {"matched": True, "matched_entry_id": entry.entry_id, "match_reason": "active_entry_exact_match", "mismatch_reasons": [], "comparison_mode": "exact_local_allowlist_comparison_only", "exact_fields_compared": list(EXACT_FIELDS), "semantic_match_used": False}
        failures.update(name for name, passed in comparisons.items() if not passed)
    reasons = ["no_active_allowlist_entry"] if not active else [f"{name}_mismatch" for name in EXACT_FIELDS if name in failures]
    return {"matched": False, "matched_entry_id": None, "match_reason": "no_active_exact_match", "mismatch_reasons": reasons, "comparison_mode": "exact_local_allowlist_comparison_only", "exact_fields_compared": list(EXACT_FIELDS), "semantic_match_used": False}

def _identity(source: CanonicalPromotionLiveAdapterDryRunDispatchReadinessPacket, candidate: EndpointCandidate, candidate_digest: str, snapshot: EndpointAllowlistSnapshot, result: dict[str, Any], evaluation_digest: str) -> dict[str, Any]:
    return {
        "source_dispatch_readiness_id": source.promotion_live_adapter_dry_run_dispatch_readiness_id,
        "source_dispatch_readiness_hash": source.promotion_live_adapter_dry_run_dispatch_readiness_hash,
        "source_live_adapter_request_id": source.source_live_adapter_dry_run_request_id,
        "source_live_adapter_request_hash": source.source_live_adapter_dry_run_request_hash,
        "execution_intent_id": source.execution_intent_id, "execution_intent_hash": source.execution_intent_hash,
        "adapter_contract_id": source.adapter_contract_id, "adapter_contract_hash": source.adapter_contract_hash,
        "endpoint_candidate_id": candidate.endpoint_candidate_id, "endpoint_candidate_digest": candidate_digest,
        "exact_endpoint_metadata": {field: getattr(candidate, field) for field in EXACT_FIELDS},
        "allowlist_snapshot_id": snapshot.allowlist_snapshot_id, "allowlist_snapshot_hash": snapshot.allowlist_snapshot_hash,
        "matched_allowlist_entry_id": result["matched_entry_id"], "allowlist_evaluation_digest": evaluation_digest,
    }

def _checks(source_hash: str, matched: bool) -> list[dict[str, Any]]:
    conditional = {"active_entry_required", "all_exact_endpoint_dimensions_compared"}
    return [{"check_id": f"pladrea-check:v1:{ordinal}:{name.replace('_', '-')}", "ordinal": ordinal, "name": name, "mode": CHECK_MODE, "passed": matched if name in conditional else True, "evidence_ref": f"source_dispatch_readiness_hash:{source_hash}:{name}", **{field: False for field in EFFECT_FIELDS}} for ordinal, name in enumerate(CHECK_NAMES, 1)]

def _requirements() -> list[dict[str, Any]]:
    return [{"ordinal": ordinal, "name": name, "separate_future_artifact_required": True, "satisfied_by_this_packet": False} for ordinal, name in enumerate(FUTURE_REQUIREMENT_NAMES, 1)]

def build_canonical_promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(source_dispatch_readiness_packet: Any, endpoint_candidate: Any, allowlist_snapshot: Any, endpoint_allowlist_evaluated_at: datetime) -> CanonicalPromotionLiveAdapterDryRunEndpointAllowlistEvaluationPacket:
    """Build self-verifying exact local endpoint evidence from authoritative readiness."""
    evaluated = _aware(endpoint_allowlist_evaluated_at, "PLADREA_EVALUATED_AT_INVALID")
    source = _source(_json_value(source_dispatch_readiness_packet))
    intent = _validate_intent_adapter(source)
    candidate = _candidate(endpoint_candidate)
    snapshot = _snapshot(allowlist_snapshot)
    _bind_candidate(candidate, source, intent)
    declared = _aware(candidate.declared_at, "PLADREA_DECLARED_AT_INVALID")
    generated = _aware(snapshot.allowlist_generated_at, "PLADREA_GENERATED_AT_INVALID")
    source_time = _aware(source.dispatch_readiness_evaluated_at, "PLADREA_SOURCE_TIME_INVALID")
    if declared > evaluated or generated > evaluated or evaluated < source_time:
        _fail("PLADREA_TIMESTAMP_ORDER_INVALID")
    source_raw = source.model_dump(mode="json")
    candidate_raw = candidate.model_dump(mode="json")
    candidate_digest = _digest(CANDIDATE_DOMAIN, candidate_raw)
    result = _evaluation(candidate, snapshot)
    evaluation_digest = _digest(EVALUATION_DOMAIN, result)
    identity = _identity(source, candidate, candidate_digest, snapshot, result, evaluation_digest)
    checks = _checks(source.promotion_live_adapter_dry_run_dispatch_readiness_hash, result["matched"])
    requirements = _requirements()
    raw = {
        "format_version": FORMAT_VERSION, "endpoint_allowlist_evaluation_mechanism": EVALUATION_MECHANISM,
        "endpoint_allowlist_evaluated_at": evaluated.isoformat(),
        "source_dispatch_readiness_id": source.promotion_live_adapter_dry_run_dispatch_readiness_id,
        "source_dispatch_readiness_hash": source.promotion_live_adapter_dry_run_dispatch_readiness_hash,
        "source_dispatch_readiness_packet": source_raw,
        "source_live_adapter_dry_run_request_id": source.source_live_adapter_dry_run_request_id,
        "source_live_adapter_dry_run_request_hash": source.source_live_adapter_dry_run_request_hash,
        "request_descriptor": source_raw["request_descriptor"], "execution_intent": source_raw["execution_intent"],
        "execution_intent_id": source.execution_intent_id, "execution_intent_hash": source.execution_intent_hash,
        "adapter_contract_descriptor": source_raw["adapter_contract_descriptor"], "adapter_contract_id": source.adapter_contract_id,
        "adapter_contract_hash": source.adapter_contract_hash, "adapter_contract_version": source.adapter_contract_version,
        **{field: source_raw[field] for field in LINEAGE_FIELDS},
        "endpoint_candidate": candidate_raw, "endpoint_candidate_digest": candidate_digest,
        "allowlist_snapshot": snapshot.model_dump(mode="json"), "allowlist_snapshot_hash": snapshot.allowlist_snapshot_hash,
        "allowlist_evaluation_result": result, "allowlist_evaluation_digest": evaluation_digest,
        "endpoint_identity_binding": identity, "endpoint_identity_binding_digest": _digest(IDENTITY_DOMAIN, identity),
        "endpoint_allowlist_checks": checks, "endpoint_allowlist_check_digest": _digest(CHECKS_DOMAIN, checks),
        "future_requirements": requirements, "future_requirement_digest": _digest(FUTURE_REQUIREMENTS_DOMAIN, requirements),
        "endpoint_allowlist_status": STATUS, "request_dispatch_state": "NOT_DISPATCHED",
        "ready_for_promotion_native_credential_authorization_evaluation": result["matched"],
        "fail_closed": not result["matched"], "human_approval_proven": False, "authority_evidence_proven": False,
        **{field: False for field in EFFECT_FIELDS},
    }
    digest = _packet_hash(raw)
    raw["promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_hash"] = digest
    raw["promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_id"] = f"pladrea:v1:sha256:{digest}"
    return verify_canonical_promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(raw)

def verify_canonical_promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(packet: Any) -> CanonicalPromotionLiveAdapterDryRunEndpointAllowlistEvaluationPacket:
    """Independently reconstruct every identity, comparison, proof, hash, and claim."""
    try:
        value = packet.model_dump(mode="json") if isinstance(packet, BaseModel) else _json_value(packet)
        candidate_packet = CanonicalPromotionLiveAdapterDryRunEndpointAllowlistEvaluationPacket.model_validate(value)
    except (ValidationError, TypeError, CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError("PLADREA_PACKET_INVALID") from exc
    raw = candidate_packet.model_dump(mode="json")
    source = _source(candidate_packet.source_dispatch_readiness_packet)
    intent = _validate_intent_adapter(source)
    source_raw = source.model_dump(mode="json")
    if candidate_packet.source_dispatch_readiness_id != source.promotion_live_adapter_dry_run_dispatch_readiness_id or candidate_packet.source_dispatch_readiness_hash != source.promotion_live_adapter_dry_run_dispatch_readiness_hash:
        _fail("PLADREA_SOURCE_SUMMARY_MISMATCH")
    copied = ("source_live_adapter_dry_run_request_id", "source_live_adapter_dry_run_request_hash", "request_descriptor", "execution_intent", "execution_intent_id", "execution_intent_hash", "adapter_contract_descriptor", "adapter_contract_id", "adapter_contract_hash", "adapter_contract_version", *LINEAGE_FIELDS)
    for field in copied:
        if _json_value(getattr(candidate_packet, field)) != _json_value(source_raw[field]):
            _fail("PLADREA_SOURCE_FIELD_MISMATCH")
    _bind_candidate(candidate_packet.endpoint_candidate, source, intent)
    candidate_raw = candidate_packet.endpoint_candidate.model_dump(mode="json")
    candidate_digest = _digest(CANDIDATE_DOMAIN, candidate_raw)
    if candidate_packet.endpoint_candidate_digest != candidate_digest:
        _fail("PLADREA_CANDIDATE_DIGEST_MISMATCH")
    snapshot_raw = candidate_packet.allowlist_snapshot.model_dump(mode="json")
    snapshot_hash = _snapshot_hash(snapshot_raw)
    if candidate_packet.allowlist_snapshot_hash != snapshot_hash or candidate_packet.allowlist_snapshot.allowlist_snapshot_hash != snapshot_hash:
        _fail("PLADREA_SNAPSHOT_HASH_MISMATCH")
    evaluated = _aware(candidate_packet.endpoint_allowlist_evaluated_at, "PLADREA_EVALUATED_AT_INVALID")
    if (_aware(candidate_packet.endpoint_candidate.declared_at, "PLADREA_DECLARED_AT_INVALID") > evaluated or _aware(candidate_packet.allowlist_snapshot.allowlist_generated_at, "PLADREA_GENERATED_AT_INVALID") > evaluated or evaluated < _aware(source.dispatch_readiness_evaluated_at, "PLADREA_SOURCE_TIME_INVALID")):
        _fail("PLADREA_TIMESTAMP_ORDER_INVALID")
    result = _evaluation(candidate_packet.endpoint_candidate, candidate_packet.allowlist_snapshot)
    evaluation_digest = _digest(EVALUATION_DOMAIN, result)
    if _json_value(candidate_packet.allowlist_evaluation_result) != result or candidate_packet.allowlist_evaluation_digest != evaluation_digest:
        _fail("PLADREA_EVALUATION_MISMATCH")
    identity = _identity(source, candidate_packet.endpoint_candidate, candidate_digest, candidate_packet.allowlist_snapshot, result, evaluation_digest)
    if candidate_packet.endpoint_identity_binding != identity or candidate_packet.endpoint_identity_binding_digest != _digest(IDENTITY_DOMAIN, identity):
        _fail("PLADREA_IDENTITY_MISMATCH")
    checks = _checks(source.promotion_live_adapter_dry_run_dispatch_readiness_hash, result["matched"])
    if _json_value(candidate_packet.endpoint_allowlist_checks) != checks or candidate_packet.endpoint_allowlist_check_digest != _digest(CHECKS_DOMAIN, checks):
        _fail("PLADREA_CHECKS_MISMATCH")
    requirements = _requirements()
    if _json_value(candidate_packet.future_requirements) != requirements or candidate_packet.future_requirement_digest != _digest(FUTURE_REQUIREMENTS_DOMAIN, requirements):
        _fail("PLADREA_REQUIREMENTS_MISMATCH")
    if candidate_packet.fail_closed != (not result["matched"]) or candidate_packet.ready_for_promotion_native_credential_authorization_evaluation != result["matched"]:
        _fail("PLADREA_FAIL_CLOSED_MISMATCH")
    if candidate_packet.human_approval_proven or candidate_packet.authority_evidence_proven or any(getattr(candidate_packet, field) for field in EFFECT_FIELDS):
        _fail("PLADREA_EFFECT_CLAIM_INVALID")
    digest = _packet_hash(raw)
    if candidate_packet.promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_hash != digest:
        _fail("PLADREA_PACKET_HASH_MISMATCH")
    if candidate_packet.promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_id != f"pladrea:v1:sha256:{digest}":
        _fail("PLADREA_PACKET_ID_MISMATCH")
    return candidate_packet
