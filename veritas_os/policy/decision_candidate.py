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


def canonical_decision_candidate_json(
    candidate: DecisionCandidate | dict[str, Any],
) -> str:
    """Serialize ``DecisionCandidate`` with canonical deterministic JSON ordering."""
    return canonical_json_dumps(normalize_decision_candidate(candidate).to_dict())


def hash_decision_candidate(candidate: DecisionCandidate | dict[str, Any]) -> str:
    """Compute SHA-256 over canonical ``DecisionCandidate`` payload."""
    return sha256_of_canonical_json(normalize_decision_candidate(candidate).to_dict())
