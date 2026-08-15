"""Fail-closed CanonicalDecisionHandoff v1 validation boundary.

This module performs deterministic, local validation only.  In particular it
does not promote a candidate, establish execution authority, or invoke Bind.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from veritas_os.security.hash import sha256_of_canonical_json

ASSERTION_VALUE_DIGEST_PROFILE = "veritas.canonical-handoff.assertion-value/v1"
VALIDATION_VERSION = "canonical-decision-handoff-validator/v1"
HUMAN_APPROVAL_EXACT_OPERATION_CLAIM = "HUMAN_APPROVAL_BINDS_EXACT_OPERATION"
AUTHORITY_SATISFIES_REQUIREMENT_CLAIM = (
    "AUTHORITY_EVIDENCE_SATISFIES_REQUIREMENT"
)
FORBIDDEN_READY_PROVENANCE_CLASSES = frozenset(
    {"UNAVAILABLE", "UNVERIFIED_STRUCTURED_INPUT"}
)
CANONICAL_PROVENANCE_CLASSES = frozenset(
    {
        "VERIFIED_RUNTIME_EVIDENCE",
        "VERIFIED_POLICY_ARTIFACT",
        "VERIFIED_AUTHORITY_EVIDENCE",
        "VERIFIED_HUMAN_APPROVAL",
        "VERIFIED_LIVE_STATE",
        "EXPLICIT_STRUCTURED_INPUT",
        "UNVERIFIED_STRUCTURED_INPUT",
        "DERIVED_CANONICALLY",
        "UNAVAILABLE",
    }
)
CANONICAL_VERIFICATION_STATUSES = frozenset(
    {"VERIFIED", "UNVERIFIED", "UNAVAILABLE"}
)


class CanonicalDecisionHandoffStatus(str, Enum):
    """Security states produced by the v1 validator."""

    INCOMPLETE = "INCOMPLETE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INVALID = "INVALID"
    STRUCTURALLY_REFUSED = "STRUCTURALLY_REFUSED"
    READY_FOR_GUARDED_PROMOTION = "READY_FOR_GUARDED_PROMOTION"


class CanonicalDecisionHandoffReasonCode(str, Enum):
    """Canonical fail-closed reason vocabulary."""

    HANDOFF_MISSING_CANONICAL_DECISION_ID = "HANDOFF_MISSING_CANONICAL_DECISION_ID"
    HANDOFF_MISSING_CANONICAL_DECISION_HASH = "HANDOFF_MISSING_CANONICAL_DECISION_HASH"
    HANDOFF_MISSING_DECISION_TIMESTAMP = "HANDOFF_MISSING_DECISION_TIMESTAMP"
    HANDOFF_TRUSTLOG_UNVERIFIED = "HANDOFF_TRUSTLOG_UNVERIFIED"
    HANDOFF_REPLAY_UNVERIFIED = "HANDOFF_REPLAY_UNVERIFIED"
    HANDOFF_REQUEST_LINEAGE_MISMATCH = "HANDOFF_REQUEST_LINEAGE_MISMATCH"
    HANDOFF_CANDIDATE_HASH_MISMATCH = "HANDOFF_CANDIDATE_HASH_MISMATCH"
    HANDOFF_TARGET_CONTEXT_MISMATCH = "HANDOFF_TARGET_CONTEXT_MISMATCH"
    HANDOFF_LINEAGE_NON_PROMOTABLE = "HANDOFF_LINEAGE_NON_PROMOTABLE"
    HANDOFF_TARGET_UNSPECIFIED = "HANDOFF_TARGET_UNSPECIFIED"
    HANDOFF_ACTION_UNSPECIFIED = "HANDOFF_ACTION_UNSPECIFIED"
    HANDOFF_ACTOR_UNSPECIFIED = "HANDOFF_ACTOR_UNSPECIFIED"
    HANDOFF_AUTHORITY_REQUIREMENT_UNRESOLVED = "HANDOFF_AUTHORITY_REQUIREMENT_UNRESOLVED"
    HANDOFF_AUTHORITY_EVIDENCE_MISSING = "HANDOFF_AUTHORITY_EVIDENCE_MISSING"
    HANDOFF_AUTHORITY_EVIDENCE_INVALID = "HANDOFF_AUTHORITY_EVIDENCE_INVALID"
    HANDOFF_AUTHORITY_EVIDENCE_EXPIRED = "HANDOFF_AUTHORITY_EVIDENCE_EXPIRED"
    HANDOFF_APPROVAL_REQUIREMENT_UNRESOLVED = "HANDOFF_APPROVAL_REQUIREMENT_UNRESOLVED"
    HANDOFF_APPROVAL_EVIDENCE_MISSING = "HANDOFF_APPROVAL_EVIDENCE_MISSING"
    HANDOFF_APPROVAL_EVIDENCE_INVALID = "HANDOFF_APPROVAL_EVIDENCE_INVALID"
    HANDOFF_APPROVAL_EVIDENCE_EXPIRED = "HANDOFF_APPROVAL_EVIDENCE_EXPIRED"
    HANDOFF_POLICY_LINEAGE_MISSING = "HANDOFF_POLICY_LINEAGE_MISSING"
    HANDOFF_POLICY_LINEAGE_STALE = "HANDOFF_POLICY_LINEAGE_STALE"
    HANDOFF_EXPECTED_STATE_MISSING = "HANDOFF_EXPECTED_STATE_MISSING"
    HANDOFF_EXPECTED_STATE_STALE = "HANDOFF_EXPECTED_STATE_STALE"
    HANDOFF_AMBIGUOUS_ACTION = "HANDOFF_AMBIGUOUS_ACTION"
    HANDOFF_SOURCE_ARTIFACT_MISMATCH = "HANDOFF_SOURCE_ARTIFACT_MISMATCH"
    HANDOFF_SCHEMA_INVALID = "HANDOFF_SCHEMA_INVALID"
    HANDOFF_PROVENANCE_UNVERIFIED = "HANDOFF_PROVENANCE_UNVERIFIED"
    HANDOFF_PROVENANCE_MISMATCH = "HANDOFF_PROVENANCE_MISMATCH"
    HANDOFF_EXPIRED = "HANDOFF_EXPIRED"


@dataclass(frozen=True)
class TrustedValueAssertion:
    """An independently trusted assertion bound to one exact JSON value."""

    field_path: str
    value_digest: str
    source_artifact_ref: str | None
    source_hash: str | None
    verification_mechanism: str
    verified_at: datetime
    claims: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateHashBindingAssertion:
    """Trusted binding of an opaque candidate hash to an exact candidate."""

    candidate_value_digest: str
    asserted_candidate_hash: str
    candidate_hash_profile: str
    source_artifact_ref: str | None
    source_hash: str | None
    verification_mechanism: str
    verified_at: datetime
    claim: str = "CANDIDATE_HASH_BINDS_CANDIDATE"


@dataclass(frozen=True)
class AuthorityEvidenceRequirementBindingAssertion:
    """Trusted cross-binding of exact Authority Evidence and requirement."""

    authority_requirement_value_digest: str
    authority_evidence_value_digest: str
    source_artifact_ref: str | None
    source_hash: str | None
    verification_mechanism: str
    verified_at: datetime
    claim: str = AUTHORITY_SATISFIES_REQUIREMENT_CLAIM


@dataclass(frozen=True)
class CanonicalDecisionHandoffValidationContext:
    """Assertions supplied independently of the untrusted handoff."""

    value_assertions: tuple[TrustedValueAssertion, ...] = ()
    candidate_hash_binding: CandidateHashBindingAssertion | None = None
    authority_requirement_binding: (
        AuthorityEvidenceRequirementBindingAssertion | None
    ) = None


@dataclass(frozen=True)
class CanonicalDecisionHandoffValidationResult:
    """Immutable report from validation; it confers no execution authority."""

    status: CanonicalDecisionHandoffStatus
    reason_codes: tuple[CanonicalDecisionHandoffReasonCode, ...]
    structure_valid: bool
    declared_status: str | None
    declared_status_matches: bool
    declared_reason_codes: tuple[str, ...]
    declared_reason_codes_match: bool
    verified_provenance_paths: tuple[str, ...] = ()
    validation_version: str = VALIDATION_VERSION
    ready_for_guarded_promotion: bool = field(init=False)
    fail_closed: bool = field(init=False)
    requires_review: bool = field(init=False)

    def __post_init__(self) -> None:
        ready = self.status is CanonicalDecisionHandoffStatus.READY_FOR_GUARDED_PROMOTION
        object.__setattr__(self, "ready_for_guarded_promotion", ready)
        object.__setattr__(self, "fail_closed", not ready)
        object.__setattr__(
            self,
            "requires_review",
            self.status is CanonicalDecisionHandoffStatus.REVIEW_REQUIRED,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible report."""
        result = asdict(self)
        result["status"] = self.status.value
        result["reason_codes"] = [reason.value for reason in self.reason_codes]
        result["declared_reason_codes"] = list(self.declared_reason_codes)
        result["verified_provenance_paths"] = list(self.verified_provenance_paths)
        return result


