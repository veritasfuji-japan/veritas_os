"""Non-enforcing downstream reconciliation capability evidence.

This module records whether a downstream execution target exposes a trustworthy
path for resolving ``EFFECT_UNKNOWN``.  The artifact is descriptive evidence
only: it does not create execution eligibility, execution permission, retry
permission, or a terminal external-effect claim.

The runtime execution path does not consume this artifact in v1.  Any future use
as an execution-eligibility precondition requires a separate architecture
decision and proof update.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from veritas_os.security.hash import sha256_of_canonical_json

_HASH = r"^[0-9a-f]{64}$"


class ReconciliationCapabilityClass(StrEnum):
    """Descriptive target capability classes from the architecture boundary."""

    AUTHORITATIVE_QUERY = "AUTHORITATIVE_QUERY"
    AUTHORITATIVE_EVIDENCE = "AUTHORITATIVE_EVIDENCE"
    HEURISTIC_ONLY = "HEURISTIC_ONLY"
    UNAVAILABLE_OR_UNVERIFIED = "UNAVAILABLE_OR_UNVERIFIED"


def _parse_aware_timestamp(value: str, reason: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(reason) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(reason)
    return parsed


class ReconciliationCapabilityEvidence(BaseModel):
    """Immutable capability assessment; never execution authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal["reconciliation-capability-evidence/v1"] = (
        "reconciliation-capability-evidence/v1"
    )
    artifact_type: Literal["reconciliation_capability_evidence"] = (
        "reconciliation_capability_evidence"
    )
    artifact_version: Literal["v1"] = "v1"

    evidence_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    endpoint_identity_binding_digest: str = Field(pattern=_HASH)
    target_configuration_digest: str = Field(pattern=_HASH)
    capability_class: ReconciliationCapabilityClass

    correlation_identity_type: str | None = None
    correlation_identity_pre_dispatch: bool
    correlation_identity_caller_controlled: bool
    exact_attempt_lookup_available: bool
    exact_lineage_binding_supported: bool
    downstream_durability_supported: bool
    non_mutating_observation_supported: bool
    authoritative_evidence_available: bool

    source_type: str = Field(min_length=1)
    source_identity: str = Field(min_length=1)
    source_digest: str = Field(pattern=_HASH)

    verifier_id: str | None = None
    verifier_policy_id: str | None = None
    verifier_policy_hash: str | None = Field(default=None, pattern=_HASH)

    assessed_at: str = Field(min_length=1)
    valid_until: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    execution_eligibility_decision_created: Literal[False] = False
    execution_permission_created: Literal[False] = False
    retry_permission_created: Literal[False] = False
    terminal_effect_claim_created: Literal[False] = False

    @model_validator(mode="after")
    def validate_semantics(self) -> "ReconciliationCapabilityEvidence":
        """Fail closed on internally inconsistent capability evidence."""
        assessed = _parse_aware_timestamp(
            self.assessed_at,
            "reconciliation_capability_assessed_at_invalid",
        )
        if self.valid_until is not None:
            valid_until = _parse_aware_timestamp(
                self.valid_until,
                "reconciliation_capability_valid_until_invalid",
            )
            if valid_until <= assessed:
                raise ValueError(
                    "reconciliation_capability_valid_until_not_after_assessed_at"
                )

        verifier_values = (
            self.verifier_id,
            self.verifier_policy_id,
            self.verifier_policy_hash,
        )
        if any(value is not None for value in verifier_values) and not all(
            isinstance(value, str) and value.strip() for value in verifier_values
        ):
            raise ValueError("reconciliation_capability_verifier_binding_incomplete")

        if self.capability_class in {
            ReconciliationCapabilityClass.AUTHORITATIVE_QUERY,
            ReconciliationCapabilityClass.AUTHORITATIVE_EVIDENCE,
        }:
            if not all(
                (
                    self.exact_lineage_binding_supported,
                    self.downstream_durability_supported,
                    self.non_mutating_observation_supported,
                )
            ):
                raise ValueError(
                    "reconciliation_capability_authoritative_properties_missing"
                )
            if not all(
                isinstance(value, str) and value.strip() for value in verifier_values
            ):
                raise ValueError(
                    "reconciliation_capability_authoritative_verifier_missing"
                )

        if self.capability_class is ReconciliationCapabilityClass.AUTHORITATIVE_QUERY:
            if (
                not self.correlation_identity_pre_dispatch
                or not self.exact_attempt_lookup_available
                or not self.correlation_identity_type
                or not self.correlation_identity_type.strip()
            ):
                raise ValueError(
                    "reconciliation_capability_authoritative_query_invalid"
                )

        if (
            self.capability_class
            is ReconciliationCapabilityClass.AUTHORITATIVE_EVIDENCE
            and not self.authoritative_evidence_available
        ):
            raise ValueError(
                "reconciliation_capability_authoritative_evidence_invalid"
            )

        if self.capability_class is ReconciliationCapabilityClass.HEURISTIC_ONLY:
            if (
                self.exact_attempt_lookup_available
                or self.authoritative_evidence_available
            ):
                raise ValueError("reconciliation_capability_heuristic_class_conflict")

        return self

    def deterministic_digest(self) -> str:
        """Return stable content identity for this non-authorizing artifact."""
        return sha256_of_canonical_json(self.model_dump(mode="json"))

