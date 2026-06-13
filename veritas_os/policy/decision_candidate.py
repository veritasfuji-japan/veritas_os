"""DecisionCandidate v1 schema and promotion helpers.

This module defines the runtime-neutral pre-``ExecutionIntent`` boundary for
LLM-proposed or agent-proposed actions. It performs schema-level validation
only: it does not extract candidates from live LLM output, call adapters,
append TrustLog entries, or adjudicate bind eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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


def _is_blank(value: str | None) -> bool:
    return not str(value or "").strip()


def _append_reason(reason_codes: list[str], reason: DecisionCandidateRefusalReason) -> None:
    if reason.value not in reason_codes:
        reason_codes.append(reason.value)


def validate_decision_candidate(
    candidate: DecisionCandidate,
) -> DecisionCandidateValidationResult:
    """Validate whether a candidate is eligible for schema-level promotion.

    Args:
        candidate: Structured decision candidate to validate.

    Returns:
        A structured validation result. Incomplete or ambiguous candidates are
        never promotable; ambiguity and unclear human approval require human
        review, while hard missing fields fail closed.
    """
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
        _append_reason(reason_codes, DecisionCandidateRefusalReason.MISSING_REQUIRED_FIELD)

    if candidate.ambiguity_flags:
        requires_human_review = True
        _append_reason(reason_codes, DecisionCandidateRefusalReason.AMBIGUOUS)

    if not candidate.required_authority:
        fail_closed = True
        _append_reason(reason_codes, DecisionCandidateRefusalReason.AUTHORITY_UNSPECIFIED)

    if candidate.required_human_approval is None:
        requires_human_review = True
        _append_reason(reason_codes, DecisionCandidateRefusalReason.HUMAN_APPROVAL_UNCLEAR)

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


def promote_decision_candidate_to_execution_intent(
    candidate: DecisionCandidate,
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
    validation_result = validate_decision_candidate(candidate)
    if not validation_result.promotable:
        reason_codes = ",".join(validation_result.reason_codes)
        raise ValueError(f"DecisionCandidate is not promotable: {reason_codes}")

    return ExecutionIntent(
        decision_id=decision_id,
        request_id=request_id,
        policy_snapshot_id=policy_snapshot_id,
        actor_identity=candidate.actor_identity,
        target_system=candidate.target_system,
        target_resource=candidate.target_resource,
        intended_action=candidate.intended_action,
        evidence_refs=list(candidate.evidence_refs),
        decision_hash=decision_hash,
        decision_ts=decision_ts,
        ttl_seconds=ttl_seconds,
        expected_state_fingerprint=expected_state_fingerprint,
        approval_context=approval_context,
        policy_lineage=policy_lineage,
    )


def canonical_decision_candidate_json(candidate: DecisionCandidate) -> str:
    """Serialize ``DecisionCandidate`` with canonical deterministic JSON ordering."""
    return canonical_json_dumps(candidate.to_dict())


def hash_decision_candidate(candidate: DecisionCandidate) -> str:
    """Compute SHA-256 over canonical ``DecisionCandidate`` payload."""
    return sha256_of_canonical_json(candidate.to_dict())
