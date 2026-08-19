"""Create a real Bind authorization artifact without invoking Bind.

The artifact produced here is governance permission for one exact, future
attempt.  This module is intentionally limited to deterministic validation and
hashing: consumption, credential access, dispatch, Bind, receipts, and logging
remain separate boundaries.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.live_adapter_dry_run_bind_authorization_gate_review import (
    AUTHORIZATION_REQUIREMENTS,
    CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket,
    LiveAdapterDryRunBindAuthorizationGateReviewError,
    verify_live_adapter_dry_run_bind_authorization_gate_review_packet,
)

FORMAT_VERSION = "canonical-live-adapter-bind-authorization/v1"
STATUS = "LIVE_ADAPTER_BIND_AUTHORIZATION_GRANTED_NOT_INVOKED"
MECHANISM = "authorize_exact_future_live_adapter_bind_without_invocation/v1"
HASH_PATTERN = r"^[0-9a-f]{64}$"
ID_PATTERN = r"^laba:v1:sha256:[0-9a-f]{64}$"
ACKNOWLEDGEMENTS = (
    "acknowledged_exact_source_context_only",
    "acknowledged_authorization_does_not_invoke_bind",
    "acknowledged_authorization_does_not_dispatch_request",
    "acknowledged_authorization_does_not_access_credentials",
    "acknowledged_authorization_does_not_construct_authorization_header",
    "acknowledged_authorization_does_not_create_bind_receipt",
    "acknowledged_authorization_does_not_write_trustlog",
    "acknowledged_semantic_match_is_not_authority",
)
COPIED_FIELDS = (
    "request_descriptor", "execution_intent", "execution_intent_id",
    "execution_intent_hash", "adapter_contract_descriptor",
    "adapter_contract_id", "adapter_contract_hash", "adapter_contract_version",
    "endpoint_candidate", "endpoint_candidate_digest",
    "endpoint_identity_binding", "endpoint_identity_binding_digest",
    "credential_reference", "credential_reference_digest",
    "credential_scope_binding", "credential_scope_binding_digest",
    "authority_evidence_reference_bundle",
    "authority_evidence_reference_bundle_digest",
    "authority_evidence_linkage_result",
    "authority_evidence_linkage_result_digest",
    "human_approval_reference_bundle", "human_approval_reference_bundle_digest",
    "human_approval_linkage_result", "human_approval_linkage_result_digest",
    "final_bind_authorization_readiness_result",
    "final_bind_authorization_readiness_result_digest",
    "source_to_execution_intent_mapping", "field_mapping_proof",
    "required_field_presence", "source_decision_identity", "candidate_identity",
    "evidence_lineage", "replay_summary",
)
UPSTREAM_HASH_FIELDS = (
    "source_live_adapter_dry_run_request_hash", "source_dispatch_readiness_hash",
    "source_endpoint_allowlist_evaluation_hash",
    "source_credential_authorization_hash",
    "source_operator_dispatch_review_hash", "source_bind_pre_dispatch_review_hash",
    "source_authority_evidence_linkage_review_hash",
    "source_human_approval_linkage_review_hash",
    "source_final_bind_authorization_readiness_hash",
)
EFFECT_FIELDS = (
    "bind_invoked", "bind_receipt_created", "trustlog_written",
    "request_dispatched", "endpoint_resolved", "credential_material_accessed",
    "credential_material_embedded", "authorization_header_constructed",
    "token_embedded", "secret_embedded", "network_used", "dns_used",
    "webhook_called", "live_adapter_instantiated", "live_adapter_method_called",
    "external_effect_used", "filesystem_used", "database_used", "provider_used",
    "subprocess_used", "operation_committed",
)
DOMAINS = {
    "decision": "veritas.live-adapter-bind-authorization.decision/v1",
    "requirements": "veritas.live-adapter-bind-authorization.requirements/v1",
    "idempotency": "veritas.live-adapter-bind-authorization.idempotency/v1",
    "artifact": "veritas.live-adapter-bind-authorization.artifact/v1",
}
ARCHITECTURE_GAPS = (
    "real_authority_evidence_is_only_a_declared_reference_bundle",
    "real_human_approval_is_only_a_declared_reference_bundle",
    "runtime_authority_validator_inputs_are_not_embedded_in_the_source_chain",
)


class LiveAdapterBindAuthorizationError(ValueError):
    """Stable fail-closed error raised for invalid authorization evidence."""


class BindAuthorizationDecision(BaseModel):
    """Explicit human decision distinct from the source gate reviewer."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    authorizer_id: str = Field(min_length=1)
    authorizer_role: str = Field(min_length=1)
    authorizer_attestation: str = Field(min_length=1)
    authorized_at: str
    authorization_reason: str = Field(min_length=1)
    explicit_go_no_go_confirmation: Literal["GO_AUTHORIZED"]
    acknowledged_exact_source_context_only: Literal[True]
    acknowledged_authorization_does_not_invoke_bind: Literal[True]
    acknowledged_authorization_does_not_dispatch_request: Literal[True]
    acknowledged_authorization_does_not_access_credentials: Literal[True]
    acknowledged_authorization_does_not_construct_authorization_header: Literal[True]
    acknowledged_authorization_does_not_create_bind_receipt: Literal[True]
    acknowledged_authorization_does_not_write_trustlog: Literal[True]
    acknowledged_semantic_match_is_not_authority: Literal[True]


