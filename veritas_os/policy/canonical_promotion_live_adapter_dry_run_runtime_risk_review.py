"""Review short-lived promotion runtime-risk evidence without invoking Bind.

This boundary consumes the verified promotion authorization projection created
from the final credential-scope recheck.  It binds one caller-supplied runtime
risk signal and observed state fingerprint to the exact intent, adapter,
endpoint, credential scope, and Bind context.  Missing, stale, mismatched, or
negative evidence fails closed.

The module performs no adapter call or I/O and grants no authority.  A passing
packet may proceed only to the remaining Real Bind Authorization requirements;
``execute_bind_adjudication`` must still obtain a fresh snapshot and call
``adapter.assess_runtime_risk`` immediately before any apply attempt.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from veritas_os.policy.canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck import (
    AUTHORIZATION_REQUIREMENTS,
    EFFECT_FIELDS,
    INVOCATION_REQUIREMENTS,
    CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError,
    verify_canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck_packet,
)
from veritas_os.policy.canonical_promotion_real_bind_authorization_contract import (
    BIND_TIME_RISK_OWNER,
    CONTRACT_VERSION as SOURCE_CONTRACT_VERSION,
    NEXT_AUTHORIZATION_REQUIREMENT,
    CanonicalPromotionRealBindAuthorizationContractError,
    RequirementRoute,
    VerifiedPromotionAuthorizationSource,
    project_verified_promotion_authorization_source,
)

FORMAT_VERSION = "canonical-promotion-live-adapter-dry-run-runtime-risk-review/v1"
REVIEW_MECHANISM = "review_context_bound_pre_authorization_runtime_risk_without_bind/v1"
MAX_REVIEW_VALIDITY_SECONDS = 300
HASH_PATTERN = r"^[0-9a-f]{64}$"
ID_PATTERN = r"^pladrrr:v1:sha256:[0-9a-f]{64}$"
PREFIX = "veritas.promotion-live-adapter-dry-run-runtime-risk-review"
DOMAINS = {
    name: f"{PREFIX}.{name}/v1"
    for name in (
        "source-projection",
        "decision",
        "result",
        "requirement-proof",
        "checks",
        "packet",
    )
}

PASS_OUTCOME = "PASS_FOR_REMAINING_AUTHORIZATION"
BLOCK_OUTCOME = "BLOCKED_BY_RUNTIME_RISK"
INDETERMINATE_OUTCOME = "INDETERMINATE_FAIL_CLOSED"
OUTCOMES = (PASS_OUTCOME, BLOCK_OUTCOME, INDETERMINATE_OUTCOME)
PASS_STATUS = "PROMOTION_NATIVE_RUNTIME_RISK_REVIEW_PASSED_NOT_AUTHORIZED"
BLOCK_STATUS = "PROMOTION_NATIVE_RUNTIME_RISK_REVIEW_BLOCKED_NOT_AUTHORIZED"
STATUSES = (PASS_STATUS, BLOCK_STATUS)
PASS_STATE = "REVIEWED_FOR_REMAINING_REAL_BIND_AUTHORIZATION_REQUIREMENTS"
BLOCK_STATE = "RUNTIME_RISK_REVIEW_FAILED_CLOSED"
STATES = (PASS_STATE, BLOCK_STATE)

CHECK_NAMES = (
    "verified_authorization_projection_reconstructed",
    "exact_source_identity_bound",
    "exact_execution_intent_bound",
    "exact_adapter_contract_bound",
    "exact_bind_context_bound",
    "exact_endpoint_identity_bound",
    "exact_credential_scope_bound",
    "runtime_risk_decision_closed_schema_valid",
    "runtime_risk_evidence_refs_present",
    "review_window_short_lived_and_ordered",
    "runtime_risk_outcome_derived_fail_closed",
    "remaining_requirements_preserved",
    "bind_time_runtime_risk_recheck_preserved",
    "no_bind_authorization_created",
    "no_execution_authority_created",
    "no_bind_or_dispatch_invocation",
    "no_credential_material_access",
    "no_external_effect",
)

ADDITIONAL_NO_EFFECT_FIELDS = (
    "human_approval_created",
    "human_approval_externally_verified",
    "human_approval_proven",
    "authority_evidence_created",
    "authority_evidence_externally_verified",
    "authority_evidence_proven",
    "execution_authority_created",
    "execution_authorized",
    "bind_authorization_created",
    "credential_material_accessed",
    "credential_store_accessed",
    "cookie_embedded",
    "password_embedded",
    "private_key_embedded",
)
NO_EFFECT_FIELDS = tuple(dict.fromkeys((*EFFECT_FIELDS, *ADDITIONAL_NO_EFFECT_FIELDS)))


class CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewError(ValueError):
    """Stable fail-closed error for invalid runtime-risk review evidence."""


class RuntimeRiskReviewDecision(BaseModel):
    """Closed, short-lived risk decision bound to one exact future Bind."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    runtime_risk_review_decision_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    reviewer_role: str = Field(min_length=1)
    reviewer_attestation: str = Field(min_length=1)
    reviewed_at: str
    valid_until: str
    source_final_credential_scope_recheck_id: str = Field(min_length=1)
    source_final_credential_scope_recheck_hash: str = Field(pattern=HASH_PATTERN)
    execution_intent_id: str = Field(min_length=1)
    execution_intent_hash: str = Field(pattern=HASH_PATTERN)
    adapter_contract_id: str = Field(min_length=1)
    adapter_contract_hash: str = Field(pattern=HASH_PATTERN)
    bind_context_hash: str = Field(pattern=HASH_PATTERN)
    final_endpoint_identity_binding_digest: str = Field(pattern=HASH_PATTERN)
    final_credential_scope_binding_digest: str = Field(pattern=HASH_PATTERN)
    expected_state_fingerprint: str | None
    observed_state_fingerprint: str | None
    runtime_risk_signal: bool | None
    runtime_risk_evidence_refs: tuple[str, ...] = Field(min_length=1)
    risk_reason: str = Field(min_length=1)
    assessment_input_mode: Literal[
        "caller_supplied_pre_authorization_runtime_risk_evidence"
    ]
    acknowledged_exact_bind_context_only: Literal[True]
    acknowledged_runtime_risk_review_is_not_authority: Literal[True]
    acknowledged_no_bind_authorization: Literal[True]
    acknowledged_no_bind_invocation: Literal[True]
    acknowledged_no_request_dispatch: Literal[True]
    acknowledged_no_credential_material_access: Literal[True]
    acknowledged_missing_stale_or_mismatched_evidence_blocks: Literal[True]
    acknowledged_bind_time_runtime_risk_recheck_still_required: Literal[True]


