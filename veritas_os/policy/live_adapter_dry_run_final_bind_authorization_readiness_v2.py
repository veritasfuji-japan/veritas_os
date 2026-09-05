"""Final dry-run Bind readiness for contract-bound no-approval routes.

This v2 artifact accepts only a verified Human Approval Not Required linkage
packet. It preserves the existing v1 approval-required path unchanged and does
not create Human Approval, execution authority, Bind authorization, or effects.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.live_adapter_dry_run_final_bind_authorization_readiness import (
    ACKNOWLEDGEMENTS,
    OUTCOMES,
    FinalBindAuthorizationReadinessReviewDecision,
)
from veritas_os.policy.live_adapter_dry_run_human_approval_not_required_linkage import (
    CanonicalLiveAdapterDryRunHumanApprovalNotRequiredLinkagePacket,
    LiveAdapterDryRunHumanApprovalNotRequiredLinkageError,
    verify_live_adapter_dry_run_human_approval_not_required_linkage_packet,
)

FORMAT_VERSION = "canonical-live-adapter-dry-run-final-bind-authorization-readiness/v2"
MECHANISM = (
    "evaluate_live_adapter_dry_run_final_bind_authorization_readiness_"
    "with_contract_bound_no_approval/v2"
)
STATUS = (
    "LIVE_ADAPTER_DRY_RUN_FINAL_BIND_AUTHORIZATION_READINESS_V2_"
    "RECORDED_NOT_AUTHORIZED"
)
CHECK_MODE = "deterministic_local_final_bind_authorization_readiness_v2_only"
DOMAIN = "veritas.live-adapter-dry-run-final-bind-authorization-readiness-v2.packet/v1"
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


class LiveAdapterDryRunFinalBindAuthorizationReadinessV2Error(ValueError):
    """Stable fail-closed error for v2 final readiness."""


class FinalReadinessV2Result(BaseModel):
    """Deterministic readiness result for the no-approval route."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    source_no_approval_linkage_verified: Literal[True]
    source_human_approval_requirement_satisfied: Literal[True]
    source_human_approval_not_required_by_action_contract: Literal[True]
    source_authority_evidence_linkage_passed: Literal[True]
    final_review_passed: bool
    accepted_for_future_bind_authorization_gate_review: bool
    rejection_reasons: tuple[str, ...]
    comparison_mode: Literal[CHECK_MODE]
    creates_bind_authorization: Literal[False]
    creates_execution_authority: Literal[False]
    creates_human_approval: Literal[False]


