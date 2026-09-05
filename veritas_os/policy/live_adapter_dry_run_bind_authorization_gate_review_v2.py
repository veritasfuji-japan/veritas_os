"""Dry-run Bind Authorization Gate review for contract-bound no-approval routes.

This v2 gate consumes only the v2 Final Bind Authorization Readiness packet
whose Human Approval requirement was resolved to NOT_REQUIRED_BY_ACTION_CONTRACT.
It records readiness for a separate future real Bind authorization artifact and
creates no authority, credentials, dispatch, network call, or external effect.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.live_adapter_dry_run_bind_authorization_gate_review import (
    ACKNOWLEDGEMENTS,
    AUTHORIZATION_REQUIREMENTS,
    INVOCATION_REQUIREMENTS,
    OUTCOMES,
    BindAuthorizationGateReviewDecision,
)
from veritas_os.policy.live_adapter_dry_run_final_bind_authorization_readiness_v2 import (
    CanonicalLiveAdapterDryRunFinalBindAuthorizationReadinessV2Packet,
    LiveAdapterDryRunFinalBindAuthorizationReadinessV2Error,
    verify_live_adapter_dry_run_final_bind_authorization_readiness_v2_packet,
)

FORMAT_VERSION = "canonical-live-adapter-dry-run-bind-authorization-gate-review/v2"
MECHANISM = (
    "review_live_adapter_dry_run_bind_authorization_gate_"
    "with_contract_bound_no_approval/v2"
)
STATUS = "LIVE_ADAPTER_DRY_RUN_BIND_AUTHORIZATION_GATE_V2_REVIEWED_NOT_AUTHORIZED"
CHECK_MODE = "deterministic_local_bind_authorization_gate_review_v2_only"
DOMAIN = "veritas.live-adapter-dry-run-bind-authorization-gate-review-v2.packet/v1"
SCOPE_LIMITATIONS = (
    "NOT_DISPATCHED",
    "NOT_BIND_INVOCATION",
    "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_RECEIPT",
    "NOT_EXECUTION_AUTHORITY",
    "NOT_HUMAN_APPROVAL",
    "HUMAN_APPROVAL_NOT_REQUIRED_BY_ACTION_CONTRACT",
    "NOT_CREDENTIAL_ACCESS",
    "NOT_AUTHORIZATION_HEADER",
    "NOT_NETWORK_CALL",
    "NOT_EXTERNAL_EFFECT",
)


class LiveAdapterDryRunBindAuthorizationGateReviewV2Error(ValueError):
    """Stable fail-closed error for the v2 no-approval gate."""


class FutureRequirementV2(BaseModel):
    """Requirement intentionally left for a separate future real artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int
    name: str
    separate_future_artifact_required: Literal[True]
    satisfied_by_this_packet: Literal[False]