class RuntimeRiskReviewResult(BaseModel):
    """Deterministic, fail-closed interpretation of supplied risk evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    outcome: Literal[*OUTCOMES]
    runtime_risk_acceptable: bool
    reason_codes: tuple[str, ...] = Field(min_length=1)
    runtime_risk_signal_present: bool
    runtime_risk_signal_passed: bool
    expected_state_fingerprint_present: bool
    observed_state_fingerprint_present: bool
    state_fingerprint_matches: bool
    intent_ttl_present: bool
    intent_fresh_for_review_window: bool
    intent_expires_at: str | None
    source_projection_verified: Literal[True]
    exact_context_binding_verified: Literal[True]
    review_window_verified: Literal[True]
    evidence_refs_present: Literal[True]
    caller_supplied_evidence_only: Literal[True]
    external_evidence_authenticity_claimed: Literal[False]
    creates_execution_authority: Literal[False]
    creates_bind_authorization: Literal[False]
    invokes_bind: Literal[False]
    dispatches_request: Literal[False]
    bind_time_runtime_risk_recheck_required: Literal[True]


class RuntimeRiskRequirementProof(BaseModel):
    """Evidence that runtime-risk review passed or failed closed."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: Literal[1]
    requirement: Literal[NEXT_AUTHORIZATION_REQUIREMENT]
    source_route_owner: str = Field(min_length=1)
    review_decision_id: str = Field(min_length=1)
    review_decision_digest: str = Field(pattern=HASH_PATTERN)
    review_result_digest: str = Field(pattern=HASH_PATTERN)
    outcome: Literal[*OUTCOMES]
    satisfied_by_this_packet: bool
    bind_time_recheck_required: Literal[True]
    bind_time_recheck_owner: Literal[BIND_TIME_RISK_OWNER]


