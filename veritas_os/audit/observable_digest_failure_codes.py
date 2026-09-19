"""Deterministic observable-digest failure classification for the v1 contract.

This module operationalizes the failure-code vocabulary defined by
docs/en/architecture/observable-digest-ref-contract-addendum.md.

The mapper is intentionally pure: it performs no I/O, logging, event emission,
resolver calls, API wiring, or runtime enforcement changes. Callers must supply
typed predicates rather than free-text exception messages.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum


class ObservableDigestFailurePredicate(str, Enum):
    """Typed v1 predicates accepted by the deterministic failure mapper."""

    LOCATOR_MISSING = "LOCATOR_MISSING"
    LOCATOR_MALFORMED = "LOCATOR_MALFORMED"
    RESOLUTION_FAILED = "RESOLUTION_FAILED"
    AUTHZ_DENIED = "AUTHZ_DENIED"
    DIGEST_MISMATCH = "DIGEST_MISMATCH"
    BOUNDARY_VALIDATION_FAILURE = "BOUNDARY_VALIDATION_FAILURE"
    REPLAY_DUPLICATE = "REPLAY_DUPLICATE"
    STALE_DIGEST = "STALE_DIGEST"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    UNKNOWN_TRANSIENT = "UNKNOWN_TRANSIENT"


@dataclass(frozen=True)
class ObservableDigestFailureCodeSpec:
    """Immutable contract output for one observable-digest failure predicate."""

    code: str
    failure_name: str
    remediation_class: str
    sla_window_seconds: int
    recommended_remediation: str


FAILURE_CODE_SPECS: dict[
    ObservableDigestFailurePredicate, ObservableDigestFailureCodeSpec
] = {
    ObservableDigestFailurePredicate.LOCATOR_MISSING: ObservableDigestFailureCodeSpec(
        code="FC01",
        failure_name="LOCATOR_MISSING",
        remediation_class="ManualReview",
        sla_window_seconds=86400,
        recommended_remediation=(
            "Provide a valid separate-store locator and re-run boundary validation"
        ),
    ),
    ObservableDigestFailurePredicate.LOCATOR_MALFORMED: ObservableDigestFailureCodeSpec(
        code="FC02",
        failure_name="LOCATOR_MALFORMED",
        remediation_class="ManualReview",
        sla_window_seconds=86400,
        recommended_remediation="Correct locator format/scheme and resubmit",
    ),
    ObservableDigestFailurePredicate.RESOLUTION_FAILED: ObservableDigestFailureCodeSpec(
        code="FC03",
        failure_name="RESOLUTION_FAILED",
        remediation_class="Retryable",
        sla_window_seconds=300,
        recommended_remediation=(
            "Retry with backoff; escalate if unavailable beyond SLA"
        ),
    ),
    ObservableDigestFailurePredicate.AUTHZ_DENIED: ObservableDigestFailureCodeSpec(
        code="FC04",
        failure_name="AUTHZ_DENIED",
        remediation_class="ImmediateAction",
        sla_window_seconds=3600,
        recommended_remediation=(
            "Halt automated commit, review access policy, require authorized approval"
        ),
    ),
    ObservableDigestFailurePredicate.DIGEST_MISMATCH: ObservableDigestFailureCodeSpec(
        code="FC05",
        failure_name="DIGEST_MISMATCH",
        remediation_class="ManualReview",
        sla_window_seconds=86400,
        recommended_remediation=(
            "Block commit, preserve resolved material in audit detail, "
            "require reviewer approval"
        ),
    ),
    ObservableDigestFailurePredicate.BOUNDARY_VALIDATION_FAILURE: ObservableDigestFailureCodeSpec(
        code="FC06",
        failure_name="BOUNDARY_VALIDATION_FAILURE",
        remediation_class="ImmediateAction",
        sla_window_seconds=3600,
        recommended_remediation=(
            "Block effect path, open incident if behavioral risk exists, attach mitigation"
        ),
    ),
    ObservableDigestFailurePredicate.REPLAY_DUPLICATE: ObservableDigestFailureCodeSpec(
        code="FC07",
        failure_name="REPLAY_DUPLICATE",
        remediation_class="ImmediateAction",
        sla_window_seconds=3600,
        recommended_remediation="Treat as replay suspicion and require explicit review",
    ),
    ObservableDigestFailurePredicate.STALE_DIGEST: ObservableDigestFailureCodeSpec(
        code="FC08",
        failure_name="STALE_DIGEST",
        remediation_class="ManualReview",
        sla_window_seconds=86400,
        recommended_remediation="Refresh digest material and re-run validation",
    ),
    ObservableDigestFailurePredicate.SCHEMA_MISMATCH: ObservableDigestFailureCodeSpec(
        code="FC09",
        failure_name="SCHEMA_MISMATCH",
        remediation_class="Deferred",
        sla_window_seconds=86400,
        recommended_remediation="Fix schema shape in caller/adapter before retry",
    ),
    ObservableDigestFailurePredicate.UNKNOWN_TRANSIENT: ObservableDigestFailureCodeSpec(
        code="FC10",
        failure_name="UNKNOWN_TRANSIENT",
        remediation_class="Retryable",
        sla_window_seconds=60,
        recommended_remediation=(
            "Retry with short backoff and create follow-up classification task if repeated"
        ),
    ),
}


FAILURE_PRIORITY: tuple[ObservableDigestFailurePredicate, ...] = (
    ObservableDigestFailurePredicate.REPLAY_DUPLICATE,
    ObservableDigestFailurePredicate.DIGEST_MISMATCH,
    ObservableDigestFailurePredicate.BOUNDARY_VALIDATION_FAILURE,
    ObservableDigestFailurePredicate.AUTHZ_DENIED,
    ObservableDigestFailurePredicate.RESOLUTION_FAILED,
    ObservableDigestFailurePredicate.STALE_DIGEST,
    ObservableDigestFailurePredicate.LOCATOR_MALFORMED,
    ObservableDigestFailurePredicate.LOCATOR_MISSING,
    ObservableDigestFailurePredicate.SCHEMA_MISMATCH,
    ObservableDigestFailurePredicate.UNKNOWN_TRANSIENT,
)


def classify_observable_digest_failure(
    predicates: Iterable[ObservableDigestFailurePredicate],
) -> ObservableDigestFailureCodeSpec | None:
    """Return the highest-priority v1 failure classification.

    Empty input means that no failure predicate has been asserted and therefore
    returns None. Raw strings are rejected so runtime exception text cannot
    silently become contract semantics.
    """

    observed: set[ObservableDigestFailurePredicate] = set()
    for predicate in predicates:
        if not isinstance(predicate, ObservableDigestFailurePredicate):
            raise TypeError(
                "predicates must contain ObservableDigestFailurePredicate values"
            )
        observed.add(predicate)

    for predicate in FAILURE_PRIORITY:
        if predicate in observed:
            return FAILURE_CODE_SPECS[predicate]
    return None