class BindAuthorizationGateReviewV2Result(BaseModel):
    """Deterministic non-authorizing gate result."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    source_final_readiness_passed: Literal[True]
    source_human_approval_requirement_satisfied: Literal[True]
    source_human_approval_not_required_by_action_contract: Literal[True]
    source_authority_evidence_linkage_passed: Literal[True]
    gate_review_passed: bool
    accepted_for_future_real_bind_authorization_artifact: bool
    rejection_reasons: tuple[str, ...]
    comparison_mode: Literal[CHECK_MODE]
    creates_real_bind_authorization: Literal[False]
    creates_execution_authority: Literal[False]
    creates_human_approval: Literal[False]


class CanonicalLiveAdapterDryRunBindAuthorizationGateReviewV2Packet(BaseModel):
    """Content-addressed no-approval gate review packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal[FORMAT_VERSION]
    live_adapter_dry_run_bind_authorization_gate_review_v2_id: str = Field(
        pattern=r"^ladbagr:v2:sha256:[0-9a-f]{64}$"
    )
    live_adapter_dry_run_bind_authorization_gate_review_v2_hash: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    bind_authorization_gate_review_mechanism: Literal[MECHANISM]
    bind_authorization_gate_review_recorded_at: str

    source_final_bind_authorization_readiness_v2_id: str
    source_final_bind_authorization_readiness_v2_hash: str
    source_final_bind_authorization_readiness_v2_packet: dict[str, Any]
    source_human_approval_not_required_linkage_hash: str
    source_authority_evidence_linkage_review_hash: str
    human_approval_requirement_resolution_hash: str

    execution_intent_id: str
    execution_intent_hash: str
    action_contract_id: str
    action_contract_version: str
    action_contract_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    requested_scope: tuple[str, ...]

    bind_authorization_gate_review_decision: BindAuthorizationGateReviewDecision
    bind_authorization_gate_review_decision_digest: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    bind_authorization_gate_review_result: BindAuthorizationGateReviewV2Result
    bind_authorization_gate_review_result_digest: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    future_real_bind_authorization_artifact_requirements: tuple[
        FutureRequirementV2, ...
    ]
    future_real_bind_authorization_artifact_requirements_digest: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    future_bind_invocation_requirements: tuple[FutureRequirementV2, ...]
    future_bind_invocation_requirements_digest: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )

    request_dispatch_state: Literal["NOT_DISPATCHED"]
    bind_state: Literal["NOT_BOUND"]
    authority_state: Literal["NOT_AUTHORIZED"]
    human_approval_state: Literal["NOT_REQUIRED"]
    bind_authorization_state: Literal["NOT_AUTHORIZED"]
    gate_review_state: Literal[
        "PASSED_FOR_FUTURE_BIND_AUTHORIZATION_ARTIFACT",
        "FAILED_FOR_FUTURE_BIND_AUTHORIZATION_ARTIFACT",
    ]

    human_approval_created: Literal[False]
    execution_authority_created: Literal[False]
    bind_authorization_created: Literal[False]
    bind_invoked: Literal[False]
    bind_receipt_created: Literal[False]
    credential_material_accessed: Literal[False]
    authorization_header_constructed: Literal[False]
    request_dispatched: Literal[False]
    network_used: Literal[False]
    external_effect_occurred: Literal[False]
    fail_closed: bool
    bind_authorization_gate_review_status: Literal[STATUS]
    scope_limitations: tuple[Literal[*SCOPE_LIMITATIONS], ...]


def _timestamp(value: Any) -> str:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise LiveAdapterDryRunBindAuthorizationGateReviewV2Error(
            "LADBAGRV2_TIMESTAMP_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiveAdapterDryRunBindAuthorizationGateReviewV2Error(
            "LADBAGRV2_TIMESTAMP_INVALID"
        )
    return parsed.astimezone(timezone.utc).isoformat()


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and value == value and value not in (
        float("inf"),
        float("-inf"),
    ):
        return value
    if isinstance(value, datetime):
        return _timestamp(value)
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json(item) for key, item in value.items()}
    raise LiveAdapterDryRunBindAuthorizationGateReviewV2Error(
        "LADBAGRV2_INVALID_JSON_VALUE"
    )


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
    omitted = {
        "live_adapter_dry_run_bind_authorization_gate_review_v2_id",
        "live_adapter_dry_run_bind_authorization_gate_review_v2_hash",
    }
    return _digest(
        DOMAIN,
        {key: value for key, value in raw.items() if key not in omitted},
    )


def _source(
    value: Any,
) -> CanonicalLiveAdapterDryRunFinalBindAuthorizationReadinessV2Packet:
    try:
        return verify_live_adapter_dry_run_final_bind_authorization_readiness_v2_packet(
            value
        )
    except (
        LiveAdapterDryRunFinalBindAuthorizationReadinessV2Error,
        TypeError,
        ValueError,
    ) as exc:
        raise LiveAdapterDryRunBindAuthorizationGateReviewV2Error(
            "LADBAGRV2_SOURCE_INVALID"
        ) from exc