def validate_reconciliation_capability_for_current_target(
    evidence: ReconciliationCapabilityEvidence,
    *,
    current_endpoint_identity_binding_digest: str,
    current_target_configuration_digest: str,
    verification_time: datetime,
    require_authoritative: bool = False,
    expected_verifier_id: str | None = None,
    expected_verifier_policy_id: str | None = None,
    expected_verifier_policy_hash: str | None = None,
    expected_evidence_digest: str | None = None,
) -> list[str]:
    """Recheck one capability artifact against current target context.

    This validator is deliberately non-authorizing.  It returns deterministic
    failure reasons only; it does not create execution eligibility, execution
    permission, retry permission, or an external-effect claim.

    Expected verifier values and the expected evidence digest are trust anchors
    supplied by the caller from an independently controlled source.  The artifact
    must not be treated as self-authenticating merely because those fields exist.
    """
    if verification_time.tzinfo is None or verification_time.utcoffset() is None:
        raise ValueError("reconciliation_capability_verification_time_invalid")

    expected_verifier_values = (
        expected_verifier_id,
        expected_verifier_policy_id,
        expected_verifier_policy_hash,
    )
    if any(value is not None for value in expected_verifier_values) and not all(
        isinstance(value, str) and value.strip() for value in expected_verifier_values
    ):
        raise ValueError("reconciliation_capability_expected_verifier_binding_incomplete")

    failures: list[str] = []

    if (
        evidence.endpoint_identity_binding_digest
        != current_endpoint_identity_binding_digest
    ):
        failures.append("reconciliation_capability_endpoint_identity_changed")

    if evidence.target_configuration_digest != current_target_configuration_digest:
        failures.append("reconciliation_capability_target_configuration_changed")

    assessed_at = _parse_aware_timestamp(
        evidence.assessed_at,
        "reconciliation_capability_assessed_at_invalid",
    )
    if assessed_at > verification_time:
        failures.append("reconciliation_capability_assessment_from_future")

    if evidence.valid_until is not None:
        valid_until = _parse_aware_timestamp(
            evidence.valid_until,
            "reconciliation_capability_valid_until_invalid",
        )
        if verification_time >= valid_until:
            failures.append("reconciliation_capability_evidence_expired")

    if require_authoritative and evidence.capability_class not in {
        ReconciliationCapabilityClass.AUTHORITATIVE_QUERY,
        ReconciliationCapabilityClass.AUTHORITATIVE_EVIDENCE,
    }:
        failures.append("reconciliation_capability_not_authoritative")

    if all(
        isinstance(value, str) and value.strip() for value in expected_verifier_values
    ):
        actual_verifier_values = (
            evidence.verifier_id,
            evidence.verifier_policy_id,
            evidence.verifier_policy_hash,
        )
        if actual_verifier_values != expected_verifier_values:
            failures.append("reconciliation_capability_verifier_binding_mismatch")

    if (
        expected_evidence_digest is not None
        and evidence.deterministic_digest() != expected_evidence_digest
    ):
        failures.append("reconciliation_capability_evidence_digest_mismatch")

    return failures