class CanonicalLiveAdapterDryRunFinalBindAuthorizationReadinessV2Packet(BaseModel):
    """Content-addressed final readiness packet for no-approval routes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal[FORMAT_VERSION]
    live_adapter_dry_run_final_bind_authorization_readiness_v2_id: str = Field(
        pattern=r"^ladfbar:v2:sha256:[0-9a-f]{64}$"
    )
    live_adapter_dry_run_final_bind_authorization_readiness_v2_hash: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    final_bind_authorization_readiness_mechanism: Literal[MECHANISM]
    final_bind_authorization_readiness_recorded_at: str

    source_human_approval_not_required_linkage_id: str
    source_human_approval_not_required_linkage_hash: str
    source_human_approval_not_required_linkage_packet: dict[str, Any]
    source_authority_evidence_linkage_review_hash: str
    human_approval_requirement_resolution_hash: str

    execution_intent_id: str
    execution_intent_hash: str
    action_contract_id: str
    action_contract_version: str
    action_contract_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    requested_scope: tuple[str, ...]

    final_bind_authorization_readiness_review_decision: (
        FinalBindAuthorizationReadinessReviewDecision
    )
    final_bind_authorization_readiness_review_decision_digest: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    final_bind_authorization_readiness_result: FinalReadinessV2Result
    final_bind_authorization_readiness_result_digest: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )

    request_dispatch_state: Literal["NOT_DISPATCHED"]
    bind_state: Literal["NOT_BOUND"]
    authority_state: Literal["NOT_AUTHORIZED"]
    human_approval_state: Literal["NOT_REQUIRED"]
    final_readiness_state: Literal[
        "READY_FOR_FUTURE_BIND_AUTHORIZATION_GATE",
        "NOT_READY_FOR_FUTURE_BIND_AUTHORIZATION_GATE",
    ]

    human_approval_created: Literal[False]
    execution_authority_created: Literal[False]
    bind_authorization_created: Literal[False]
    bind_invoked: Literal[False]
    bind_receipt_created: Literal[False]
    credential_material_accessed: Literal[False]
    authorization_header_constructed: Literal[False]
    network_used: Literal[False]
    external_effect_occurred: Literal[False]
    fail_closed: bool
    final_bind_authorization_readiness_status: Literal[STATUS]
    scope_limitations: tuple[Literal[*SCOPE_LIMITATIONS], ...]


def _timestamp(value: Any) -> str:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise LiveAdapterDryRunFinalBindAuthorizationReadinessV2Error(
            "LADFBARV2_TIMESTAMP_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiveAdapterDryRunFinalBindAuthorizationReadinessV2Error(
            "LADFBARV2_TIMESTAMP_INVALID"
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
    raise LiveAdapterDryRunFinalBindAuthorizationReadinessV2Error(
        "LADFBARV2_INVALID_JSON_VALUE"
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
        "live_adapter_dry_run_final_bind_authorization_readiness_v2_id",
        "live_adapter_dry_run_final_bind_authorization_readiness_v2_hash",
    }
    return _digest(
        DOMAIN,
        {key: value for key, value in raw.items() if key not in omitted},
    )


def _source(
    value: Any,
) -> CanonicalLiveAdapterDryRunHumanApprovalNotRequiredLinkagePacket:
    try:
        return verify_live_adapter_dry_run_human_approval_not_required_linkage_packet(
            value
        )
    except (
        LiveAdapterDryRunHumanApprovalNotRequiredLinkageError,
        TypeError,
        ValueError,
    ) as exc:
        raise LiveAdapterDryRunFinalBindAuthorizationReadinessV2Error(
            "LADFBARV2_SOURCE_INVALID"
        ) from exc


def _validate_source(
    source: CanonicalLiveAdapterDryRunHumanApprovalNotRequiredLinkagePacket,
) -> None:
    result = source.human_approval_not_required_linkage_result
    if (
        source.request_dispatch_state != "NOT_DISPATCHED"
        or source.bind_state != "NOT_BOUND"
        or source.authority_state != "NOT_AUTHORIZED"
        or source.human_approval_state != "NOT_REQUIRED"
        or source.fail_closed
        or not result.accepted_for_final_bind_authorization_readiness
        or result.human_approval_required
        or source.human_approval_reference_count != 0
        or source.human_approval_created
        or source.execution_authority_created
        or source.bind_authorization_created
        or source.bind_invoked
        or source.network_used
        or source.external_effect_occurred
    ):
        raise LiveAdapterDryRunFinalBindAuthorizationReadinessV2Error(
            "LADFBARV2_SOURCE_REJECTED"
        )


def _decision(value: Any) -> FinalBindAuthorizationReadinessReviewDecision:
    try:
        decision = FinalBindAuthorizationReadinessReviewDecision.model_validate(
            _json(value)
        )
        normalized = decision.model_copy(
            update={"reviewed_at": _timestamp(decision.reviewed_at)}
        )
    except (ValidationError, TypeError, ValueError) as exc:
        raise LiveAdapterDryRunFinalBindAuthorizationReadinessV2Error(
            "LADFBARV2_DECISION_INVALID"
        ) from exc
    if not all(getattr(normalized, field) for field in ACKNOWLEDGEMENTS):
        raise LiveAdapterDryRunFinalBindAuthorizationReadinessV2Error(
            "LADFBARV2_ACKNOWLEDGEMENT_MISSING"
        )
    return normalized


def _derived(
    decision: FinalBindAuthorizationReadinessReviewDecision,
) -> dict[str, Any]:
    accepted = decision.review_outcome == OUTCOMES[0]
    return {
        "source_no_approval_linkage_verified": True,
        "source_human_approval_requirement_satisfied": True,
        "source_human_approval_not_required_by_action_contract": True,
        "source_authority_evidence_linkage_passed": True,
        "final_review_passed": accepted,
        "accepted_for_future_bind_authorization_gate_review": accepted,
        "rejection_reasons": (
            [] if accepted else ["FINAL_BIND_AUTHORIZATION_READINESS_REJECTED"]
        ),
        "comparison_mode": CHECK_MODE,
        "creates_bind_authorization": False,
        "creates_execution_authority": False,
        "creates_human_approval": False,
    }


def build_live_adapter_dry_run_final_bind_authorization_readiness_v2_packet(
    source_human_approval_not_required_linkage_packet: Any,
    final_bind_authorization_readiness_review_decision: Any,
    final_bind_authorization_readiness_recorded_at: datetime,
) -> CanonicalLiveAdapterDryRunFinalBindAuthorizationReadinessV2Packet:
    """Build final readiness without requiring or inventing Human Approval."""

    source = _source(source_human_approval_not_required_linkage_packet)
    _validate_source(source)
    decision = _decision(final_bind_authorization_readiness_review_decision)
    result = _derived(decision)
    accepted = result["accepted_for_future_bind_authorization_gate_review"]

    source_raw = source.model_dump(mode="json")
    decision_digest = _digest("decision/v2", decision)
    result_digest = _digest("result/v2", result)
    raw = {
        "format_version": FORMAT_VERSION,
        "final_bind_authorization_readiness_mechanism": MECHANISM,
        "final_bind_authorization_readiness_recorded_at": _timestamp(
            final_bind_authorization_readiness_recorded_at
        ),
        "source_human_approval_not_required_linkage_id": (
            source.live_adapter_dry_run_human_approval_not_required_linkage_id
        ),
        "source_human_approval_not_required_linkage_hash": (
            source.live_adapter_dry_run_human_approval_not_required_linkage_hash
        ),
        "source_human_approval_not_required_linkage_packet": source_raw,
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
        "final_bind_authorization_readiness_review_decision": decision.model_dump(
            mode="json"
        ),
        "final_bind_authorization_readiness_review_decision_digest": decision_digest,
        "final_bind_authorization_readiness_result": result,
        "final_bind_authorization_readiness_result_digest": result_digest,
        "request_dispatch_state": "NOT_DISPATCHED",
        "bind_state": "NOT_BOUND",
        "authority_state": "NOT_AUTHORIZED",
        "human_approval_state": "NOT_REQUIRED",
        "final_readiness_state": (
            "READY_FOR_FUTURE_BIND_AUTHORIZATION_GATE"
            if accepted
            else "NOT_READY_FOR_FUTURE_BIND_AUTHORIZATION_GATE"
        ),
        "human_approval_created": False,
        "execution_authority_created": False,
        "bind_authorization_created": False,
        "bind_invoked": False,
        "bind_receipt_created": False,
        "credential_material_accessed": False,
        "authorization_header_constructed": False,
        "network_used": False,
        "external_effect_occurred": False,
        "fail_closed": not accepted,
        "final_bind_authorization_readiness_status": STATUS,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_final_bind_authorization_readiness_v2_hash"] = digest
    raw["live_adapter_dry_run_final_bind_authorization_readiness_v2_id"] = (
        f"ladfbar:v2:sha256:{digest}"
    )
    return verify_live_adapter_dry_run_final_bind_authorization_readiness_v2_packet(
        raw
    )


def verify_live_adapter_dry_run_final_bind_authorization_readiness_v2_packet(
    value: Any,
) -> CanonicalLiveAdapterDryRunFinalBindAuthorizationReadinessV2Packet:
    """Re-verify source, decision, derived result, non-effects, and hash."""

    try:
        packet = (
            value
            if isinstance(
                value,
                CanonicalLiveAdapterDryRunFinalBindAuthorizationReadinessV2Packet,
            )
            else CanonicalLiveAdapterDryRunFinalBindAuthorizationReadinessV2Packet.model_validate(
                _json(value)
            )
        )
    except (
        ValidationError,
        TypeError,
        LiveAdapterDryRunFinalBindAuthorizationReadinessV2Error,
    ) as exc:
        raise LiveAdapterDryRunFinalBindAuthorizationReadinessV2Error(
            "LADFBARV2_PACKET_SCHEMA_INVALID"
        ) from exc

    source = _source(packet.source_human_approval_not_required_linkage_packet)
    _validate_source(source)
    decision = _decision(packet.final_bind_authorization_readiness_review_decision)
    expected_result = _derived(decision)
    accepted = expected_result["accepted_for_future_bind_authorization_gate_review"]

    identities = (
        packet.source_human_approval_not_required_linkage_id
        == source.live_adapter_dry_run_human_approval_not_required_linkage_id,
        packet.source_human_approval_not_required_linkage_hash
        == source.live_adapter_dry_run_human_approval_not_required_linkage_hash,
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
        raise LiveAdapterDryRunFinalBindAuthorizationReadinessV2Error(
            "LADFBARV2_IDENTITY_MISMATCH"
        )

    if (
        packet.final_bind_authorization_readiness_review_decision_digest
        != _digest("decision/v2", decision)
        or _json(packet.final_bind_authorization_readiness_result)
        != _json(expected_result)
        or packet.final_bind_authorization_readiness_result_digest
        != _digest("result/v2", expected_result)
        or packet.final_readiness_state
        != (
            "READY_FOR_FUTURE_BIND_AUTHORIZATION_GATE"
            if accepted
            else "NOT_READY_FOR_FUTURE_BIND_AUTHORIZATION_GATE"
        )
        or packet.fail_closed != (not accepted)
    ):
        raise LiveAdapterDryRunFinalBindAuthorizationReadinessV2Error(
            "LADFBARV2_DERIVED_MISMATCH"
        )

    effects = (
        packet.human_approval_created,
        packet.execution_authority_created,
        packet.bind_authorization_created,
        packet.bind_invoked,
        packet.bind_receipt_created,
        packet.credential_material_accessed,
        packet.authorization_header_constructed,
        packet.network_used,
        packet.external_effect_occurred,
    )
    if any(effects):
        raise LiveAdapterDryRunFinalBindAuthorizationReadinessV2Error(
            "LADFBARV2_EFFECT_INVALID"
        )
    if packet.scope_limitations != SCOPE_LIMITATIONS:
        raise LiveAdapterDryRunFinalBindAuthorizationReadinessV2Error(
            "LADFBARV2_SCOPE_LIMITATIONS_MISMATCH"
        )

    actual = packet.model_dump(mode="python")
    digest = _packet_hash(actual)
    if (
        packet.live_adapter_dry_run_final_bind_authorization_readiness_v2_hash
        != digest
        or packet.live_adapter_dry_run_final_bind_authorization_readiness_v2_id
        != f"ladfbar:v2:sha256:{digest}"
    ):
        raise LiveAdapterDryRunFinalBindAuthorizationReadinessV2Error(
            "LADFBARV2_HASH_MISMATCH"
        )
    return packet