def _validate_source(
    source: CanonicalLiveAdapterDryRunFinalBindAuthorizationReadinessV2Packet,
) -> None:
    result = source.final_bind_authorization_readiness_result
    if (
        source.request_dispatch_state != "NOT_DISPATCHED"
        or source.bind_state != "NOT_BOUND"
        or source.authority_state != "NOT_AUTHORIZED"
        or source.human_approval_state != "NOT_REQUIRED"
        or source.final_readiness_state
        != "READY_FOR_FUTURE_BIND_AUTHORIZATION_GATE"
        or source.fail_closed
        or not result.accepted_for_future_bind_authorization_gate_review
        or not result.source_human_approval_requirement_satisfied
        or not result.source_human_approval_not_required_by_action_contract
        or source.human_approval_created
        or source.execution_authority_created
        or source.bind_authorization_created
        or source.bind_invoked
        or source.network_used
        or source.external_effect_occurred
    ):
        raise LiveAdapterDryRunBindAuthorizationGateReviewV2Error(
            "LADBAGRV2_SOURCE_REJECTED"
        )


def _decision(value: Any) -> BindAuthorizationGateReviewDecision:
    try:
        decision = BindAuthorizationGateReviewDecision.model_validate(_json(value))
        normalized = decision.model_copy(
            update={"reviewed_at": _timestamp(decision.reviewed_at)}
        )
    except (ValidationError, TypeError, ValueError) as exc:
        raise LiveAdapterDryRunBindAuthorizationGateReviewV2Error(
            "LADBAGRV2_DECISION_INVALID"
        ) from exc
    if not all(getattr(normalized, field) for field in ACKNOWLEDGEMENTS):
        raise LiveAdapterDryRunBindAuthorizationGateReviewV2Error(
            "LADBAGRV2_ACKNOWLEDGEMENT_MISSING"
        )
    return normalized


def _requirements(names: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        {
            "ordinal": ordinal,
            "name": name,
            "separate_future_artifact_required": True,
            "satisfied_by_this_packet": False,
        }
        for ordinal, name in enumerate(names, 1)
    ]


