"""Pure deterministic audit-entry builder for observable-digest failures.

This module turns already-observed typed predicates and audit facts into an
immutable, reviewer-facing audit record. It intentionally performs no I/O,
persistence, logging, network access, resolver calls, runtime enforcement, or
automatic remediation.

The builder preserves four separate concepts:

observation != interpretation != recommendation != execution

A recommended remediation never implies that remediation was executed.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from veritas_os.audit.observable_digest_failure_codes import (
    FAILURE_PRIORITY,
    ObservableDigestFailurePredicate,
    classify_observable_digest_failure,
)


OBSERVABLE_DIGEST_AUDIT_SCHEMA_VERSION = "1.0"


def _non_empty(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _canonical_utc_timestamp(value: str) -> str:
    text = _non_empty(value, "timestamp")
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("timestamp must be valid ISO8601 UTC") from exc

    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be timezone-aware UTC")

    return parsed.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ObservableDigestAuditRevocationVector:
    """Immutable optional revocation-vector observation."""

    confirmed: bool
    source_count: int
    compact: str

    def __post_init__(self) -> None:
        if self.source_count < 0:
            raise ValueError("source_count must be >= 0")
        if not str(self.compact).strip():
            raise ValueError("compact must be non-empty")


@dataclass(frozen=True)
class ObservableDigestAuditPayloadSummary:
    """Immutable optional compact payload observation."""

    digest_bytes: int | None = None
    locator_scheme: str | None = None

    def __post_init__(self) -> None:
        if self.digest_bytes is not None and self.digest_bytes < 0:
            raise ValueError("digest_bytes must be >= 0")
        if self.locator_scheme is not None and not str(self.locator_scheme).strip():
            raise ValueError("locator_scheme must be non-empty when supplied")


@dataclass(frozen=True)
class ObservableDigestAuditExecutionObservation:
    """Explicit observed execution fact.

    Presence of this object means the caller is asserting that an action was
    actually observed. Recommendations never create this object automatically.
    """

    action_taken: str
    remediation_attempts: int = 0

    def __post_init__(self) -> None:
        if not str(self.action_taken).strip():
            raise ValueError("action_taken must be non-empty")
        if self.remediation_attempts < 0:
            raise ValueError("remediation_attempts must be >= 0")


@dataclass(frozen=True)
class ObservableDigestAuditObservation:
    """Facts observed before deterministic contract interpretation."""

    predicates: tuple[ObservableDigestFailurePredicate, ...]
    locator: str | None
    resolved_digest: str | None
    expected_digest: str | None
    validation_result: str
    caller_id_hash: str | None
    actor: str
    revocation_vector: ObservableDigestAuditRevocationVector | None
    payload_summary: ObservableDigestAuditPayloadSummary | None

    @property
    def predicate_present(self) -> bool:
        return bool(self.predicates)


@dataclass(frozen=True)
class ObservableDigestAuditInterpretation:
    """Deterministic contract interpretation of the observed predicates."""

    failure_code: str
    failure_name: str


@dataclass(frozen=True)
class ObservableDigestAuditRecommendation:
    """Contract recommendation, separate from any observed execution."""

    remediation_class: str
    sla_window_seconds: int
    recommended_remediation: str


@dataclass(frozen=True)
class ObservableDigestFailureAuditEntry:
    """Immutable audit entry produced by the pure builder."""

    event_id: str
    timestamp: str
    v1_schema_version: str
    observation: ObservableDigestAuditObservation
    interpretation: ObservableDigestAuditInterpretation | None
    recommendation: ObservableDigestAuditRecommendation | None
    execution: ObservableDigestAuditExecutionObservation | None

    @property
    def classification_present(self) -> bool:
        return self.interpretation is not None

    @property
    def execution_observed(self) -> bool:
        return self.execution is not None

    def to_contract_dict(self) -> dict[str, object]:
        """Return a deterministic flat audit-detail representation."""

        payload: dict[str, object] = {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "v1_schema_version": self.v1_schema_version,
            "predicate_present": self.observation.predicate_present,
            "observed_predicates": [
                predicate.value for predicate in self.observation.predicates
            ],
            "classification_present": self.classification_present,
            "validation_result": self.observation.validation_result,
            "actor": self.observation.actor,
            "execution_observed": self.execution_observed,
        }

        for key, value in (
            ("locator", self.observation.locator),
            ("resolved_digest", self.observation.resolved_digest),
            ("expected_digest", self.observation.expected_digest),
            ("caller_id_hash", self.observation.caller_id_hash),
        ):
            if value is not None:
                payload[key] = value

        if self.observation.revocation_vector is not None:
            rv = self.observation.revocation_vector
            payload["revocation_vector"] = {
                "confirmed": rv.confirmed,
                "source_count": rv.source_count,
                "compact": rv.compact,
            }

        if self.observation.payload_summary is not None:
            summary = self.observation.payload_summary
            summary_payload: dict[str, object] = {}
            if summary.digest_bytes is not None:
                summary_payload["digest_bytes"] = summary.digest_bytes
            if summary.locator_scheme is not None:
                summary_payload["locator_scheme"] = summary.locator_scheme
            payload["payload_summary"] = summary_payload

        if self.interpretation is not None:
            payload["failure_code"] = self.interpretation.failure_code
            payload["failure_name"] = self.interpretation.failure_name

        if self.recommendation is not None:
            payload["remediation_class"] = self.recommendation.remediation_class
            payload["sla_window_seconds"] = self.recommendation.sla_window_seconds
            payload["recommended_remediation"] = (
                self.recommendation.recommended_remediation
            )

        if self.execution is not None:
            payload["action_taken"] = self.execution.action_taken
            payload["remediation_attempts"] = self.execution.remediation_attempts

        return payload


def _normalize_predicates(
    predicates: Iterable[ObservableDigestFailurePredicate],
) -> tuple[ObservableDigestFailurePredicate, ...]:
    observed: set[ObservableDigestFailurePredicate] = set()
    for predicate in predicates:
        if not isinstance(predicate, ObservableDigestFailurePredicate):
            raise TypeError(
                "predicates must contain ObservableDigestFailurePredicate values"
            )
        observed.add(predicate)

    return tuple(predicate for predicate in FAILURE_PRIORITY if predicate in observed)


def build_observable_digest_failure_audit_entry(
    *,
    event_id: str,
    timestamp: str,
    predicates: Iterable[ObservableDigestFailurePredicate],
    validation_result: str,
    actor: str,
    locator: str | None = None,
    resolved_digest: str | None = None,
    expected_digest: str | None = None,
    caller_id_hash: str | None = None,
    revocation_vector: ObservableDigestAuditRevocationVector | None = None,
    payload_summary: ObservableDigestAuditPayloadSummary | None = None,
    execution: ObservableDigestAuditExecutionObservation | None = None,
    schema_version: str = OBSERVABLE_DIGEST_AUDIT_SCHEMA_VERSION,
) -> ObservableDigestFailureAuditEntry:
    """Build one immutable audit entry without side effects.

    The caller supplies event identity, time, observations, and any explicit
    execution fact. The builder does not generate timestamps/IDs, emit records,
    resolve locators, perform remediation, or infer execution from a
    recommendation.
    """

    if schema_version != OBSERVABLE_DIGEST_AUDIT_SCHEMA_VERSION:
        raise ValueError(
            "unsupported observable-digest audit schema version: "
            f"{schema_version}"
        )

    normalized_predicates = _normalize_predicates(predicates)
    classification = classify_observable_digest_failure(normalized_predicates)

    observation = ObservableDigestAuditObservation(
        predicates=normalized_predicates,
        locator=_optional_text(locator),
        resolved_digest=_optional_text(resolved_digest),
        expected_digest=_optional_text(expected_digest),
        validation_result=_non_empty(validation_result, "validation_result"),
        caller_id_hash=_optional_text(caller_id_hash),
        actor=_non_empty(actor, "actor"),
        revocation_vector=revocation_vector,
        payload_summary=payload_summary,
    )

    interpretation: ObservableDigestAuditInterpretation | None = None
    recommendation: ObservableDigestAuditRecommendation | None = None

    if classification is not None:
        interpretation = ObservableDigestAuditInterpretation(
            failure_code=classification.code,
            failure_name=classification.failure_name,
        )
        recommendation = ObservableDigestAuditRecommendation(
            remediation_class=classification.remediation_class,
            sla_window_seconds=classification.sla_window_seconds,
            recommended_remediation=classification.recommended_remediation,
        )

    return ObservableDigestFailureAuditEntry(
        event_id=_non_empty(event_id, "event_id"),
        timestamp=_canonical_utc_timestamp(timestamp),
        v1_schema_version=schema_version,
        observation=observation,
        interpretation=interpretation,
        recommendation=recommendation,
        execution=execution,
    )