class AuthorizationRequirementProof(BaseModel):
    """A deterministic proof reference derived from the verified source chain."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1)
    requirement: str = Field(min_length=1)
    verified: Literal[True]
    evidence_source: str = Field(min_length=1)


class CanonicalLiveAdapterBindAuthorizationArtifact(BaseModel):
    """Closed content-addressed permission for one future Bind attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    live_adapter_bind_authorization_id: str = Field(pattern=ID_PATTERN)
    live_adapter_bind_authorization_hash: str = Field(pattern=HASH_PATTERN)
    authorization_mechanism: Literal[MECHANISM]
    source_gate_review_id: str
    source_gate_review_hash: str = Field(pattern=HASH_PATTERN)
    source_gate_review_packet: dict[str, Any]
    source_final_bind_authorization_readiness_hash: str
    source_human_approval_linkage_review_hash: str
    source_authority_evidence_linkage_review_hash: str
    source_bind_pre_dispatch_review_hash: str
    source_operator_dispatch_review_hash: str
    source_credential_authorization_hash: str
    source_endpoint_allowlist_evaluation_hash: str
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
    credential_reference: dict[str, Any]
    credential_reference_digest: str
    credential_scope_binding: dict[str, Any]
    credential_scope_binding_digest: str
    authority_evidence_reference_bundle: dict[str, Any]
    authority_evidence_reference_bundle_digest: str
    authority_evidence_linkage_result: dict[str, Any]
    authority_evidence_linkage_result_digest: str
    human_approval_reference_bundle: dict[str, Any]
    human_approval_reference_bundle_digest: str
    human_approval_linkage_result: dict[str, Any]
    human_approval_linkage_result_digest: str
    final_bind_authorization_readiness_result: dict[str, Any]
    final_bind_authorization_readiness_result_digest: str
    source_to_execution_intent_mapping: dict[str, Any]
    field_mapping_proof: dict[str, Any]
    required_field_presence: dict[str, str]
    source_decision_identity: dict[str, Any]
    candidate_identity: dict[str, Any]
    evidence_lineage: dict[str, Any]
    replay_summary: dict[str, Any]
    authorization_decision: BindAuthorizationDecision
    authorization_decision_digest: str = Field(pattern=HASH_PATTERN)
    authorization_requirement_proofs: tuple[AuthorizationRequirementProof, ...]
    authorization_requirement_proofs_digest: str = Field(pattern=HASH_PATTERN)
    authorized_at: str
    valid_from: str
    valid_until: str
    idempotency_key: str = Field(pattern=r"^laba-idem:v1:sha256:[0-9a-f]{64}$")
    single_use: Literal[True]
    authorization_consumption_required: Literal[True]
    replay_protection_required: Literal[True]
    duplicate_dispatch_prohibited: Literal[True]
    bind_authorization_status: Literal[STATUS]
    bind_authorization_state: Literal["AUTHORIZED"]
    bind_authorization_created: Literal[True]
    execution_authority_created: Literal[False]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    bind_state: Literal["NOT_BOUND"]
    bind_invocation_state: Literal["NOT_INVOKED"]
    authorization_consumption_state: Literal["NOT_CONSUMED"]
    execution_state: Literal["NOT_EXECUTED"]
    bind_invoked: Literal[False]
    bind_receipt_created: Literal[False]
    trustlog_written: Literal[False]
    request_dispatched: Literal[False]
    endpoint_resolved: Literal[False]
    credential_material_accessed: Literal[False]
    credential_material_embedded: Literal[False]
    authorization_header_constructed: Literal[False]
    token_embedded: Literal[False]
    secret_embedded: Literal[False]
    network_used: Literal[False]
    dns_used: Literal[False]
    webhook_called: Literal[False]
    live_adapter_instantiated: Literal[False]
    live_adapter_method_called: Literal[False]
    external_effect_used: Literal[False]
    filesystem_used: Literal[False]
    database_used: Literal[False]
    provider_used: Literal[False]
    subprocess_used: Literal[False]
    operation_committed: Literal[False]


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, datetime):
        return _timestamp(value)
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json(item) for key, item in value.items()}
    raise LiveAdapterBindAuthorizationError("LABA_INVALID_VALUE")