def canonical_handoff_assertion_value_digest(value: Any) -> str:
    """Digest an exact JSON value using the local assertion binding profile.

    This digest is not an artifact hash or domain-level candidate/decision hash.
    """
    return sha256_of_canonical_json(
        {"profile": ASSERTION_VALUE_DIGEST_PROFILE, "value": value}
    )


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _resolve(payload: Mapping[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = payload
    for component in path.split("."):
        if not isinstance(current, Mapping) or component not in current:
            return False, None
        current = current[component]
    return True, current


def _result(
    payload: Any,
    status: CanonicalDecisionHandoffStatus,
    reasons: tuple[CanonicalDecisionHandoffReasonCode, ...],
    *,
    structure_valid: bool = True,
    verified: tuple[str, ...] = (),
) -> CanonicalDecisionHandoffValidationResult:
    declared_status = payload.get("handoff_status") if isinstance(payload, Mapping) else None
    raw_reasons = payload.get("refusal_reason_codes", []) if isinstance(payload, Mapping) else []
    declared_reasons = tuple(raw_reasons) if isinstance(raw_reasons, list) else ()
    computed = tuple(reason.value for reason in reasons)
    return CanonicalDecisionHandoffValidationResult(
        status=status,
        reason_codes=reasons,
        structure_valid=structure_valid,
        declared_status=declared_status if isinstance(declared_status, str) else None,
        declared_status_matches=declared_status == status.value,
        declared_reason_codes=declared_reasons,
        declared_reason_codes_match=declared_reasons == computed,
        verified_provenance_paths=verified,
    )


def validate_canonical_decision_handoff(
    handoff: Any,
    trusted_context: CanonicalDecisionHandoffValidationContext,
    evaluated_at: datetime,
) -> CanonicalDecisionHandoffValidationResult:
    """Validate an untrusted CanonicalDecisionHandoff without side effects.

    Args:
        handoff: Untrusted JSON-like handoff value.
        trusted_context: Assertions obtained independently from the handoff.
        evaluated_at: Deterministic, timezone-aware evaluation time.

    Returns:
        A fail-closed immutable validation report.
    """
    schema_reason = (CanonicalDecisionHandoffReasonCode.HANDOFF_SCHEMA_INVALID,)
    if not isinstance(evaluated_at, datetime) or evaluated_at.tzinfo is None:
        return _result(handoff, CanonicalDecisionHandoffStatus.INVALID, schema_reason, structure_valid=False)
    if not isinstance(trusted_context, CanonicalDecisionHandoffValidationContext):
        return _result(handoff, CanonicalDecisionHandoffStatus.INVALID, schema_reason, structure_valid=False)
    if not isinstance(handoff, Mapping) or handoff.get("format_version") != (
        "canonical-decision-handoff/v1"
    ) or not _nonempty(handoff.get("handoff_id")):
        return _result(
            handoff,
            CanonicalDecisionHandoffStatus.INVALID,
            schema_reason,
            structure_valid=False,
        )
    required_objects = (
        "source_decision", "candidate", "decision_lineage", "trustlog_lineage",
        "replay_lineage", "authority_requirement", "human_approval_requirement",
        "target_context",
    )
    if not isinstance(handoff, Mapping) or any(
        not isinstance(handoff.get(key), Mapping) for key in required_objects
    ) or not isinstance(handoff.get("provenance"), list):
        return _result(handoff, CanonicalDecisionHandoffStatus.INVALID, schema_reason, structure_valid=False)
    nullable_objects = (
        "policy_lineage",
        "authority_evidence",
        "human_approval_evidence",
        "expected_state",
    )
    if any(
        handoff.get(key) is not None
        and not isinstance(handoff.get(key), Mapping)
        for key in nullable_objects
    ):
        return _result(
            handoff,
            CanonicalDecisionHandoffStatus.INVALID,
            schema_reason,
            structure_valid=False,
        )
    candidate = handoff["candidate"]
    action = candidate.get("canonical_action")
    if action is not None and not isinstance(action, Mapping):
        return _result(handoff, CanonicalDecisionHandoffStatus.INVALID, schema_reason, structure_valid=False)
    provenance = handoff["provenance"]
    if any(not isinstance(record, Mapping) for record in provenance):
        return _result(handoff, CanonicalDecisionHandoffStatus.INVALID, schema_reason, structure_valid=False)
    if any(
        not isinstance(record.get("provenance_class"), str)
        or record.get("provenance_class") not in CANONICAL_PROVENANCE_CLASSES
        or not isinstance(record.get("verification_status"), str)
        or record.get("verification_status")
        not in CANONICAL_VERIFICATION_STATUSES
        for record in provenance
    ):
        return _result(
            handoff,
            CanonicalDecisionHandoffStatus.INVALID,
            schema_reason,
            structure_valid=False,
        )
    paths = [record.get("field_path") for record in provenance]
    if any(not _nonempty(path) for path in paths) or len(paths) != len(set(paths)):
        return _result(handoff, CanonicalDecisionHandoffStatus.INVALID, schema_reason, structure_valid=False)
    timestamps = [handoff.get("created_at")]
    if handoff.get("expires_at") is not None:
        timestamps.append(handoff.get("expires_at"))
    if any(_timestamp(value) is None for value in timestamps):
        return _result(handoff, CanonicalDecisionHandoffStatus.INVALID, schema_reason, structure_valid=False)

    reason = CanonicalDecisionHandoffReasonCode
    if candidate.get("lineage_promotability") != "promotable":
        return _result(handoff, CanonicalDecisionHandoffStatus.STRUCTURALLY_REFUSED, (reason.HANDOFF_LINEAGE_NON_PROMOTABLE,))

    invalid: list[CanonicalDecisionHandoffReasonCode] = []
    source = handoff["source_decision"]
    trustlog = handoff["trustlog_lineage"]
    replay = handoff["replay_lineage"]
    if source.get("canonical_decision_id") != handoff["decision_lineage"].get("decision_id"):
        invalid.append(reason.HANDOFF_SOURCE_ARTIFACT_MISMATCH)
    if handoff["decision_lineage"].get("bind_proof_ref"):
        invalid.append(reason.HANDOFF_SOURCE_ARTIFACT_MISMATCH)
    request_ids = (
        source.get("request_id"),
        trustlog.get("request_id"),
        replay.get("request_id"),
    )
    if not all(_nonempty(request_id) for request_id in request_ids):
        return _result(
            handoff,
            CanonicalDecisionHandoffStatus.INVALID,
            schema_reason,
            structure_valid=False,
        )
    if request_ids[0] != request_ids[1] or request_ids[0] != request_ids[2]:
        invalid.append(reason.HANDOFF_REQUEST_LINEAGE_MISMATCH)
    trustlog_verified = trustlog.get("verified")
    replay_verified = replay.get("verified")
    if type(trustlog_verified) is not bool or type(replay_verified) is not bool:
        return _result(
            handoff,
            CanonicalDecisionHandoffStatus.INVALID,
            schema_reason,
            structure_valid=False,
        )
    target = handoff["target_context"]
    if all(_nonempty(candidate.get(key)) for key in ("target_system", "target_resource")) and (
        candidate.get("target_system") != target.get("target_system")
        or candidate.get("target_resource") != target.get("target_resource")
        or target.get("canonicalized") is not True
    ):
        invalid.append(reason.HANDOFF_TARGET_CONTEXT_MISMATCH)

    authority = handoff.get("authority_evidence")
    authority_requirement = handoff["authority_requirement"]
    approval_requirement = handoff["human_approval_requirement"]
    if any(
        type(requirement.get(key)) is not bool
        for requirement in (authority_requirement, approval_requirement)
        for key in ("resolved", "required")
    ):
        return _result(
            handoff,
            CanonicalDecisionHandoffStatus.INVALID,
            schema_reason,
            structure_valid=False,
        )
    candidate_fields_present = all(
        _nonempty(candidate.get(key))
        for key in ("actor_identity", "target_system", "target_resource")
    )
    if (
        isinstance(authority, Mapping)
        and isinstance(action, Mapping)
        and candidate_fields_present
    ):
        if any(
            (authority.get("actor_identity") != candidate.get("actor_identity"),
             authority.get("action_contract_id") != (action or {}).get("contract_id"),
             authority.get("target_system") != candidate.get("target_system"),
             authority.get("target_scope") != candidate.get("target_resource"),
             authority.get("validation_result") != "VALID",
             not _nonempty(authority.get("issuer")),
             not _nonempty(authority.get("evidence_ref")),
             not _nonempty(authority.get("evidence_hash")))
        ):
            invalid.append(reason.HANDOFF_AUTHORITY_EVIDENCE_INVALID)
        expires = _timestamp(authority.get("expires_at"))
        issued = _timestamp(authority.get("issued_at"))
        if expires is None or issued is None:
            return _result(handoff, CanonicalDecisionHandoffStatus.INVALID, schema_reason, structure_valid=False)
        if evaluated_at > expires:
            invalid.append(reason.HANDOFF_AUTHORITY_EVIDENCE_EXPIRED)
        elif issued > expires or issued > evaluated_at:
            invalid.append(reason.HANDOFF_AUTHORITY_EVIDENCE_INVALID)

    approval = handoff.get("human_approval_evidence")
    if (
        isinstance(approval, Mapping)
        and isinstance(action, Mapping)
        and candidate_fields_present
    ):
        if any(
            (approval.get("candidate_ref") != candidate.get("candidate_id"),
             approval.get("action_contract_id") != (action or {}).get("contract_id"),
             approval.get("target_resource") != candidate.get("target_resource"),
             not _nonempty(approval.get("approver_identity")),
             not _nonempty(approval.get("receipt_ref")),
             not _nonempty(approval.get("receipt_hash")),
             approval.get("validation_result") != "VALID")
        ):
            invalid.append(reason.HANDOFF_APPROVAL_EVIDENCE_INVALID)
        expires = _timestamp(approval.get("expires_at"))
        approved = _timestamp(approval.get("approved_at"))
        if expires is None or approved is None:
            return _result(handoff, CanonicalDecisionHandoffStatus.INVALID, schema_reason, structure_valid=False)
        if evaluated_at > expires:
            invalid.append(reason.HANDOFF_APPROVAL_EVIDENCE_EXPIRED)
        elif approved > expires or approved > evaluated_at:
            invalid.append(reason.HANDOFF_APPROVAL_EVIDENCE_INVALID)

    policy = handoff.get("policy_lineage")
    if isinstance(policy, Mapping):
        if (
            type(policy.get("superseded")) is not bool
            or not isinstance(policy.get("policy_ids"), list)
            or not policy.get("policy_ids")
            or not all(_nonempty(policy_id) for policy_id in policy["policy_ids"])
        ):
            return _result(
                handoff,
                CanonicalDecisionHandoffStatus.INVALID,
                schema_reason,
                structure_valid=False,
            )
        effective = _timestamp(policy.get("effective_at"))
        expires = _timestamp(policy.get("expires_at"))
        if effective is None or expires is None:
            return _result(handoff, CanonicalDecisionHandoffStatus.INVALID, schema_reason, structure_valid=False)
        if (
            policy.get("superseded") is True or effective > evaluated_at
            or evaluated_at > expires or effective > expires
            or not all(_nonempty(policy.get(key)) for key in ("snapshot_id", "version", "semantic_digest"))
            or not isinstance(policy.get("policy_ids"), list) or not policy.get("policy_ids")
        ):
            # INVALID semantic contradictions retain precedence over review.
            if invalid:
                return _result(
                    handoff,
                    CanonicalDecisionHandoffStatus.INVALID,
                    tuple(dict.fromkeys(invalid)),
                )
            return _result(
                handoff,
                CanonicalDecisionHandoffStatus.REVIEW_REQUIRED,
                (reason.HANDOFF_POLICY_LINEAGE_STALE,),
            )
    expected_state = handoff.get("expected_state")
    if isinstance(expected_state, Mapping):
        observed = _timestamp(expected_state.get("observed_at"))
        if observed is None:
            return _result(handoff, CanonicalDecisionHandoffStatus.INVALID, schema_reason, structure_valid=False)
        if observed > evaluated_at or not all(_nonempty(expected_state.get(key)) for key in ("fingerprint", "source_ref")):
            invalid.append(reason.HANDOFF_EXPECTED_STATE_STALE)

    binding = trusted_context.candidate_hash_binding
    binding_trustworthy = binding is not None and (
        bool(binding.candidate_hash_profile)
        and bool(binding.verification_mechanism)
        and isinstance(binding.verified_at, datetime)
        and binding.verified_at.tzinfo is not None
        and binding.verified_at <= evaluated_at
    )
    binding_mismatch = binding_trustworthy and (
        binding.claim != "CANDIDATE_HASH_BINDS_CANDIDATE"
        or binding.candidate_value_digest
        != canonical_handoff_assertion_value_digest(candidate)
        or binding.asserted_candidate_hash != handoff.get("candidate_hash")
    )
    if invalid:
        if binding_mismatch:
            invalid.append(reason.HANDOFF_CANDIDATE_HASH_MISMATCH)
        return _result(handoff, CanonicalDecisionHandoffStatus.INVALID, tuple(dict.fromkeys(invalid)))

    if approval_requirement.get("resolved") is not True:
        return _result(
            handoff,
            CanonicalDecisionHandoffStatus.INCOMPLETE,
            (reason.HANDOFF_APPROVAL_REQUIREMENT_UNRESOLVED,),
        )
    if approval_requirement.get("required") is True and approval is None:
        return _result(handoff, CanonicalDecisionHandoffStatus.REVIEW_REQUIRED, (reason.HANDOFF_APPROVAL_EVIDENCE_MISSING,))
    incomplete: list[CanonicalDecisionHandoffReasonCode] = []
    if not _nonempty(source.get("canonical_decision_id")):
        incomplete.append(reason.HANDOFF_MISSING_CANONICAL_DECISION_ID)
    if not _nonempty(source.get("canonical_decision_hash")):
        incomplete.append(reason.HANDOFF_MISSING_CANONICAL_DECISION_HASH)
    if not _nonempty(source.get("canonical_decision_ts")):
        incomplete.append(reason.HANDOFF_MISSING_DECISION_TIMESTAMP)
    elif _timestamp(source.get("canonical_decision_ts")) is None:
        return _result(handoff, CanonicalDecisionHandoffStatus.INVALID, schema_reason, structure_valid=False)
    elif _timestamp(source.get("canonical_decision_ts")) > evaluated_at:
        return _result(
            handoff,
            CanonicalDecisionHandoffStatus.INVALID,
            schema_reason,
            structure_valid=False,
        )
    if not _nonempty(candidate.get("actor_identity")):
        incomplete.append(reason.HANDOFF_ACTOR_UNSPECIFIED)
    if not _nonempty(candidate.get("target_system")) or not _nonempty(candidate.get("target_resource")):
        incomplete.append(reason.HANDOFF_TARGET_UNSPECIFIED)
    if action is None:
        incomplete.extend((reason.HANDOFF_ACTION_UNSPECIFIED, reason.HANDOFF_AMBIGUOUS_ACTION))
    elif not all((_nonempty(action.get("contract_id")), _nonempty(action.get("version")), isinstance(action.get("parameters"), Mapping))):
        incomplete.append(reason.HANDOFF_AMBIGUOUS_ACTION)
    if authority_requirement.get("resolved") is not True:
        incomplete.append(reason.HANDOFF_AUTHORITY_REQUIREMENT_UNRESOLVED)
    elif authority_requirement.get("required") is True and authority is None:
        incomplete.append(reason.HANDOFF_AUTHORITY_EVIDENCE_MISSING)
    if policy is None:
        incomplete.append(reason.HANDOFF_POLICY_LINEAGE_MISSING)
    if expected_state is None:
        incomplete.append(reason.HANDOFF_EXPECTED_STATE_MISSING)
    if not _nonempty(source.get("request_id")) or not _nonempty(
        handoff.get("candidate_hash")
    ):
        return _result(
            handoff,
            CanonicalDecisionHandoffStatus.INVALID,
            schema_reason,
            structure_valid=False,
        )
    if approval is not None and not _nonempty(candidate.get("candidate_id")):
        return _result(
            handoff,
            CanonicalDecisionHandoffStatus.INVALID,
            schema_reason,
            structure_valid=False,
        )
    if (
        trustlog_verified is not True
        or not _nonempty(trustlog.get("artifact_ref"))
        or not _nonempty(trustlog.get("chain_hash"))
    ):
        incomplete.append(reason.HANDOFF_TRUSTLOG_UNVERIFIED)
    if (
        replay_verified is not True
        or not _nonempty(replay.get("artifact_ref"))
        or not _nonempty(replay.get("artifact_hash"))
    ):
        incomplete.append(reason.HANDOFF_REPLAY_UNVERIFIED)
    expires_at = _timestamp(handoff.get("expires_at")) if handoff.get("expires_at") else None
    created_at = _timestamp(handoff.get("created_at"))
    if created_at > evaluated_at:
        return _result(
            handoff,
            CanonicalDecisionHandoffStatus.INVALID,
            schema_reason,
            structure_valid=False,
        )
    if expires_at is not None and (created_at > expires_at or evaluated_at > expires_at):
        return _result(
            handoff,
            CanonicalDecisionHandoffStatus.INVALID,
            (reason.HANDOFF_EXPIRED,),
        )
    if incomplete:
        status = CanonicalDecisionHandoffStatus.INVALID if any(
            item in {reason.HANDOFF_TARGET_UNSPECIFIED, reason.HANDOFF_ACTION_UNSPECIFIED, reason.HANDOFF_AMBIGUOUS_ACTION}
            for item in incomplete
        ) else CanonicalDecisionHandoffStatus.INCOMPLETE
        return _result(handoff, status, tuple(incomplete))

    if not binding_trustworthy:
        return _result(
            handoff,
            CanonicalDecisionHandoffStatus.INCOMPLETE,
            (reason.HANDOFF_PROVENANCE_UNVERIFIED,),
        )
    if binding_mismatch:
        return _result(
            handoff,
            CanonicalDecisionHandoffStatus.INVALID,
            (reason.HANDOFF_CANDIDATE_HASH_MISMATCH,),
        )

    if authority_requirement["required"]:
        authority_binding = trusted_context.authority_requirement_binding
        if (
            authority_binding is None
            or not authority_binding.verification_mechanism
            or not isinstance(authority_binding.verified_at, datetime)
            or authority_binding.verified_at.tzinfo is None
            or authority_binding.verified_at > evaluated_at
            or authority_binding.claim != AUTHORITY_SATISFIES_REQUIREMENT_CLAIM
        ):
            return _result(
                handoff,
                CanonicalDecisionHandoffStatus.INCOMPLETE,
                (reason.HANDOFF_PROVENANCE_UNVERIFIED,),
            )
        if (
            authority_binding.authority_requirement_value_digest
            != canonical_handoff_assertion_value_digest(authority_requirement)
            or authority_binding.authority_evidence_value_digest
            != canonical_handoff_assertion_value_digest(authority)
        ):
            return _result(
                handoff,
                CanonicalDecisionHandoffStatus.INVALID,
                (reason.HANDOFF_PROVENANCE_MISMATCH,),
            )

    mandatory = (
        "source_decision.request_id", "source_decision.canonical_decision_id",
        "source_decision.canonical_decision_hash", "source_decision.canonical_decision_ts",
        "candidate.actor_identity", "candidate.target_system", "candidate.target_resource",
        "candidate.canonical_action", "candidate_hash", "trustlog_lineage", "replay_lineage",
        "policy_lineage", "authority_requirement", "authority_evidence",
        "human_approval_requirement", "human_approval_evidence", "expected_state",
    )
    records = {record["field_path"]: record for record in provenance}
    assertions: dict[str, list[TrustedValueAssertion]] = {}
    for assertion in trusted_context.value_assertions:
        assertions.setdefault(assertion.field_path, []).append(assertion)
    verified: list[str] = []
    for path in mandatory:
        present, value = _resolve(handoff, path)
        record = records.get(path)
        matches = assertions.get(path, [])
        if (
            not present
            or record is None
            or record.get("verification_status") != "VERIFIED"
            or record.get("provenance_class")
            in FORBIDDEN_READY_PROVENANCE_CLASSES
            or len(matches) != 1
        ):
            return _result(handoff, CanonicalDecisionHandoffStatus.INCOMPLETE, (reason.HANDOFF_PROVENANCE_UNVERIFIED,), verified=tuple(verified))
        assertion = matches[0]
        if assertion.verified_at.tzinfo is None or assertion.verified_at > evaluated_at:
            return _result(
                handoff,
                CanonicalDecisionHandoffStatus.INCOMPLETE,
                (reason.HANDOFF_PROVENANCE_UNVERIFIED,),
                verified=tuple(verified),
            )
        if (
            path == "human_approval_evidence"
            and approval_requirement["required"]
            and HUMAN_APPROVAL_EXACT_OPERATION_CLAIM not in assertion.claims
        ):
            return _result(
                handoff,
                CanonicalDecisionHandoffStatus.INCOMPLETE,
                (reason.HANDOFF_PROVENANCE_UNVERIFIED,),
                verified=tuple(verified),
            )
        if (
            record.get("value") != value
            or assertion.value_digest != canonical_handoff_assertion_value_digest(value)
            or not assertion.verification_mechanism
            or (record.get("source_artifact_ref") is not None and record.get("source_artifact_ref") != assertion.source_artifact_ref)
            or (record.get("source_hash") is not None and record.get("source_hash") != assertion.source_hash)
        ):
            return _result(handoff, CanonicalDecisionHandoffStatus.INVALID, (reason.HANDOFF_PROVENANCE_MISMATCH,), verified=tuple(verified))
        verified.append(path)
    return _result(handoff, CanonicalDecisionHandoffStatus.READY_FOR_GUARDED_PROMOTION, (), verified=tuple(verified))