def _derived(
    decision: BindAuthorizationGateReviewDecision,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    accepted = decision.review_outcome == OUTCOMES[0]
    result = {
        "source_final_readiness_passed": True,
        "source_human_approval_requirement_satisfied": True,
        "source_human_approval_not_required_by_action_contract": True,
        "source_authority_evidence_linkage_passed": True,
        "gate_review_passed": accepted,
        "accepted_for_future_real_bind_authorization_artifact": accepted,
        "rejection_reasons": (
            [] if accepted else ["BIND_AUTHORIZATION_GATE_REVIEW_FAILED"]
        ),
        "comparison_mode": CHECK_MODE,
        "creates_real_bind_authorization": False,
        "creates_execution_authority": False,
        "creates_human_approval": False,
    }
    return (
        result,
        _requirements(AUTHORIZATION_REQUIREMENTS),
        _requirements(INVOCATION_REQUIREMENTS),
    )


def build_live_adapter_dry_run_bind_authorization_gate_review_v2_packet(
    source_final_bind_authorization_readiness_v2_packet: Any,
    bind_authorization_gate_review_decision: Any,
    bind_authorization_gate_review_recorded_at: datetime,
) -> CanonicalLiveAdapterDryRunBindAuthorizationGateReviewV2Packet:
    """Build a non-authorizing gate packet for the no-approval route."""

    source = _source(source_final_bind_authorization_readiness_v2_packet)
    _validate_source(source)
    decision = _decision(bind_authorization_gate_review_decision)
    result, authorization, invocation = _derived(decision)
    accepted = result["accepted_for_future_real_bind_authorization_artifact"]

    decision_digest = _digest("decision/v2", decision)
    result_digest = _digest("result/v2", result)
    authorization_digest = _digest("authorization-requirements/v2", authorization)
    invocation_digest = _digest("invocation-requirements/v2", invocation)
    source_raw = source.model_dump(mode="json")
    raw = {
        "format_version": FORMAT_VERSION,
        "bind_authorization_gate_review_mechanism": MECHANISM,
        "bind_authorization_gate_review_recorded_at": _timestamp(
            bind_authorization_gate_review_recorded_at
        ),
        "source_final_bind_authorization_readiness_v2_id": (
            source.live_adapter_dry_run_final_bind_authorization_readiness_v2_id
        ),
        "source_final_bind_authorization_readiness_v2_hash": (
            source.live_adapter_dry_run_final_bind_authorization_readiness_v2_hash
        ),
        "source_final_bind_authorization_readiness_v2_packet": source_raw,
        "source_human_approval_not_required_linkage_hash": (
            source.source_human_approval_not_required_linkage_hash
        ),
        "source_authority_evidence_linkage_review_hash": (
            source.source_authority_evidence_linkage_review_hash
        ),
        "human_approval_requirement_resolution_hash": (
            source.human_approval_requirement_resolution_hash
        ),
        "execution_intent_id": source.execution_intent_id,
        "execution_intent_hash": source.execution_intent_hash,
        "action_contract_id": source.action_contract_id,
        "action_contract_version": source.action_contract_version,
        "action_contract_digest": source.action_contract_digest,
        "requested_scope": source.requested_scope,
        "bind_authorization_gate_review_decision": decision.model_dump(mode="json"),
        "bind_authorization_gate_review_decision_digest": decision_digest,
        "bind_authorization_gate_review_result": result,
        "bind_authorization_gate_review_result_digest": result_digest,
        "future_real_bind_authorization_artifact_requirements": authorization,
        "future_real_bind_authorization_artifact_requirements_digest": (
            authorization_digest
        ),
        "future_bind_invocation_requirements": invocation,
        "future_bind_invocation_requirements_digest": invocation_digest,
        "request_dispatch_state": "NOT_DISPATCHED",
        "bind_state": "NOT_BOUND",
        "authority_state": "NOT_AUTHORIZED",
        "human_approval_state": "NOT_REQUIRED",
        "bind_authorization_state": "NOT_AUTHORIZED",
        "gate_review_state": (
            "PASSED_FOR_FUTURE_BIND_AUTHORIZATION_ARTIFACT"
            if accepted
            else "FAILED_FOR_FUTURE_BIND_AUTHORIZATION_ARTIFACT"
        ),
        "human_approval_created": False,
        "execution_authority_created": False,
        "bind_authorization_created": False,
        "bind_invoked": False,
        "bind_receipt_created": False,
        "credential_material_accessed": False,
        "authorization_header_constructed": False,
        "request_dispatched": False,
        "network_used": False,
        "external_effect_occurred": False,
        "fail_closed": not accepted,
        "bind_authorization_gate_review_status": STATUS,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_bind_authorization_gate_review_v2_hash"] = digest
    raw["live_adapter_dry_run_bind_authorization_gate_review_v2_id"] = (
        f"ladbagr:v2:sha256:{digest}"
    )
    return verify_live_adapter_dry_run_bind_authorization_gate_review_v2_packet(raw)


def verify_live_adapter_dry_run_bind_authorization_gate_review_v2_packet(
    value: Any,
) -> CanonicalLiveAdapterDryRunBindAuthorizationGateReviewV2Packet:
    """Re-verify source, decision, requirements, non-effects, and packet hash."""

    try:
        packet = (
            value
            if isinstance(
                value,
                CanonicalLiveAdapterDryRunBindAuthorizationGateReviewV2Packet,
            )
            else CanonicalLiveAdapterDryRunBindAuthorizationGateReviewV2Packet.model_validate(
                _json(value)
            )
        )
    except (
        ValidationError,
        TypeError,
        LiveAdapterDryRunBindAuthorizationGateReviewV2Error,
    ) as exc:
        raise LiveAdapterDryRunBindAuthorizationGateReviewV2Error(
            "LADBAGRV2_PACKET_SCHEMA_INVALID"
        ) from exc

    source = _source(packet.source_final_bind_authorization_readiness_v2_packet)
    _validate_source(source)
    decision = _decision(packet.bind_authorization_gate_review_decision)
    result, authorization, invocation = _derived(decision)
    accepted = result["accepted_for_future_real_bind_authorization_artifact"]

    identities = (
        packet.source_final_bind_authorization_readiness_v2_id
        == source.live_adapter_dry_run_final_bind_authorization_readiness_v2_id,
        packet.source_final_bind_authorization_readiness_v2_hash
        == source.live_adapter_dry_run_final_bind_authorization_readiness_v2_hash,
        packet.source_human_approval_not_required_linkage_hash
        == source.source_human_approval_not_required_linkage_hash,
        packet.source_authority_evidence_linkage_review_hash
        == source.source_authority_evidence_linkage_review_hash,
        packet.human_approval_requirement_resolution_hash
        == source.human_approval_requirement_resolution_hash,
        packet.execution_intent_id == source.execution_intent_id,
        packet.execution_intent_hash == source.execution_intent_hash,
        packet.action_contract_id == source.action_contract_id,
        packet.action_contract_version == source.action_contract_version,
        packet.action_contract_digest == source.action_contract_digest,
        packet.requested_scope == source.requested_scope,
    )
    if not all(identities):
        raise LiveAdapterDryRunBindAuthorizationGateReviewV2Error(
            "LADBAGRV2_IDENTITY_MISMATCH"
        )

    expected_gate_state = (
        "PASSED_FOR_FUTURE_BIND_AUTHORIZATION_ARTIFACT"
        if accepted
        else "FAILED_FOR_FUTURE_BIND_AUTHORIZATION_ARTIFACT"
    )
    if (
        packet.bind_authorization_gate_review_decision_digest
        != _digest("decision/v2", decision)
        or _json(packet.bind_authorization_gate_review_result) != _json(result)
        or packet.bind_authorization_gate_review_result_digest
        != _digest("result/v2", result)
        or _json(packet.future_real_bind_authorization_artifact_requirements)
        != _json(authorization)
        or packet.future_real_bind_authorization_artifact_requirements_digest
        != _digest("authorization-requirements/v2", authorization)
        or _json(packet.future_bind_invocation_requirements)
        != _json(invocation)
        or packet.future_bind_invocation_requirements_digest
        != _digest("invocation-requirements/v2", invocation)
        or packet.gate_review_state != expected_gate_state
        or packet.fail_closed != (not accepted)
    ):
        raise LiveAdapterDryRunBindAuthorizationGateReviewV2Error(
            "LADBAGRV2_DERIVED_MISMATCH"
        )

    effects = (
        packet.human_approval_created,
        packet.execution_authority_created,
        packet.bind_authorization_created,
        packet.bind_invoked,
        packet.bind_receipt_created,
        packet.credential_material_accessed,
        packet.authorization_header_constructed,
        packet.request_dispatched,
        packet.network_used,
        packet.external_effect_occurred,
    )
    if any(effects):
        raise LiveAdapterDryRunBindAuthorizationGateReviewV2Error(
            "LADBAGRV2_EFFECT_INVALID"
        )
    if packet.scope_limitations != SCOPE_LIMITATIONS:
        raise LiveAdapterDryRunBindAuthorizationGateReviewV2Error(
            "LADBAGRV2_SCOPE_LIMITATIONS_MISMATCH"
        )

    actual = packet.model_dump(mode="python")
    digest = _packet_hash(actual)
    if (
        packet.live_adapter_dry_run_bind_authorization_gate_review_v2_hash
        != digest
        or packet.live_adapter_dry_run_bind_authorization_gate_review_v2_id
        != f"ladbagr:v2:sha256:{digest}"
    ):
        raise LiveAdapterDryRunBindAuthorizationGateReviewV2Error(
            "LADBAGRV2_HASH_MISMATCH"
        )
    return packet