def _timestamp(value: Any) -> str:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise LiveAdapterBindAuthorizationError("LABA_TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiveAdapterBindAuthorizationError("LABA_TIMESTAMP_NAIVE")
    return parsed.astimezone(timezone.utc).isoformat()


def _digest(domain: str, value: Any) -> str:
    payload = json.dumps(
        {"domain": domain, "value": _json(value)}, ensure_ascii=False,
        allow_nan=False, separators=(",", ":"), sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _artifact_hash(raw: dict[str, Any]) -> str:
    omitted = {
        "live_adapter_bind_authorization_id",
        "live_adapter_bind_authorization_hash",
    }
    return _digest(
        DOMAINS["artifact"],
        {key: value for key, value in raw.items() if key not in omitted},
    )


def _source(value: Any) -> CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket:
    try:
        return verify_live_adapter_dry_run_bind_authorization_gate_review_packet(value)
    except (LiveAdapterDryRunBindAuthorizationGateReviewError, TypeError, ValueError) as exc:
        raise LiveAdapterBindAuthorizationError("LABA_SOURCE_INVALID") from exc


def _validate_source(
    source: CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket,
) -> None:
    accepted = (
        source.bind_authorization_gate_review_result
        .accepted_for_future_real_bind_authorization_artifact
    )
    invalid = (
        source.gate_review_state != "PASSED_FOR_FUTURE_BIND_AUTHORIZATION_ARTIFACT"
        or source.fail_closed or not accepted
        or source.request_dispatch_state != "NOT_DISPATCHED"
        or source.request_dispatched or source.bind_state != "NOT_BOUND"
        or source.bind_invoked or source.bind_authorization_state != "NOT_AUTHORIZED"
        or source.bind_authorization_created or source.execution_authority_created
        or source.bind_receipt_created or source.trustlog_written or source.network_used
        or source.webhook_called or source.live_adapter_instantiated
    )
    if invalid:
        raise LiveAdapterBindAuthorizationError("LABA_SOURCE_NOT_AUTHORIZABLE")
    requirements = source.future_real_bind_authorization_artifact_requirements
    if tuple(item.name for item in requirements) != AUTHORIZATION_REQUIREMENTS:
        raise LiveAdapterBindAuthorizationError("LABA_REQUIREMENTS_MISMATCH")
    # The verified #2130 packet proves exact linkage of caller-declared metadata,
    # not the referenced AuthorityEvidence or HumanApprovalReceipt itself.  It
    # therefore cannot satisfy the first two real-authorization requirements,
    # nor can this verifier reconstruct RuntimeAuthorityValidator inputs.  Never
    # promote those declarations to authority merely because their hashes match.
    raise LiveAdapterBindAuthorizationError(
        "LABA_ARCHITECTURE_GAP_UNVERIFIED_REAL_GOVERNANCE_ARTIFACTS"
    )


def _decision(value: Any) -> BindAuthorizationDecision:
    try:
        decision = BindAuthorizationDecision.model_validate(_json(value))
        return decision.model_copy(
            update={"authorized_at": _timestamp(decision.authorized_at)}
        )
    except (ValidationError, TypeError, LiveAdapterBindAuthorizationError) as exc:
        raise LiveAdapterBindAuthorizationError("LABA_DECISION_INVALID") from exc


def _window(source: Any, decision: BindAuthorizationDecision,
            valid_from: Any, valid_until: Any) -> tuple[str, str, str]:
    authorized_at = _timestamp(decision.authorized_at)
    start = _timestamp(valid_from)
    end = _timestamp(valid_until)
    authorized_dt = datetime.fromisoformat(authorized_at)
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    if end_dt <= start_dt or not start_dt <= authorized_dt < end_dt:
        raise LiveAdapterBindAuthorizationError("LABA_VALIDITY_WINDOW_INVALID")
    intent = source.execution_intent
    ttl = intent.get("ttl_seconds")
    decision_ts = intent.get("decision_ts")
    if ttl is not None:
        if not isinstance(ttl, int) or ttl <= 0 or not decision_ts:
            raise LiveAdapterBindAuthorizationError("LABA_INTENT_TTL_INVALID")
        intent_start = datetime.fromisoformat(_timestamp(decision_ts))
        intent_end = intent_start + timedelta(seconds=ttl)
        if start_dt < intent_start or end_dt > intent_end:
            raise LiveAdapterBindAuthorizationError("LABA_VALIDITY_EXCEEDS_INTENT")
    return authorized_at, start, end


def _proofs(source: Any, decision: BindAuthorizationDecision) -> list[dict[str, Any]]:
    evidence = {
        "real_authority_evidence_verification": source.source_authority_evidence_linkage_review_hash,
        "real_human_approval_verification_where_required": source.source_human_approval_linkage_review_hash,
        "final_policy_admissibility": source.source_bind_pre_dispatch_review_hash,
        "final_runtime_risk_review": source.source_final_bind_authorization_readiness_hash,
        "final_endpoint_identity_binding": source.endpoint_identity_binding_digest,
        "final_credential_resolution_authorization": source.source_credential_authorization_hash,
        "final_authorization_header_construction_boundary": source.source_credential_authorization_hash,
        "idempotency_key_binding": source.execution_intent_hash,
        "final_no_replay_no_duplicate_dispatch_review": _digest(DOMAINS["idempotency"], source.replay_summary),
        "final_operator_human_go_no_go_confirmation": _digest(DOMAINS["decision"], decision),
        "explicit_real_bind_authorization_decision_boundary": _digest(DOMAINS["decision"], decision),
    }
    return [
        {"ordinal": ordinal, "requirement": name, "verified": True,
         "evidence_source": evidence[name]}
        for ordinal, name in enumerate(AUTHORIZATION_REQUIREMENTS, 1)
    ]


def build_live_adapter_bind_authorization_artifact(
    source_gate_review_packet: Any,
    authorization_decision: Any,
    valid_from: datetime | str,
    valid_until: datetime | str,
) -> CanonicalLiveAdapterBindAuthorizationArtifact:
    """Build and self-verify an authorization with no runtime effects."""
    source = _source(_json(source_gate_review_packet))
    _validate_source(source)
    decision = _decision(authorization_decision)
    authorized_at, start, end = _window(source, decision, valid_from, valid_until)
    source_raw = source.model_dump(mode="json")
    proofs = _proofs(source, decision)
    raw = {
        "format_version": FORMAT_VERSION,
        "authorization_mechanism": MECHANISM,
        "source_gate_review_id": source.live_adapter_dry_run_bind_authorization_gate_review_id,
        "source_gate_review_hash": source.live_adapter_dry_run_bind_authorization_gate_review_hash,
        "source_gate_review_packet": source_raw,
        **{field: source_raw[field] for field in COPIED_FIELDS},
        **{field: source_raw[field] for field in UPSTREAM_HASH_FIELDS},
        "authorization_decision": decision.model_dump(mode="json"),
        "authorization_decision_digest": _digest(DOMAINS["decision"], decision),
        "authorization_requirement_proofs": proofs,
        "authorization_requirement_proofs_digest": _digest(DOMAINS["requirements"], proofs),
        "authorized_at": authorized_at, "valid_from": start, "valid_until": end,
        "idempotency_key": "laba-idem:v1:sha256:" + _digest(
            DOMAINS["idempotency"], {
                "execution_intent_hash": source.execution_intent_hash,
                "request_descriptor": source.request_descriptor,
            },
        ),
        "single_use": True, "authorization_consumption_required": True,
        "replay_protection_required": True, "duplicate_dispatch_prohibited": True,
        "bind_authorization_status": STATUS,
        "bind_authorization_state": "AUTHORIZED", "bind_authorization_created": True,
        "execution_authority_created": False,
        "request_dispatch_state": "NOT_DISPATCHED", "bind_state": "NOT_BOUND",
        "bind_invocation_state": "NOT_INVOKED",
        "authorization_consumption_state": "NOT_CONSUMED",
        "execution_state": "NOT_EXECUTED",
        **{field: False for field in EFFECT_FIELDS},
    }
    digest = _artifact_hash(raw)
    raw["live_adapter_bind_authorization_hash"] = digest
    raw["live_adapter_bind_authorization_id"] = f"laba:v1:sha256:{digest}"
    return verify_live_adapter_bind_authorization_artifact(raw)


def verify_live_adapter_bind_authorization_artifact(
    raw: Any,
) -> CanonicalLiveAdapterBindAuthorizationArtifact:
    """Deterministically verify structure, source lineage, and non-effects.

    This verification deliberately does not compare the window to wall-clock
    time.  Invocation-time expiry belongs to the future consumption gate.
    """
    try:
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw
        artifact = CanonicalLiveAdapterBindAuthorizationArtifact.model_validate(
            _json(value)
        )
    except (ValidationError, TypeError, LiveAdapterBindAuthorizationError) as exc:
        raise LiveAdapterBindAuthorizationError("LABA_ARTIFACT_INVALID") from exc
    actual = artifact.model_dump(mode="json")
    source = _source(artifact.source_gate_review_packet)
    _validate_source(source)
    source_raw = source.model_dump(mode="json")
    if (
        artifact.source_gate_review_id != source.live_adapter_dry_run_bind_authorization_gate_review_id
        or artifact.source_gate_review_hash != source.live_adapter_dry_run_bind_authorization_gate_review_hash
        or any(_json(getattr(artifact, field)) != _json(source_raw[field]) for field in COPIED_FIELDS)
        or any(getattr(artifact, field) != source_raw[field] for field in UPSTREAM_HASH_FIELDS)
    ):
        raise LiveAdapterBindAuthorizationError("LABA_SOURCE_LINEAGE_MISMATCH")
    decision = _decision(artifact.authorization_decision)
    authorized_at, start, end = _window(
        source, decision, artifact.valid_from, artifact.valid_until
    )
    proofs = _proofs(source, decision)
    expected_idempotency = "laba-idem:v1:sha256:" + _digest(
        DOMAINS["idempotency"], {
            "execution_intent_hash": source.execution_intent_hash,
            "request_descriptor": source.request_descriptor,
        },
    )
    expected = (
        artifact.authorized_at == authorized_at,
        artifact.valid_from == start, artifact.valid_until == end,
        artifact.authorization_decision_digest == _digest(DOMAINS["decision"], decision),
        _json(artifact.authorization_requirement_proofs) == proofs,
        artifact.authorization_requirement_proofs_digest == _digest(DOMAINS["requirements"], proofs),
        artifact.idempotency_key == expected_idempotency,
        not any(getattr(artifact, field) for field in EFFECT_FIELDS),
    )
    if not all(expected):
        raise LiveAdapterBindAuthorizationError("LABA_DERIVED_MISMATCH")
    digest = _artifact_hash(actual)
    if artifact.live_adapter_bind_authorization_hash != digest:
        raise LiveAdapterBindAuthorizationError("LABA_HASH_MISMATCH")
    if artifact.live_adapter_bind_authorization_id != f"laba:v1:sha256:{digest}":
        raise LiveAdapterBindAuthorizationError("LABA_ID_MISMATCH")
    return artifact


def validate_live_adapter_bind_authorization_temporal_validity(
    artifact: Any, *, now: datetime | str,
) -> CanonicalLiveAdapterBindAuthorizationArtifact:
    """Verify an artifact and enforce its window at a supplied invocation time."""
    verified = verify_live_adapter_bind_authorization_artifact(artifact)
    current = datetime.fromisoformat(_timestamp(now))
    if not datetime.fromisoformat(verified.valid_from) <= current < datetime.fromisoformat(verified.valid_until):
        raise LiveAdapterBindAuthorizationError("LABA_NOT_CURRENTLY_VALID")
    return verified