class RuntimeRiskReviewCheck(BaseModel):
    """One ordered deterministic invariant verified by the review boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1, le=len(CHECK_NAMES))
    name: Literal[*CHECK_NAMES]
    passed: Literal[True]
    evidence_ref: str = Field(min_length=1)


class _PacketBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    promotion_live_adapter_dry_run_runtime_risk_review_id: str = Field(
        pattern=ID_PATTERN
    )
    promotion_live_adapter_dry_run_runtime_risk_review_hash: str = Field(
        pattern=HASH_PATTERN
    )
    runtime_risk_review_mechanism: Literal[REVIEW_MECHANISM]
    runtime_risk_review_recorded_at: str
    source_contract_version: Literal[SOURCE_CONTRACT_VERSION]
    source_final_credential_scope_recheck_id: str = Field(min_length=1)
    source_final_credential_scope_recheck_hash: str = Field(pattern=HASH_PATTERN)
    source_credential_scope_rechecked_at: str
    source_authorization_projection: VerifiedPromotionAuthorizationSource
    source_authorization_projection_digest: str = Field(pattern=HASH_PATTERN)
    execution_intent_id: str = Field(min_length=1)
    execution_intent_hash: str = Field(pattern=HASH_PATTERN)
    adapter_contract_id: str = Field(min_length=1)
    adapter_contract_hash: str = Field(pattern=HASH_PATTERN)
    bind_context_hash: str = Field(pattern=HASH_PATTERN)
    final_endpoint_identity_binding_digest: str = Field(pattern=HASH_PATTERN)
    final_credential_scope_binding_digest: str = Field(pattern=HASH_PATTERN)
    runtime_risk_review_decision: RuntimeRiskReviewDecision
    runtime_risk_review_decision_digest: str = Field(pattern=HASH_PATTERN)
    runtime_risk_review_result: RuntimeRiskReviewResult
    runtime_risk_review_result_digest: str = Field(pattern=HASH_PATTERN)
    runtime_risk_requirement_proof: RuntimeRiskRequirementProof
    runtime_risk_requirement_proof_digest: str = Field(pattern=HASH_PATTERN)
    runtime_risk_review_checks: tuple[RuntimeRiskReviewCheck, ...]
    runtime_risk_review_check_digest: str = Field(pattern=HASH_PATTERN)
    remaining_authorization_routes: tuple[RequirementRoute, ...]
    remaining_invocation_routes: tuple[RequirementRoute, ...]
    next_authorization_requirement: Literal[*AUTHORIZATION_REQUIREMENTS]
    runtime_risk_review_status: Literal[*STATUSES]
    runtime_risk_review_state: Literal[*STATES]
    runtime_risk_review_completed: Literal[True]
    runtime_risk_requirement_satisfied: bool
    ready_for_remaining_real_bind_authorization_requirements: bool
    bind_time_runtime_risk_recheck_required: Literal[True]
    bind_time_runtime_risk_owner: Literal[BIND_TIME_RISK_OWNER]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    bind_state: Literal["NOT_BOUND"]
    authority_state: Literal["NOT_AUTHORIZED"]
    human_approval_state: Literal["NOT_APPROVED"]
    bind_authorization_state: Literal["NOT_AUTHORIZED"]
    ready_for_real_bind: Literal[False]
    ready_for_network_dispatch: Literal[False]
    fail_closed: bool


CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewPacket = create_model(
    "CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewPacket",
    __base__=_PacketBase,
    **{name: (Literal[False], ...) for name in NO_EFFECT_FIELDS},
)


def _fail(code: str) -> None:
    raise CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewError(code)


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if (
        isinstance(value, float)
        and value == value
        and value
        not in (
            float("inf"),
            float("-inf"),
        )
    ):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            _fail("CPLADRRR_TIMESTAMP_INVALID")
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json(item) for key, item in value.items()}
    _fail("CPLADRRR_VALUE_INVALID")


def _aware(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(code)
    return parsed.astimezone(timezone.utc)


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json(value)},
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _packet_hash(raw: dict[str, Any]) -> str:
    return _digest(
        DOMAINS["packet"],
        {
            key: value
            for key, value in raw.items()
            if key
            not in {
                "promotion_live_adapter_dry_run_runtime_risk_review_id",
                "promotion_live_adapter_dry_run_runtime_risk_review_hash",
            }
        },
    )


def _source(value: Any) -> tuple[Any, VerifiedPromotionAuthorizationSource]:
    try:
        source = verify_canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck_packet(
            _json(value)
        )
        projection = project_verified_promotion_authorization_source(source)
    except (
        CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError,
        CanonicalPromotionRealBindAuthorizationContractError,
        TypeError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewError(
            "CPLADRRR_SOURCE_INVALID"
        ) from exc
    return source, projection


def _decision(value: Any) -> RuntimeRiskReviewDecision:
    raw = _json(value)
    if not isinstance(raw, dict):
        _fail("CPLADRRR_DECISION_INVALID")
    signal = raw.get("runtime_risk_signal")
    if signal is not None and not isinstance(signal, bool):
        _fail("CPLADRRR_RUNTIME_RISK_SIGNAL_INVALID")
    refs = raw.get("runtime_risk_evidence_refs")
    if (
        not isinstance(refs, (list, tuple))
        or not refs
        or any(not isinstance(ref, str) or not ref.strip() for ref in refs)
        or len(set(refs)) != len(refs)
    ):
        _fail("CPLADRRR_EVIDENCE_REFS_INVALID")
    try:
        return RuntimeRiskReviewDecision.model_validate(raw)
    except ValidationError as exc:
        raise CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewError(
            "CPLADRRR_DECISION_INVALID"
        ) from exc


def _validate_decision_binding(
    projection: VerifiedPromotionAuthorizationSource,
    decision: RuntimeRiskReviewDecision,
) -> None:
    authorization_requirements = tuple(
        route.requirement for route in projection.authorization_routes
    )
    invocation_requirements = tuple(
        route.requirement for route in projection.invocation_routes
    )
    if (
        authorization_requirements != AUTHORIZATION_REQUIREMENTS
        or invocation_requirements != INVOCATION_REQUIREMENTS
        or authorization_requirements[0] != NEXT_AUTHORIZATION_REQUIREMENT
    ):
        _fail("CPLADRRR_SOURCE_ROUTE_MISMATCH")
    expected = {
        "source_final_credential_scope_recheck_id": (
            projection.source_final_credential_scope_recheck_id
        ),
        "source_final_credential_scope_recheck_hash": (
            projection.source_final_credential_scope_recheck_hash
        ),
        "execution_intent_id": projection.execution_intent_id,
        "execution_intent_hash": projection.execution_intent_hash,
        "adapter_contract_id": projection.adapter_contract_id,
        "adapter_contract_hash": projection.adapter_contract_hash,
        "bind_context_hash": projection.bind_context_hash,
        "final_endpoint_identity_binding_digest": (
            projection.final_endpoint_identity_binding_digest
        ),
        "final_credential_scope_binding_digest": (
            projection.final_credential_scope_binding_digest
        ),
        "expected_state_fingerprint": projection.execution_intent.get(
            "expected_state_fingerprint"
        ),
    }
    if any(getattr(decision, field) != value for field, value in expected.items()):
        _fail("CPLADRRR_DECISION_BINDING_MISMATCH")


def _validate_times(
    source_rechecked_at: Any,
    decision: RuntimeRiskReviewDecision,
    recorded_at: Any,
) -> tuple[datetime, datetime, datetime]:
    source_at = _aware(source_rechecked_at, "CPLADRRR_SOURCE_TIME_INVALID")
    reviewed_at = _aware(decision.reviewed_at, "CPLADRRR_REVIEWED_AT_INVALID")
    valid_until = _aware(decision.valid_until, "CPLADRRR_VALID_UNTIL_INVALID")
    recorded = _aware(recorded_at, "CPLADRRR_RECORDED_AT_INVALID")
    validity = (valid_until - reviewed_at).total_seconds()
    if (
        reviewed_at < source_at
        or recorded < reviewed_at
        or recorded >= valid_until
        or validity <= 0
        or validity > MAX_REVIEW_VALIDITY_SECONDS
    ):
        _fail("CPLADRRR_REVIEW_WINDOW_INVALID")
    return reviewed_at, valid_until, recorded


def _result(
    projection: VerifiedPromotionAuthorizationSource,
    decision: RuntimeRiskReviewDecision,
    reviewed_at: datetime,
    valid_until: datetime,
) -> dict[str, Any]:
    expected = decision.expected_state_fingerprint
    observed = decision.observed_state_fingerprint
    expected_present = isinstance(expected, str) and bool(expected.strip())
    observed_present = isinstance(observed, str) and bool(observed.strip())
    fingerprint_matches = expected_present and observed_present and expected == observed

    ttl = projection.execution_intent.get("ttl_seconds")
    ttl_present = isinstance(ttl, int) and not isinstance(ttl, bool) and ttl > 0
    intent_expires_at = None
    intent_fresh = False
    if ttl_present:
        decision_at = _aware(
            projection.execution_intent.get("decision_ts"),
            "CPLADRRR_INTENT_DECISION_TIME_INVALID",
        )
        expiry = decision_at + timedelta(seconds=ttl)
        intent_expires_at = expiry.isoformat()
        intent_fresh = reviewed_at <= expiry and valid_until <= expiry

    block_reasons = []
    missing_reasons = []
    if decision.runtime_risk_signal is False:
        block_reasons.append("CPLADRRR_RUNTIME_RISK_UNACCEPTABLE")
    elif decision.runtime_risk_signal is None:
        missing_reasons.append("CPLADRRR_RUNTIME_RISK_SIGNAL_MISSING")
    if not expected_present:
        missing_reasons.append("CPLADRRR_EXPECTED_STATE_FINGERPRINT_MISSING")
    if not observed_present:
        missing_reasons.append("CPLADRRR_OBSERVED_STATE_FINGERPRINT_MISSING")
    if expected_present and observed_present and not fingerprint_matches:
        block_reasons.append("CPLADRRR_STATE_DRIFT_DETECTED")
    if not ttl_present:
        missing_reasons.append("CPLADRRR_INTENT_TTL_MISSING")
    elif not intent_fresh:
        block_reasons.append("CPLADRRR_INTENT_NOT_FRESH_FOR_REVIEW_WINDOW")

    if block_reasons:
        outcome = BLOCK_OUTCOME
        reasons = block_reasons + missing_reasons
    elif missing_reasons:
        outcome = INDETERMINATE_OUTCOME
        reasons = missing_reasons
    else:
        outcome = PASS_OUTCOME
        reasons = ["CPLADRRR_RUNTIME_RISK_ACCEPTABLE"]

    return {
        "outcome": outcome,
        "runtime_risk_acceptable": outcome == PASS_OUTCOME,
        "reason_codes": reasons,
        "runtime_risk_signal_present": decision.runtime_risk_signal is not None,
        "runtime_risk_signal_passed": decision.runtime_risk_signal is True,
        "expected_state_fingerprint_present": expected_present,
        "observed_state_fingerprint_present": observed_present,
        "state_fingerprint_matches": fingerprint_matches,
        "intent_ttl_present": ttl_present,
        "intent_fresh_for_review_window": intent_fresh,
        "intent_expires_at": intent_expires_at,
        "source_projection_verified": True,
        "exact_context_binding_verified": True,
        "review_window_verified": True,
        "evidence_refs_present": True,
        "caller_supplied_evidence_only": True,
        "external_evidence_authenticity_claimed": False,
        "creates_execution_authority": False,
        "creates_bind_authorization": False,
        "invokes_bind": False,
        "dispatches_request": False,
        "bind_time_runtime_risk_recheck_required": True,
    }


def _derived(
    projection: VerifiedPromotionAuthorizationSource,
    decision: RuntimeRiskReviewDecision,
    reviewed_at: datetime,
    valid_until: datetime,
) -> tuple[Any, ...]:
    decision_raw = decision.model_dump(mode="json")
    decision_raw["reviewed_at"] = reviewed_at.isoformat()
    decision_raw["valid_until"] = valid_until.isoformat()
    decision_digest = _digest(DOMAINS["decision"], decision_raw)
    result = _result(projection, decision, reviewed_at, valid_until)
    result_digest = _digest(DOMAINS["result"], result)
    passed = result["outcome"] == PASS_OUTCOME
    source_runtime_route = projection.authorization_routes[0]
    proof = {
        "ordinal": 1,
        "requirement": NEXT_AUTHORIZATION_REQUIREMENT,
        "source_route_owner": source_runtime_route.implementation_owner,
        "review_decision_id": decision.runtime_risk_review_decision_id,
        "review_decision_digest": decision_digest,
        "review_result_digest": result_digest,
        "outcome": result["outcome"],
        "satisfied_by_this_packet": passed,
        "bind_time_recheck_required": True,
        "bind_time_recheck_owner": BIND_TIME_RISK_OWNER,
    }
    proof_digest = _digest(DOMAINS["requirement-proof"], proof)
    checks = [
        {
            "ordinal": ordinal,
            "name": name,
            "passed": True,
            "evidence_ref": (
                f"source:{projection.source_final_credential_scope_recheck_hash}:"
                f"decision:{decision_digest}:{name}"
            ),
        }
        for ordinal, name in enumerate(CHECK_NAMES, 1)
    ]
    authorization_routes = (
        projection.authorization_routes[1:]
        if passed
        else projection.authorization_routes
    )
    return (
        decision_raw,
        decision_digest,
        result,
        result_digest,
        proof,
        proof_digest,
        checks,
        authorization_routes,
        passed,
    )


def _assemble(
    source: Any,
    projection: VerifiedPromotionAuthorizationSource,
    decision: RuntimeRiskReviewDecision,
    recorded_at: str,
) -> dict[str, Any]:
    reviewed_at, valid_until, recorded = _validate_times(
        source.credential_scope_rechecked_at,
        decision,
        recorded_at,
    )
    _validate_decision_binding(projection, decision)
    (
        decision_raw,
        decision_digest,
        result,
        result_digest,
        proof,
        proof_digest,
        checks,
        authorization_routes,
        passed,
    ) = _derived(projection, decision, reviewed_at, valid_until)
    projection_raw = projection.model_dump(mode="json")
    raw = {
        "format_version": FORMAT_VERSION,
        "runtime_risk_review_mechanism": REVIEW_MECHANISM,
        "runtime_risk_review_recorded_at": recorded.isoformat(),
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "source_final_credential_scope_recheck_id": (
            projection.source_final_credential_scope_recheck_id
        ),
        "source_final_credential_scope_recheck_hash": (
            projection.source_final_credential_scope_recheck_hash
        ),
        "source_credential_scope_rechecked_at": source.credential_scope_rechecked_at,
        "source_authorization_projection": projection_raw,
        "source_authorization_projection_digest": _digest(
            DOMAINS["source-projection"], projection_raw
        ),
        "execution_intent_id": projection.execution_intent_id,
        "execution_intent_hash": projection.execution_intent_hash,
        "adapter_contract_id": projection.adapter_contract_id,
        "adapter_contract_hash": projection.adapter_contract_hash,
        "bind_context_hash": projection.bind_context_hash,
        "final_endpoint_identity_binding_digest": (
            projection.final_endpoint_identity_binding_digest
        ),
        "final_credential_scope_binding_digest": (
            projection.final_credential_scope_binding_digest
        ),
        "runtime_risk_review_decision": decision_raw,
        "runtime_risk_review_decision_digest": decision_digest,
        "runtime_risk_review_result": result,
        "runtime_risk_review_result_digest": result_digest,
        "runtime_risk_requirement_proof": proof,
        "runtime_risk_requirement_proof_digest": proof_digest,
        "runtime_risk_review_checks": checks,
        "runtime_risk_review_check_digest": _digest(DOMAINS["checks"], checks),
        "remaining_authorization_routes": [
            route.model_dump(mode="json") for route in authorization_routes
        ],
        "remaining_invocation_routes": [
            route.model_dump(mode="json") for route in projection.invocation_routes
        ],
        "next_authorization_requirement": authorization_routes[0].requirement,
        "runtime_risk_review_status": PASS_STATUS if passed else BLOCK_STATUS,
        "runtime_risk_review_state": PASS_STATE if passed else BLOCK_STATE,
        "runtime_risk_review_completed": True,
        "runtime_risk_requirement_satisfied": passed,
        "ready_for_remaining_real_bind_authorization_requirements": passed,
        "bind_time_runtime_risk_recheck_required": True,
        "bind_time_runtime_risk_owner": BIND_TIME_RISK_OWNER,
        "request_dispatch_state": "NOT_DISPATCHED",
        "bind_state": "NOT_BOUND",
        "authority_state": "NOT_AUTHORIZED",
        "human_approval_state": "NOT_APPROVED",
        "bind_authorization_state": "NOT_AUTHORIZED",
        "ready_for_real_bind": False,
        "ready_for_network_dispatch": False,
        "fail_closed": not passed,
        **{field: False for field in NO_EFFECT_FIELDS},
    }
    digest = _packet_hash(raw)
    raw["promotion_live_adapter_dry_run_runtime_risk_review_hash"] = digest
    raw["promotion_live_adapter_dry_run_runtime_risk_review_id"] = (
        f"pladrrr:v1:sha256:{digest}"
    )
    return raw


def build_canonical_promotion_live_adapter_dry_run_runtime_risk_review_packet(
    source_final_credential_scope_recheck_packet: Any,
    runtime_risk_review_decision: Any,
    runtime_risk_review_recorded_at: datetime,
) -> CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewPacket:
    """Build and self-verify a non-authorizing runtime-risk review packet."""

    source, projection = _source(source_final_credential_scope_recheck_packet)
    decision = _decision(runtime_risk_review_decision)
    raw = _assemble(
        source,
        projection,
        decision,
        _aware(
            runtime_risk_review_recorded_at,
            "CPLADRRR_RECORDED_AT_INVALID",
        ).isoformat(),
    )
    return verify_canonical_promotion_live_adapter_dry_run_runtime_risk_review_packet(
        raw,
        source_final_credential_scope_recheck_packet,
    )


def verify_canonical_promotion_live_adapter_dry_run_runtime_risk_review_packet(
    packet: Any,
    source_final_credential_scope_recheck_packet: Any,
) -> CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewPacket:
    """Verify the compact packet against its independently supplied full source."""

    source, projection = _source(source_final_credential_scope_recheck_packet)
    try:
        value = _json(packet)
        candidate = (
            CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewPacket.model_validate(
                value
            )
        )
    except (
        ValidationError,
        CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewError,
        TypeError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewError(
            "CPLADRRR_PACKET_INVALID"
        ) from exc

    decision = _decision(candidate.runtime_risk_review_decision)
    expected = _assemble(
        source,
        projection,
        decision,
        candidate.runtime_risk_review_recorded_at,
    )
    expected["promotion_live_adapter_dry_run_runtime_risk_review_id"] = (
        candidate.promotion_live_adapter_dry_run_runtime_risk_review_id
    )
    expected["promotion_live_adapter_dry_run_runtime_risk_review_hash"] = (
        candidate.promotion_live_adapter_dry_run_runtime_risk_review_hash
    )
    raw = candidate.model_dump(mode="json")
    if any(raw[field] != expected[field] for field in raw):
        _fail("CPLADRRR_PACKET_RECONSTRUCTION_MISMATCH")
    digest = _packet_hash(raw)
    if candidate.promotion_live_adapter_dry_run_runtime_risk_review_hash != digest:
        _fail("CPLADRRR_PACKET_HASH_MISMATCH")
    if candidate.promotion_live_adapter_dry_run_runtime_risk_review_id != (
        f"pladrrr:v1:sha256:{digest}"
    ):
        _fail("CPLADRRR_PACKET_ID_MISMATCH")
    return candidate


__all__ = [
    "BLOCK_OUTCOME",
    "BLOCK_STATE",
    "BLOCK_STATUS",
    "CHECK_NAMES",
    "DOMAINS",
    "FORMAT_VERSION",
    "INDETERMINATE_OUTCOME",
    "MAX_REVIEW_VALIDITY_SECONDS",
    "NO_EFFECT_FIELDS",
    "PASS_OUTCOME",
    "PASS_STATE",
    "PASS_STATUS",
    "CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewError",
    "CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewPacket",
    "RuntimeRiskRequirementProof",
    "RuntimeRiskReviewCheck",
    "RuntimeRiskReviewDecision",
    "RuntimeRiskReviewResult",
    "build_canonical_promotion_live_adapter_dry_run_runtime_risk_review_packet",
    "verify_canonical_promotion_live_adapter_dry_run_runtime_risk_review_packet",
]
