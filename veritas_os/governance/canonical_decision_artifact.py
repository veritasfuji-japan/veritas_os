"""Deterministic Canonical Decision Artifact v1 construction and verification.

The verifier establishes only internal structure, canonical hash integrity, and
content-addressed identifier coherence.  It does not establish source
authenticity, provenance, TrustLog or replay membership, governance signatures,
human approval, handoff readiness, or execution authority.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Mapping

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    ValidationError,
    model_serializer,
    model_validator,
)

from veritas_os.api.schemas import (
    DecideResponse,
    LineagePromotabilitySummary,
    TransitionRefusal,
)
from veritas_os.core.decision_semantics import validate_gate_business_combination
from veritas_os.security.hash import sha256_hex

CDA_FORMAT_VERSION = "canonical-decision-artifact/v1"
CDA_HASH_PROFILE = "veritas.canonical-decision/v1"
CDA_PROJECTION_VERSION = "canonical-decision-projection/v1"
CDA_SOURCE_TYPE = "DecideResponse"
CDA_DECISION_ID_PREFIX = "cda:v1:sha256:"
CDA_CHOSEN_BINDING_PROFILE = "veritas.canonical-decision.chosen-value/v1"
CDA_GOVERNANCE_IDENTITY_BINDING_PROFILE = (
    "veritas.canonical-decision.governance-identity/v1"
)
CDA_LINEAGE_PROMOTABILITY_BINDING_PROFILE = (
    "veritas.canonical-decision.lineage-promotability/v1"
)
CDA_TRANSITION_REFUSAL_BINDING_PROFILE = (
    "veritas.canonical-decision.transition-refusal/v1"
)

_DIGEST_PATTERN = r"^[0-9a-f]{64}$"
_DECISION_ID_PATTERN = r"^cda:v1:sha256:[0-9a-f]{64}$"
_CANONICAL_TIMESTAMP_PATTERN = (
    r"^[0-9]{4}-(0[1-9]|1[0-2])-([0-2][0-9]|3[01])T"
    r"([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]\.[0-9]{6}Z$"
)

_SOURCE_FIELDS = frozenset(
    {
        "request_id",
        "chosen",
        "decision_status",
        "rejection_reason",
        "gate_decision",
        "business_decision",
        "next_action",
        "actionability_status",
        "requires_bind_before_execution",
        "human_review_required",
        "required_evidence",
        "missing_evidence",
        "satisfied_evidence",
        "rationale",
        "refusal_reason",
        "actionability_block_reason",
        "actionability_refusal_type",
        "governance_identity",
        "lineage_promotability",
        "transition_refusal",
        "bind_outcome",
        "bind_failure_reason",
        "bind_reason_code",
        "bind_receipt_id",
        "execution_intent_id",
        "bound_execution_intent_id",
        "authority_check_result",
        "constraint_check_result",
        "drift_check_result",
        "risk_check_result",
        "bind_summary",
        "bind_operator_summary",
        "bind_operator_detail",
    }
)
POST_BIND_SOURCE_FIELDS = (
    "bind_outcome",
    "bind_failure_reason",
    "bind_reason_code",
    "bind_receipt_id",
    "execution_intent_id",
    "bound_execution_intent_id",
    "authority_check_result",
    "constraint_check_result",
    "drift_check_result",
    "risk_check_result",
    "bind_summary",
    "bind_operator_summary",
    "bind_operator_detail",
)
PRE_BIND_ACTIONABILITY_STATES = frozenset(
    {
        "reviewable_only",
        "bind_required_before_execution",
        "blocked",
        "human_review_required",
        "formation_transition_refused",
    }
)


class CanonicalDecisionArtifactBuildReason(str, Enum):
    """Stable machine-readable reasons for refusing artifact construction."""

    SOURCE_NOT_DECIDE_RESPONSE = "SOURCE_NOT_DECIDE_RESPONSE"
    SOURCE_NOT_NORMALIZED = "SOURCE_NOT_NORMALIZED"
    SOURCE_REQUEST_ID_MISSING = "SOURCE_REQUEST_ID_MISSING"
    POST_BIND_SOURCE_REFUSED = "POST_BIND_SOURCE_REFUSED"
    UNRESOLVED_GATE_DECISION = "UNRESOLVED_GATE_DECISION"
    POST_BIND_ACTIONABILITY_REFUSED = "POST_BIND_ACTIONABILITY_REFUSED"
    ACTIONABILITY_BOUNDARY_INVALID = "ACTIONABILITY_BOUNDARY_INVALID"
    NAIVE_TIMESTAMP = "NAIVE_TIMESTAMP"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    NON_CANONICAL_JSON_VALUE = "NON_CANONICAL_JSON_VALUE"


class CanonicalDecisionArtifactBuildError(ValueError):
    """Fail-closed builder error carrying a stable reason code."""

    def __init__(self, reason_code: CanonicalDecisionArtifactBuildReason) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code.value)


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CanonicalDecisionSourceContract(_FrozenModel):
    """Frozen identity of the normalized source projection contract."""

    type: Literal["DecideResponse"] = CDA_SOURCE_TYPE
    projection_version: Literal["canonical-decision-projection/v1"] = (
        CDA_PROJECTION_VERSION
    )


class CanonicalDecisionChosenBinding(_FrozenModel):
    """Opaque binding to the exact normalized chosen value."""

    profile: Literal["veritas.canonical-decision.chosen-value/v1"]
    sha256: str = Field(pattern=_DIGEST_PATTERN)


class CanonicalDecisionGovernanceIdentityBinding(_FrozenModel):
    """Opaque binding to a structurally present governance identity."""

    profile: Literal["veritas.canonical-decision.governance-identity/v1"]
    sha256: str = Field(pattern=_DIGEST_PATTERN)


class CanonicalDecisionLineagePromotabilityBinding(_FrozenModel):
    """Opaque binding to the normalized lineage promotability record."""

    profile: Literal["veritas.canonical-decision.lineage-promotability/v1"]
    sha256: str = Field(pattern=_DIGEST_PATTERN)


class CanonicalDecisionTransitionRefusalBinding(_FrozenModel):
    """Opaque binding to the normalized transition refusal record."""

    profile: Literal["veritas.canonical-decision.transition-refusal/v1"]
    sha256: str = Field(pattern=_DIGEST_PATTERN)


class CanonicalSelectedActionEvidence(_FrozenModel):
    """Content address of a normalized structured execution candidate."""

    candidate_hash: str = Field(pattern=_DIGEST_PATTERN)
    chosen_binding_sha256: str = Field(pattern=_DIGEST_PATTERN)


class CanonicalPolicySnapshotEvidence(_FrozenModel):
    """Policy identity already authenticated by the decision pipeline."""

    snapshot_id: str = Field(pattern=_DIGEST_PATTERN)
    version: str = Field(min_length=1)
    semantic_digest: str = Field(pattern=_DIGEST_PATTERN)
    signature_verified: Literal[True]
    signer_id: str = Field(min_length=1)
    verified_at: str = Field(min_length=1)


class CanonicalDecisionProjection(_FrozenModel):
    """Exact closed v1 decision projection."""

    formation_status: Literal["COMPLETE", "INCOMPLETE"]
    chosen_binding: CanonicalDecisionChosenBinding
    selected_action_evidence: CanonicalSelectedActionEvidence | None = None
    policy_snapshot_evidence: CanonicalPolicySnapshotEvidence | None = None
    decision_status: Literal["allow", "modify", "rejected", "block", "abstain"]
    rejection_reason: str | None
    gate_decision: Literal["proceed", "hold", "block", "human_review_required"]
    business_decision: Literal[
        "APPROVE",
        "DENY",
        "HOLD",
        "REVIEW_REQUIRED",
        "POLICY_DEFINITION_REQUIRED",
        "EVIDENCE_REQUIRED",
    ]
    next_action: str
    actionability_status: Literal[
        "reviewable_only",
        "bind_required_before_execution",
        "blocked",
        "human_review_required",
        "formation_transition_refused",
    ]
    requires_bind_before_execution: bool
    human_review_required: bool
    required_evidence: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    satisfied_evidence: tuple[str, ...]
    rationale: str | None
    refusal_reason: str | None
    actionability_block_reason: str | None
    actionability_refusal_type: str | None
    governance_identity_binding: CanonicalDecisionGovernanceIdentityBinding | None
    lineage_promotability_binding: CanonicalDecisionLineagePromotabilityBinding | None
    transition_refusal_binding: CanonicalDecisionTransitionRefusalBinding | None

    @model_serializer(mode="wrap")
    def _serialize_optional_evidence(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        """Keep legacy CDA-v1 JSON exact when new evidence is unavailable."""
        serialized = handler(self)
        if self.selected_action_evidence is None:
            serialized.pop("selected_action_evidence", None)
        if self.policy_snapshot_evidence is None:
            serialized.pop("policy_snapshot_evidence", None)
        return serialized

    @model_validator(mode="after")
    def _validate_semantics(self) -> "CanonicalDecisionProjection":
        complete = self.formation_status == "COMPLETE"
        if complete != (self.governance_identity_binding is not None):
            raise ValueError("formation status contradicts governance identity binding")
        _validate_actionability_boundary(
            self.actionability_status,
            self.requires_bind_before_execution,
            self.human_review_required,
        )
        validate_gate_business_combination(
            gate_decision=self.gate_decision,
            business_decision=self.business_decision,
            human_review_required=self.human_review_required,
        )
        return self


class CanonicalDecisionArtifact(_FrozenModel):
    """Immutable, content-addressed Canonical Decision Artifact v1."""

    format_version: Literal["canonical-decision-artifact/v1"]
    hash_profile: Literal["veritas.canonical-decision/v1"]
    decision_id: str = Field(pattern=_DECISION_ID_PATTERN)
    decision_hash: str = Field(pattern=_DIGEST_PATTERN)
    decision_ts: str = Field(pattern=_CANONICAL_TIMESTAMP_PATTERN)
    request_id: str = Field(min_length=1)
    source_contract: CanonicalDecisionSourceContract
    decision: CanonicalDecisionProjection

    @model_validator(mode="after")
    def _validate_timestamp(self) -> "CanonicalDecisionArtifact":
        if _normalize_timestamp(self.decision_ts) != self.decision_ts:
            raise ValueError("decision_ts is not canonical UTC")
        return self


class CanonicalDecisionArtifactVerificationReason(str, Enum):
    """Stable verifier result reasons in deterministic reporting order."""

    ARTIFACT_MISSING = "ARTIFACT_MISSING"
    ARTIFACT_SCHEMA_INVALID = "ARTIFACT_SCHEMA_INVALID"
    ARTIFACT_HASH_MISMATCH = "ARTIFACT_HASH_MISMATCH"
    ARTIFACT_DECISION_ID_MISMATCH = "ARTIFACT_DECISION_ID_MISMATCH"


class CanonicalDecisionArtifactVerificationResult(_FrozenModel):
    """Fail-closed result of independent internal artifact verification."""

    is_valid: bool
    reason_codes: tuple[str, ...]
    artifact: CanonicalDecisionArtifact | None
    computed_decision_hash: str | None
    expected_decision_id: str | None


def strict_canonical_json_bytes(value: Any) -> bytes:
    """Return CDA-v1 canonical UTF-8 JSON, refusing non-JSON/non-finite data."""
    _validate_canonical_json_value(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_decision_preimage(
    artifact: CanonicalDecisionArtifact,
) -> dict[str, Any]:
    """Construct the exact non-circular CDA-v1 decision hash preimage."""
    return {
        "profile": artifact.hash_profile,
        "format_version": artifact.format_version,
        "request_id": artifact.request_id,
        "decision_ts": artifact.decision_ts,
        "source_contract": artifact.source_contract.model_dump(mode="json"),
        "decision": artifact.decision.model_dump(mode="json", exclude_none=True),
    }


def build_canonical_decision_artifact(
    source: DecideResponse,
    *,
    decision_ts: datetime | str,
) -> CanonicalDecisionArtifact:
    """Build an immutable CDA v1 from an already-normalized pre-Bind response.

    Args:
        source: Authoritative normalized ``DecideResponse`` instance.
        decision_ts: Required timezone-aware finalization timestamp.

    Raises:
        CanonicalDecisionArtifactBuildError: If any v1 boundary is violated.
    """
    normalized = _validated_source_projection(source)
    request_id = normalized["request_id"]
    if normalized["gate_decision"] not in {
        "proceed",
        "hold",
        "block",
        "human_review_required",
    }:
        raise CanonicalDecisionArtifactBuildError(
            CanonicalDecisionArtifactBuildReason.UNRESOLVED_GATE_DECISION
        )
    actionability = normalized["actionability_status"]
    if actionability == "actionable_after_bind":
        raise CanonicalDecisionArtifactBuildError(
            CanonicalDecisionArtifactBuildReason.POST_BIND_ACTIONABILITY_REFUSED
        )
    try:
        _validate_actionability_boundary(
            actionability,
            normalized["requires_bind_before_execution"],
            normalized["human_review_required"],
        )
        validate_gate_business_combination(
            gate_decision=normalized["gate_decision"],
            business_decision=normalized["business_decision"],
            human_review_required=normalized["human_review_required"],
        )
    except ValueError as exc:
        raise CanonicalDecisionArtifactBuildError(
            CanonicalDecisionArtifactBuildReason.ACTIONABILITY_BOUNDARY_INVALID
        ) from exc
    normalized_ts = _normalize_builder_timestamp(decision_ts)
    try:
        decision = _build_projection(normalized)
        provisional = {
            "format_version": CDA_FORMAT_VERSION,
            "hash_profile": CDA_HASH_PROFILE,
            "decision_ts": normalized_ts,
            "request_id": request_id,
            "source_contract": CanonicalDecisionSourceContract(),
            "decision": decision,
        }
        preimage = {
            "profile": CDA_HASH_PROFILE,
            "format_version": CDA_FORMAT_VERSION,
            "request_id": request_id,
            "decision_ts": normalized_ts,
            "source_contract": provisional["source_contract"].model_dump(mode="json"),
            "decision": decision.model_dump(mode="json", exclude_none=True),
        }
        decision_hash = sha256_hex(strict_canonical_json_bytes(preimage))
        return CanonicalDecisionArtifact(
            **provisional,
            decision_hash=decision_hash,
            decision_id=CDA_DECISION_ID_PREFIX + decision_hash,
        )
    except (TypeError, ValueError, ValidationError) as exc:
        if isinstance(exc, CanonicalDecisionArtifactBuildError):
            raise
        raise CanonicalDecisionArtifactBuildError(
            CanonicalDecisionArtifactBuildReason.NON_CANONICAL_JSON_VALUE
        ) from exc


def verify_canonical_decision_artifact(
    artifact: Mapping[str, Any] | CanonicalDecisionArtifact | None,
) -> CanonicalDecisionArtifactVerificationResult:
    """Verify internal CDA-v1 structure and identity without provenance claims."""
    if artifact is None:
        return _verification_failure("ARTIFACT_MISSING")
    try:
        raw = (
            artifact.model_dump(mode="json")
            if isinstance(artifact, CanonicalDecisionArtifact)
            else artifact
        )
        parsed = CanonicalDecisionArtifact.model_validate(raw)
        serialized = strict_canonical_json_bytes(canonical_decision_preimage(parsed))
        computed_hash = sha256_hex(serialized)
    except (TypeError, ValueError, ValidationError):
        return _verification_failure("ARTIFACT_SCHEMA_INVALID")
    expected_id = CDA_DECISION_ID_PREFIX + computed_hash
    reasons: list[str] = []
    if parsed.decision_hash != computed_hash:
        reasons.append("ARTIFACT_HASH_MISMATCH")
    if parsed.decision_id != expected_id:
        reasons.append("ARTIFACT_DECISION_ID_MISMATCH")
    return CanonicalDecisionArtifactVerificationResult(
        is_valid=not reasons,
        reason_codes=tuple(reasons),
        artifact=parsed,
        computed_decision_hash=computed_hash,
        expected_decision_id=expected_id,
    )


def _verification_failure(reason: str) -> CanonicalDecisionArtifactVerificationResult:
    return CanonicalDecisionArtifactVerificationResult(
        is_valid=False,
        reason_codes=(reason,),
        artifact=None,
        computed_decision_hash=None,
        expected_decision_id=None,
    )


def _validated_source_projection(source: DecideResponse) -> dict[str, Any]:
    if not isinstance(source, DecideResponse):
        raise CanonicalDecisionArtifactBuildError(
            CanonicalDecisionArtifactBuildReason.SOURCE_NOT_DECIDE_RESPONSE
        )
    if type(source.request_id) is not str or not source.request_id:
        raise CanonicalDecisionArtifactBuildError(
            CanonicalDecisionArtifactBuildReason.SOURCE_REQUEST_ID_MISSING
        )
    try:
        _validate_canonical_json_value(source.chosen)
        if source.governance_identity is not None:
            _validate_canonical_json_value(source.governance_identity)
        _validate_typed_source_model(
            source.lineage_promotability,
            LineagePromotabilitySummary,
        )
        _validate_typed_source_model(
            source.transition_refusal,
            TransitionRefusal,
        )
    except (TypeError, ValueError) as exc:
        raise CanonicalDecisionArtifactBuildError(
            CanonicalDecisionArtifactBuildReason.NON_CANONICAL_JSON_VALUE
        ) from exc
    try:
        # JSON-mode dumping can coerce non-finite floats under Pydantic's
        # serialization policy.  Inspect the Python projection first so no
        # hash-relevant non-finite or unsupported value can be laundered.
        python_projection = source.model_dump(mode="python", include=_SOURCE_FIELDS)
    except (TypeError, ValueError) as exc:
        raise CanonicalDecisionArtifactBuildError(
            CanonicalDecisionArtifactBuildReason.NON_CANONICAL_JSON_VALUE
        ) from exc
    if any(python_projection[field] is not None for field in POST_BIND_SOURCE_FIELDS):
        raise CanonicalDecisionArtifactBuildError(
            CanonicalDecisionArtifactBuildReason.POST_BIND_SOURCE_REFUSED
        )
    try:
        strict_canonical_json_bytes(python_projection)
    except (TypeError, ValueError) as exc:
        raise CanonicalDecisionArtifactBuildError(
            CanonicalDecisionArtifactBuildReason.NON_CANONICAL_JSON_VALUE
        ) from exc
    try:
        extracted = source.model_dump(mode="json", include=_SOURCE_FIELDS)
        revalidated = DecideResponse.model_validate(extracted)
        normalized = revalidated.model_dump(mode="json", include=_SOURCE_FIELDS)
    except (TypeError, ValueError, ValidationError) as exc:
        raise CanonicalDecisionArtifactBuildError(
            CanonicalDecisionArtifactBuildReason.SOURCE_NOT_NORMALIZED
        ) from exc
    if extracted != normalized:
        raise CanonicalDecisionArtifactBuildError(
            CanonicalDecisionArtifactBuildReason.SOURCE_NOT_NORMALIZED
        )
    return extracted


def _validate_canonical_json_value(value: Any) -> None:
    """Recursively require exact CDA-v1 canonical JSON value families.

    Python containers and objects that ``json.dumps`` or Pydantic might coerce
    are deliberately rejected rather than converted into canonical identity.

    Args:
        value: Candidate value to validate without normalization.

    Raises:
        TypeError: If a value, container, or mapping key is not an exact JSON
            family supported by CDA v1.
        ValueError: If a floating-point value is non-finite.
    """
    value_type = type(value)
    if value is None or value_type is bool or value_type is int or value_type is str:
        return
    if value_type is float:
        if not math.isfinite(value):
            raise ValueError("canonical JSON numbers must be finite")
        return
    if value_type is list:
        for item in value:
            _validate_canonical_json_value(item)
        return
    if value_type is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError("canonical JSON object keys must be strings")
            _validate_canonical_json_value(item)
        return
    raise TypeError(f"unsupported canonical JSON value type: {value_type.__qualname__}")


def _validate_typed_source_model(
    value: BaseModel | None,
    expected_type: type[BaseModel],
) -> None:
    """Validate raw contents of one explicitly allowed typed source model.

    Only the declared top-level Pydantic source model may cross this boundary.
    Its known fields and Pydantic extras are inspected before ``model_dump`` so
    nested Python objects cannot be normalized into a CDA binding.

    Args:
        value: Current raw source-model value, or ``None``.
        expected_type: Exact Pydantic model type allowed for this source field.

    Raises:
        TypeError: If the top-level type is unexpected or any contained value
            is not an exact canonical JSON family.
        ValueError: If a contained floating-point value is non-finite.
    """
    if value is None:
        return
    if type(value) is not expected_type:
        raise TypeError(f"unexpected typed source model: {type(value).__qualname__}")
    for field_name in expected_type.model_fields:
        _validate_canonical_json_value(getattr(value, field_name))
    extras = value.__pydantic_extra__
    if extras is not None:
        _validate_canonical_json_value(extras)


def _normalize_builder_timestamp(value: datetime | str) -> str:
    if not isinstance(value, (datetime, str)) or value == "":
        raise CanonicalDecisionArtifactBuildError(
            CanonicalDecisionArtifactBuildReason.INVALID_TIMESTAMP
        )
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except ValueError as exc:
        raise CanonicalDecisionArtifactBuildError(
            CanonicalDecisionArtifactBuildReason.INVALID_TIMESTAMP
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CanonicalDecisionArtifactBuildError(
            CanonicalDecisionArtifactBuildReason.NAIVE_TIMESTAMP
        )
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _normalize_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _binding_digest(profile: str, value: Any) -> str:
    return sha256_hex(strict_canonical_json_bytes({"profile": profile, "value": value}))


def _build_projection(source: dict[str, Any]) -> CanonicalDecisionProjection:
    governance = source["governance_identity"]
    selected_action_evidence = _selected_action_evidence(source["chosen"])
    policy_snapshot_evidence = _policy_snapshot_evidence(governance)
    common = {
        field: source[field]
        for field in (
            "decision_status",
            "rejection_reason",
            "gate_decision",
            "business_decision",
            "next_action",
            "actionability_status",
            "requires_bind_before_execution",
            "human_review_required",
            "required_evidence",
            "missing_evidence",
            "satisfied_evidence",
            "rationale",
            "refusal_reason",
            "actionability_block_reason",
            "actionability_refusal_type",
        )
    }
    return CanonicalDecisionProjection(
        formation_status="COMPLETE" if governance is not None else "INCOMPLETE",
        chosen_binding=CanonicalDecisionChosenBinding(
            profile=CDA_CHOSEN_BINDING_PROFILE,
            sha256=_binding_digest(CDA_CHOSEN_BINDING_PROFILE, source["chosen"]),
        ),
        selected_action_evidence=selected_action_evidence,
        policy_snapshot_evidence=policy_snapshot_evidence,
        governance_identity_binding=(
            CanonicalDecisionGovernanceIdentityBinding(
                profile=CDA_GOVERNANCE_IDENTITY_BINDING_PROFILE,
                sha256=_binding_digest(
                    CDA_GOVERNANCE_IDENTITY_BINDING_PROFILE, governance
                ),
            )
            if governance is not None
            else None
        ),
        lineage_promotability_binding=_optional_binding(
            CanonicalDecisionLineagePromotabilityBinding,
            CDA_LINEAGE_PROMOTABILITY_BINDING_PROFILE,
            source["lineage_promotability"],
        ),
        transition_refusal_binding=_optional_binding(
            CanonicalDecisionTransitionRefusalBinding,
            CDA_TRANSITION_REFUSAL_BINDING_PROFILE,
            source["transition_refusal"],
        ),
        **common,
    )


def _selected_action_evidence(value: Any) -> CanonicalSelectedActionEvidence | None:
    """Derive selected-action evidence only from a complete candidate payload."""
    if not isinstance(value, dict):
        return None
    try:
        from veritas_os.policy.decision_candidate import (
            hash_decision_candidate,
            normalize_decision_candidate,
            validate_decision_candidate,
        )

        candidate = normalize_decision_candidate(value)
        if not validate_decision_candidate(candidate).promotable:
            return None
    except (TypeError, ValueError):
        return None
    return CanonicalSelectedActionEvidence(
        candidate_hash=hash_decision_candidate(candidate),
        chosen_binding_sha256=_binding_digest(
            CDA_CHOSEN_BINDING_PROFILE, candidate.to_dict()
        ),
    )


def _policy_snapshot_evidence(
    value: Any,
) -> CanonicalPolicySnapshotEvidence | None:
    """Project the existing signed governance identity without inventing trust."""
    if not isinstance(value, dict):
        return None
    try:
        return CanonicalPolicySnapshotEvidence(
            snapshot_id=value["digest"],
            version=value["policy_version"],
            semantic_digest=value["digest"],
            signature_verified=value["signature_verified"],
            signer_id=value["signer_id"],
            verified_at=value["verified_at"],
        )
    except (KeyError, TypeError, ValueError, ValidationError):
        return None


def _optional_binding(model: type[_FrozenModel], profile: str, value: Any) -> Any:
    if value is None:
        return None
    return model(profile=profile, sha256=_binding_digest(profile, value))


def _validate_actionability_boundary(
    status: str,
    requires_bind: bool,
    human_review_required: bool,
) -> None:
    if status not in PRE_BIND_ACTIONABILITY_STATES:
        raise ValueError("actionability state is outside the pre-Bind boundary")
    expected_bind = status in {
        "reviewable_only",
        "bind_required_before_execution",
        "human_review_required",
    }
    if requires_bind is not expected_bind:
        raise ValueError("actionability status contradicts bind requirement")
    if status in {"human_review_required", "formation_transition_refused"}:
        if not human_review_required:
            raise ValueError("actionability status requires human review")
