"""DecisionCandidate v1 schema and promotion helpers.

This module defines the runtime-neutral pre-``ExecutionIntent`` boundary for
LLM-proposed or agent-proposed actions. It performs schema-level validation
only: it does not extract candidates from live LLM output, call adapters,
append TrustLog entries, or adjudicate bind eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Any
from uuid import uuid4

from veritas_os.policy.bind_artifacts import ExecutionIntent
from veritas_os.security.hash import canonical_json_dumps, sha256_of_canonical_json


class DecisionCandidatePromotionStatus(str, Enum):
    """Promotion status for a validated ``DecisionCandidate``."""

    PROMOTABLE = "PROMOTABLE"
    REFUSED = "REFUSED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


class DecisionCandidateRefusalType(str, Enum):
    """Canonical refusal artifact type for non-promoted candidates."""

    FAIL_CLOSED = "FAIL_CLOSED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    REFUSED = "REFUSED"


class DecisionCandidateRefusalReason(str, Enum):
    """Reason codes emitted by ``DecisionCandidate`` validation."""

    MISSING_REQUIRED_FIELD = "DECISION_CANDIDATE_MISSING_REQUIRED_FIELD"
    AMBIGUOUS = "DECISION_CANDIDATE_AMBIGUOUS"
    AUTHORITY_UNSPECIFIED = "DECISION_CANDIDATE_AUTHORITY_UNSPECIFIED"
    HUMAN_APPROVAL_UNCLEAR = "DECISION_CANDIDATE_HUMAN_APPROVAL_UNCLEAR"
    RISK_INDETERMINATE = "DECISION_CANDIDATE_RISK_INDETERMINATE"
    RATIONALE_ONLY = "DECISION_CANDIDATE_RATIONALE_ONLY"
    PROMOTABLE = "DECISION_CANDIDATE_PROMOTABLE"


HARD_REQUIRED_FIELDS = (
    "action_type",
    "actor_identity",
    "target_system",
    "target_resource",
    "intended_action",
)

INDETERMINATE_RISK_LEVELS = {"", "unknown", "indeterminate"}

STRING_FIELDS = (
    "candidate_id",
    "source_model",
    "source_trace_ref",
    "candidate_type",
    "action_type",
    "actor_identity",
    "target_system",
    "target_resource",
    "intended_action",
    "risk_level",
    "candidate_rationale_ref",
)

LIST_FIELDS = (
    "required_authority",
    "evidence_refs",
    "policy_context_refs",
    "ambiguity_flags",
    "missing_required_fields",
)

HUMAN_APPROVAL_TRUE_VALUES = {"true", "yes", "approved", "required"}
HUMAN_APPROVAL_FALSE_VALUES = {"false", "no", "not_required", "none"}
REGULATED_TRUE_VALUES = {"true", "yes", "high", "regulated"}
REGULATED_FALSE_VALUES = {"false", "no", "none"}


REVIEWER_REDACTION_PROFILE = "reviewer_safe_v1"

REDACTED_REVIEWER_FIELDS = (
    "target_resource",
    "actor_identity",
    "source_model",
    "metadata",
)

OMITTED_REVIEWER_FIELDS = (
    "normalized_candidate_snapshot",
    "validation_result_snapshot",
    "source_trace_ref",
    "raw_natural_language",
    "candidate_rationale_text",
    "prompt",
    "completion",
    "token",
    "credential",
    "secret",
)


@dataclass(frozen=True)
class DecisionCandidate:
    """Runtime-neutral candidate contract before ``ExecutionIntent``.

    The schema captures structured, policy-relevant fields for an action
    proposed by an LLM or agent. Natural-language rationale references may be
    retained for reviewer context, but they are never sufficient to promote a
    candidate when required structured fields are missing.
    """

    candidate_id: str = field(default_factory=lambda: uuid4().hex)
    source_model: str = ""
    source_trace_ref: str | None = None
    candidate_type: str = "execution_intent_candidate"
    action_type: str = ""
    actor_identity: str = ""
    target_system: str = ""
    target_resource: str = ""
    intended_action: str = ""
    required_authority: list[str] = field(default_factory=list)
    required_human_approval: bool | None = None
    risk_level: str = "unknown"
    regulated_or_high_impact: bool = False
    evidence_refs: list[str] = field(default_factory=list)
    policy_context_refs: list[str] = field(default_factory=list)
    ambiguity_flags: list[str] = field(default_factory=list)
    missing_required_fields: list[str] = field(default_factory=list)
    candidate_rationale_ref: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "candidate_id": self.candidate_id,
            "source_model": self.source_model,
            "source_trace_ref": self.source_trace_ref,
            "candidate_type": self.candidate_type,
            "action_type": self.action_type,
            "actor_identity": self.actor_identity,
            "target_system": self.target_system,
            "target_resource": self.target_resource,
            "intended_action": self.intended_action,
            "required_authority": list(self.required_authority),
            "required_human_approval": self.required_human_approval,
            "risk_level": self.risk_level,
            "regulated_or_high_impact": self.regulated_or_high_impact,
            "evidence_refs": list(self.evidence_refs),
            "policy_context_refs": list(self.policy_context_refs),
            "ambiguity_flags": list(self.ambiguity_flags),
            "missing_required_fields": list(self.missing_required_fields),
            "candidate_rationale_ref": self.candidate_rationale_ref,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class DecisionCandidateValidationResult:
    """Structured result returned by ``validate_decision_candidate``."""

    promotion_status: DecisionCandidatePromotionStatus
    promotable: bool
    requires_human_review: bool
    fail_closed: bool
    reason_codes: list[str] = field(default_factory=list)
    missing_required_fields: list[str] = field(default_factory=list)
    ambiguity_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "promotion_status": self.promotion_status.value,
            "promotable": self.promotable,
            "requires_human_review": self.requires_human_review,
            "fail_closed": self.fail_closed,
            "reason_codes": list(self.reason_codes),
            "missing_required_fields": list(self.missing_required_fields),
            "ambiguity_flags": list(self.ambiguity_flags),
        }


@dataclass(frozen=True)
class DecisionCandidatePromotionResult:
    """Canonical non-throwing promotion or refusal result."""

    promoted: bool
    execution_intent: ExecutionIntent | None
    validation_result: DecisionCandidateValidationResult
    normalized_candidate: DecisionCandidate
    refusal_reason_codes: list[str] = field(default_factory=list)
    requires_human_review: bool = False
    fail_closed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        execution_intent = (
            self.execution_intent.to_dict()
            if self.execution_intent is not None
            else None
        )
        return {
            "promoted": self.promoted,
            "execution_intent": execution_intent,
            "validation_result": self.validation_result.to_dict(),
            "normalized_candidate": self.normalized_candidate.to_dict(),
            "refusal_reason_codes": list(self.refusal_reason_codes),
            "requires_human_review": self.requires_human_review,
            "fail_closed": self.fail_closed,
        }


@dataclass(frozen=True)
class DecisionCandidateRefusalArtifact:
    """Canonical pre-``ExecutionIntent`` evidence for refused candidates.

    The artifact records why a normalized ``DecisionCandidate`` did not become
    an ``ExecutionIntent``. It is review evidence only: constructing it does
    not perform bind adjudication, append TrustLog entries, call adapters, or
    imply that any execution attempt occurred.
    """

    candidate_id: str
    candidate_hash: str
    source_model: str
    source_trace_ref: str | None
    promotion_status: str
    refusal_reason_codes: list[str]
    missing_required_fields: list[str]
    ambiguity_flags: list[str]
    requires_human_review: bool
    fail_closed: bool
    normalized_candidate_snapshot: dict[str, Any]
    validation_result_snapshot: dict[str, Any]
    refusal_id: str = field(default_factory=lambda: uuid4().hex)
    refusal_type: str = DecisionCandidateRefusalType.REFUSED.value
    created_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Canonicalize refusal type from fail-closed and review state."""
        refusal_type = self.refusal_type
        if self.fail_closed:
            refusal_type = DecisionCandidateRefusalType.FAIL_CLOSED.value
        elif self.requires_human_review:
            refusal_type = DecisionCandidateRefusalType.HUMAN_REVIEW_REQUIRED.value
        object.__setattr__(self, "refusal_type", refusal_type)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "refusal_id": self.refusal_id,
            "candidate_id": self.candidate_id,
            "candidate_hash": self.candidate_hash,
            "source_model": self.source_model,
            "source_trace_ref": self.source_trace_ref,
            "promotion_status": self.promotion_status,
            "refusal_reason_codes": list(self.refusal_reason_codes),
            "missing_required_fields": list(self.missing_required_fields),
            "ambiguity_flags": list(self.ambiguity_flags),
            "requires_human_review": self.requires_human_review,
            "fail_closed": self.fail_closed,
            "normalized_candidate_snapshot": dict(self.normalized_candidate_snapshot),
            "validation_result_snapshot": dict(self.validation_result_snapshot),
            "refusal_type": self.refusal_type,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class DecisionCandidateRefusalReviewerExport:
    """Redacted reviewer-facing view of a refusal artifact.

    This export preserves structured refusal signals and hashes while omitting
    raw candidate snapshots, validation snapshots, natural-language content,
    prompts, tokens, credentials, and sensitive metadata values. Building it is
    side-effect free and does not imply execution was attempted.
    """

    refusal_id: str
    candidate_id: str
    candidate_hash: str
    artifact_hash: str
    refusal_type: str
    promotion_status: str
    refusal_reason_codes: list[str]
    missing_required_fields: list[str]
    ambiguity_flags: list[str]
    requires_human_review: bool
    fail_closed: bool
    safe_summary: str
    export_id: str = field(default_factory=lambda: uuid4().hex)
    redaction_profile: str = REVIEWER_REDACTION_PROFILE
    redacted_fields: list[str] = field(
        default_factory=lambda: list(REDACTED_REVIEWER_FIELDS)
    )
    omitted_fields: list[str] = field(
        default_factory=lambda: list(OMITTED_REVIEWER_FIELDS)
    )
    created_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable redacted reviewer export."""
        return {
            "export_id": self.export_id,
            "refusal_id": self.refusal_id,
            "candidate_id": self.candidate_id,
            "candidate_hash": self.candidate_hash,
            "artifact_hash": self.artifact_hash,
            "refusal_type": self.refusal_type,
            "promotion_status": self.promotion_status,
            "refusal_reason_codes": list(self.refusal_reason_codes),
            "missing_required_fields": list(self.missing_required_fields),
            "ambiguity_flags": list(self.ambiguity_flags),
            "requires_human_review": self.requires_human_review,
            "fail_closed": self.fail_closed,
            "safe_summary": self.safe_summary,
            "redaction_profile": self.redaction_profile,
            "redacted_fields": list(self.redacted_fields),
            "omitted_fields": list(self.omitted_fields),
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


def _strip_string(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_values = value
    else:
        raw_values = [value]

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        item = str(raw_value).strip()
        if not item or item in seen:
            continue
        normalized.append(item)
        seen.add(item)
    return normalized


def _normalize_metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    return {"raw": value}


def _normalize_required_human_approval(value: Any) -> bool | None:
    if isinstance(value, bool) or value is None:
        return value
    normalized = str(value).strip().lower()
    if normalized in HUMAN_APPROVAL_TRUE_VALUES:
        return True
    if normalized in HUMAN_APPROVAL_FALSE_VALUES:
        return False
    return None


def _normalize_regulated_or_high_impact(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in REGULATED_TRUE_VALUES:
        return True
    if normalized in REGULATED_FALSE_VALUES:
        return False
    return False


def normalize_decision_candidate(
    payload: DecisionCandidate | dict[str, Any],
) -> DecisionCandidate:
    """Normalize a raw ``DecisionCandidate`` payload without promoting it.

    The normalizer accepts either the dataclass contract or an untrusted raw
    dictionary, trims scalar string fields, canonicalizes list-like fields, and
    converts unclear approval values to conservative review-oriented defaults.
    It performs no validation, promotion, TrustLog writes, bind adjudication, or
    adapter calls.
    """
    if isinstance(payload, DecisionCandidate):
        raw_payload = payload.to_dict()
    elif isinstance(payload, dict):
        raw_payload = dict(payload)
    else:
        raise TypeError("payload must be a DecisionCandidate or dict")

    candidate_field_names = {field.name for field in fields(DecisionCandidate)}
    normalized_payload = {
        key: value for key, value in raw_payload.items() if key in candidate_field_names
    }

    for field_name in STRING_FIELDS:
        if field_name in normalized_payload:
            normalized_payload[field_name] = _strip_string(
                normalized_payload[field_name]
            )

    for field_name in LIST_FIELDS:
        normalized_payload[field_name] = _normalize_string_list(
            normalized_payload.get(field_name)
        )

    normalized_payload["metadata"] = _normalize_metadata(
        normalized_payload.get("metadata")
    )
    normalized_payload["required_human_approval"] = _normalize_required_human_approval(
        normalized_payload.get("required_human_approval")
    )
    normalized_payload["regulated_or_high_impact"] = (
        _normalize_regulated_or_high_impact(
            normalized_payload.get("regulated_or_high_impact")
        )
    )

    risk_level = str(normalized_payload.get("risk_level") or "").strip().lower()
    normalized_payload["risk_level"] = risk_level or "unknown"

    return DecisionCandidate(**normalized_payload)


def _is_blank(value: str | None) -> bool:
    return not str(value or "").strip()


def _append_reason(
    reason_codes: list[str], reason: DecisionCandidateRefusalReason
) -> None:
    if reason.value not in reason_codes:
        reason_codes.append(reason.value)


def validate_decision_candidate(
    candidate: DecisionCandidate | dict[str, Any],
) -> DecisionCandidateValidationResult:
    """Validate whether a candidate is eligible for schema-level promotion.

    Args:
        candidate: Structured decision candidate to validate.

    Returns:
        A structured validation result. Incomplete or ambiguous candidates are
        never promotable; ambiguity and unclear human approval require human
        review, while hard missing fields fail closed.
    """
    candidate = normalize_decision_candidate(candidate)

    missing_required_fields = list(candidate.missing_required_fields)
    for field_name in HARD_REQUIRED_FIELDS:
        value = getattr(candidate, field_name)
        if _is_blank(value) and field_name not in missing_required_fields:
            missing_required_fields.append(field_name)

    reason_codes: list[str] = []
    requires_human_review = False
    fail_closed = False

    if missing_required_fields:
        fail_closed = True
        _append_reason(
            reason_codes, DecisionCandidateRefusalReason.MISSING_REQUIRED_FIELD
        )

    if candidate.ambiguity_flags:
        requires_human_review = True
        _append_reason(reason_codes, DecisionCandidateRefusalReason.AMBIGUOUS)

    if not candidate.required_authority:
        fail_closed = True
        _append_reason(
            reason_codes, DecisionCandidateRefusalReason.AUTHORITY_UNSPECIFIED
        )

    if candidate.required_human_approval is None:
        requires_human_review = True
        _append_reason(
            reason_codes, DecisionCandidateRefusalReason.HUMAN_APPROVAL_UNCLEAR
        )

    risk_level = str(candidate.risk_level or "").strip().lower()
    if candidate.regulated_or_high_impact and risk_level in INDETERMINATE_RISK_LEVELS:
        requires_human_review = True
        _append_reason(reason_codes, DecisionCandidateRefusalReason.RISK_INDETERMINATE)

    if candidate.candidate_rationale_ref and missing_required_fields:
        fail_closed = True
        _append_reason(reason_codes, DecisionCandidateRefusalReason.RATIONALE_ONLY)

    promotable = not reason_codes
    if promotable:
        _append_reason(reason_codes, DecisionCandidateRefusalReason.PROMOTABLE)
        promotion_status = DecisionCandidatePromotionStatus.PROMOTABLE
    elif requires_human_review and not fail_closed:
        promotion_status = DecisionCandidatePromotionStatus.HUMAN_REVIEW_REQUIRED
    else:
        promotion_status = DecisionCandidatePromotionStatus.REFUSED

    return DecisionCandidateValidationResult(
        promotion_status=promotion_status,
        promotable=promotable,
        requires_human_review=requires_human_review,
        fail_closed=fail_closed,
        reason_codes=reason_codes,
        missing_required_fields=missing_required_fields,
        ambiguity_flags=list(candidate.ambiguity_flags),
    )


def try_promote_decision_candidate_to_execution_intent(
    candidate: DecisionCandidate | dict[str, Any],
    *,
    decision_id: str = "",
    request_id: str = "",
    policy_snapshot_id: str = "",
    decision_hash: str = "",
    decision_ts: str = "",
    ttl_seconds: int | None = None,
    expected_state_fingerprint: str | None = None,
    approval_context: dict[str, Any] | None = None,
    policy_lineage: dict[str, Any] | None = None,
) -> DecisionCandidatePromotionResult:
    """Return a non-throwing promotion or structured refusal result.

    This helper is schema-first and runtime-neutral. It normalizes and validates
    the candidate before constructing an ``ExecutionIntent``; it does not append
    TrustLog entries, perform bind adjudication, or call adapters.
    """
    normalized_candidate = normalize_decision_candidate(candidate)
    validation_result = validate_decision_candidate(normalized_candidate)

    if not validation_result.promotable:
        return DecisionCandidatePromotionResult(
            promoted=False,
            execution_intent=None,
            validation_result=validation_result,
            normalized_candidate=normalized_candidate,
            refusal_reason_codes=list(validation_result.reason_codes),
            requires_human_review=validation_result.requires_human_review,
            fail_closed=validation_result.fail_closed,
        )

    intent = ExecutionIntent(
        decision_id=decision_id,
        request_id=request_id,
        policy_snapshot_id=policy_snapshot_id,
        actor_identity=normalized_candidate.actor_identity,
        target_system=normalized_candidate.target_system,
        target_resource=normalized_candidate.target_resource,
        intended_action=normalized_candidate.intended_action,
        evidence_refs=list(normalized_candidate.evidence_refs),
        decision_hash=decision_hash,
        decision_ts=decision_ts,
        ttl_seconds=ttl_seconds,
        expected_state_fingerprint=expected_state_fingerprint,
        approval_context=approval_context,
        policy_lineage=policy_lineage,
    )
    return DecisionCandidatePromotionResult(
        promoted=True,
        execution_intent=intent,
        validation_result=validation_result,
        normalized_candidate=normalized_candidate,
        refusal_reason_codes=[],
        requires_human_review=False,
        fail_closed=False,
    )


def promote_decision_candidate_to_execution_intent(
    candidate: DecisionCandidate | dict[str, Any],
    *,
    decision_id: str = "",
    request_id: str = "",
    policy_snapshot_id: str = "",
    decision_hash: str = "",
    decision_ts: str = "",
    ttl_seconds: int | None = None,
    expected_state_fingerprint: str | None = None,
    approval_context: dict[str, Any] | None = None,
    policy_lineage: dict[str, Any] | None = None,
) -> ExecutionIntent:
    """Promote a valid candidate into an ``ExecutionIntent``.

    The helper validates first and raises ``ValueError`` when the candidate is
    not promotable. It performs no TrustLog writes, bind adjudication, adapter
    calls, or live authority-source validation.
    """
    result = try_promote_decision_candidate_to_execution_intent(
        candidate,
        decision_id=decision_id,
        request_id=request_id,
        policy_snapshot_id=policy_snapshot_id,
        decision_hash=decision_hash,
        decision_ts=decision_ts,
        ttl_seconds=ttl_seconds,
        expected_state_fingerprint=expected_state_fingerprint,
        approval_context=approval_context,
        policy_lineage=policy_lineage,
    )
    if result.execution_intent is None:
        reason_codes = ",".join(result.refusal_reason_codes)
        raise ValueError(f"DecisionCandidate is not promotable: {reason_codes}")
    return result.execution_intent


def build_decision_candidate_refusal_artifact(
    result: DecisionCandidatePromotionResult,
    *,
    created_at: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> DecisionCandidateRefusalArtifact:
    """Build a canonical refusal artifact from a non-promoted result.

    Raises:
        ValueError: If ``result`` represents a promoted candidate.
    """
    if result.promoted:
        raise ValueError("Promoted candidates cannot produce refusal artifacts")

    normalized_candidate = result.normalized_candidate
    validation_result = result.validation_result
    return DecisionCandidateRefusalArtifact(
        candidate_id=normalized_candidate.candidate_id,
        candidate_hash=hash_decision_candidate(normalized_candidate),
        source_model=normalized_candidate.source_model,
        source_trace_ref=normalized_candidate.source_trace_ref,
        promotion_status=validation_result.promotion_status.value,
        refusal_reason_codes=list(result.refusal_reason_codes),
        missing_required_fields=list(validation_result.missing_required_fields),
        ambiguity_flags=list(validation_result.ambiguity_flags),
        requires_human_review=result.requires_human_review,
        fail_closed=result.fail_closed,
        normalized_candidate_snapshot=normalized_candidate.to_dict(),
        validation_result_snapshot=validation_result.to_dict(),
        created_at=created_at,
        metadata=dict(metadata or {}),
    )


def try_build_decision_candidate_refusal_artifact(
    candidate: DecisionCandidate | dict[str, Any],
    *,
    created_at: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> DecisionCandidateRefusalArtifact | None:
    """Return a refusal artifact for invalid candidates, or ``None`` if promotable."""
    result = try_promote_decision_candidate_to_execution_intent(candidate)
    if result.promoted:
        return None
    return build_decision_candidate_refusal_artifact(
        result,
        created_at=created_at,
        metadata=metadata,
    )


def _build_refusal_reviewer_safe_summary(
    artifact: DecisionCandidateRefusalArtifact,
) -> str:
    """Build a deterministic generic reviewer summary without raw identifiers."""
    if artifact.missing_required_fields:
        return (
            "DecisionCandidate was not promoted to ExecutionIntent because "
            "required structured fields were missing."
        )
    if artifact.fail_closed:
        return (
            "DecisionCandidate was not promoted to ExecutionIntent because "
            "structured validation failed closed."
        )
    if artifact.ambiguity_flags or artifact.requires_human_review:
        return (
            "DecisionCandidate requires human review because ambiguity flags "
            "were present."
        )
    return (
        "DecisionCandidate was not promoted to ExecutionIntent because "
        "structured validation did not permit promotion."
    )


def build_decision_candidate_refusal_reviewer_export(
    artifact: DecisionCandidateRefusalArtifact,
    *,
    created_at: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> DecisionCandidateRefusalReviewerExport:
    """Build a redacted reviewer-facing export for a refusal artifact.

    The export includes structured refusal reason fields and hashes only. It
    intentionally omits raw candidate snapshots, validation snapshots, source
    traces, natural-language rationale, prompts, tokens, credentials, and raw
    artifact metadata values.
    """
    return DecisionCandidateRefusalReviewerExport(
        refusal_id=artifact.refusal_id,
        candidate_id=artifact.candidate_id,
        candidate_hash=artifact.candidate_hash,
        artifact_hash=hash_decision_candidate_refusal_artifact(artifact),
        refusal_type=artifact.refusal_type,
        promotion_status=artifact.promotion_status,
        refusal_reason_codes=list(artifact.refusal_reason_codes),
        missing_required_fields=list(artifact.missing_required_fields),
        ambiguity_flags=list(artifact.ambiguity_flags),
        requires_human_review=artifact.requires_human_review,
        fail_closed=artifact.fail_closed,
        safe_summary=_build_refusal_reviewer_safe_summary(artifact),
        created_at=created_at,
        metadata=dict(metadata or {}),
    )


def canonical_decision_candidate_json(
    candidate: DecisionCandidate | dict[str, Any],
) -> str:
    """Serialize ``DecisionCandidate`` with canonical deterministic JSON ordering."""
    return canonical_json_dumps(normalize_decision_candidate(candidate).to_dict())


def hash_decision_candidate(candidate: DecisionCandidate | dict[str, Any]) -> str:
    """Compute SHA-256 over canonical ``DecisionCandidate`` payload."""
    return sha256_of_canonical_json(normalize_decision_candidate(candidate).to_dict())


def canonical_decision_candidate_refusal_artifact_json(
    artifact: DecisionCandidateRefusalArtifact,
) -> str:
    """Serialize refusal artifact with canonical deterministic JSON ordering."""
    return canonical_json_dumps(artifact.to_dict())


def hash_decision_candidate_refusal_artifact(
    artifact: DecisionCandidateRefusalArtifact,
) -> str:
    """Compute SHA-256 over a canonical refusal artifact payload."""
    return sha256_of_canonical_json(artifact.to_dict())


def canonical_decision_candidate_refusal_reviewer_export_json(
    export: DecisionCandidateRefusalReviewerExport,
) -> str:
    """Serialize reviewer refusal export with deterministic JSON ordering."""
    return canonical_json_dumps(export.to_dict())


def hash_decision_candidate_refusal_reviewer_export(
    export: DecisionCandidateRefusalReviewerExport,
) -> str:
    """Compute SHA-256 over a canonical reviewer refusal export payload."""
    return sha256_of_canonical_json(export.to_dict())
