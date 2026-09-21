"""Tests for the pure observable-digest audit-entry builder."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from veritas_os.audit.observable_digest_audit_entry import (
    OBSERVABLE_DIGEST_AUDIT_SCHEMA_VERSION,
    ObservableDigestAuditExecutionObservation,
    ObservableDigestAuditPayloadSummary,
    ObservableDigestAuditRevocationVector,
    build_observable_digest_failure_audit_entry,
)
from veritas_os.audit.observable_digest_failure_codes import (
    ObservableDigestFailurePredicate,
)


def _build(**overrides: object):
    values: dict[str, object] = {
        "event_id": "evt-001",
        "timestamp": "2026-09-21T00:00:00Z",
        "predicates": [ObservableDigestFailurePredicate.DIGEST_MISMATCH],
        "validation_result": "failed",
        "actor": "wat_boundary",
        "locator": "store://tenant-x/observable/abc",
        "resolved_digest": "sha256:resolved",
        "expected_digest": "sha256:expected",
        "caller_id_hash": "sha256:caller",
    }
    values.update(overrides)
    return build_observable_digest_failure_audit_entry(**values)


def test_builder_maps_observation_to_interpretation_and_recommendation() -> None:
    entry = _build()

    assert entry.observation.predicate_present is True
    assert entry.classification_present is True
    assert entry.interpretation is not None
    assert entry.interpretation.failure_code == "FC05"
    assert entry.interpretation.failure_name == "DIGEST_MISMATCH"
    assert entry.recommendation is not None
    assert entry.recommendation.remediation_class == "ManualReview"
    assert entry.recommendation.sla_window_seconds == 86400
    assert entry.recommendation.recommended_remediation
    assert entry.execution is None
    assert entry.execution_observed is False


def test_recommendation_does_not_imply_execution() -> None:
    payload = _build().to_contract_dict()

    assert payload["remediation_class"] == "ManualReview"
    assert payload["execution_observed"] is False
    assert "action_taken" not in payload
    assert "remediation_attempts" not in payload


def test_execution_is_present_only_when_explicitly_observed() -> None:
    execution = ObservableDigestAuditExecutionObservation(
        action_taken="blocked_pending_review",
        remediation_attempts=1,
    )

    entry = _build(execution=execution)
    payload = entry.to_contract_dict()

    assert entry.execution_observed is True
    assert payload["execution_observed"] is True
    assert payload["action_taken"] == "blocked_pending_review"
    assert payload["remediation_attempts"] == 1
    assert payload["recommended_remediation"] != payload["action_taken"]


def test_empty_predicates_preserve_no_failure_without_unknown_transient() -> None:
    entry = _build(predicates=[], validation_result="passed")
    payload = entry.to_contract_dict()

    assert entry.observation.predicate_present is False
    assert entry.classification_present is False
    assert entry.interpretation is None
    assert entry.recommendation is None
    assert payload["observed_predicates"] == []
    assert payload["classification_present"] is False
    assert "failure_code" not in payload
    assert "failure_name" not in payload
    assert "remediation_class" not in payload


def test_unknown_transient_requires_explicit_typed_predicate() -> None:
    entry = _build(
        predicates=[ObservableDigestFailurePredicate.UNKNOWN_TRANSIENT],
    )

    assert entry.interpretation is not None
    assert entry.interpretation.failure_code == "FC10"
    assert entry.interpretation.failure_name == "UNKNOWN_TRANSIENT"


def test_raw_strings_are_not_interpreted_as_predicates() -> None:
    with pytest.raises(TypeError, match="ObservableDigestFailurePredicate"):
        _build(predicates=["DIGEST_MISMATCH"])


def test_multiple_predicates_are_deduplicated_and_priority_ordered() -> None:
    predicates = [
        ObservableDigestFailurePredicate.LOCATOR_MISSING,
        ObservableDigestFailurePredicate.DIGEST_MISMATCH,
        ObservableDigestFailurePredicate.RESOLUTION_FAILED,
        ObservableDigestFailurePredicate.DIGEST_MISMATCH,
    ]

    entry = _build(predicates=predicates)

    assert entry.observation.predicates == (
        ObservableDigestFailurePredicate.DIGEST_MISMATCH,
        ObservableDigestFailurePredicate.RESOLUTION_FAILED,
        ObservableDigestFailurePredicate.LOCATOR_MISSING,
    )
    assert entry.interpretation is not None
    assert entry.interpretation.failure_code == "FC05"


def test_same_semantic_input_produces_same_entry_independent_of_predicate_order() -> None:
    predicates = [
        ObservableDigestFailurePredicate.LOCATOR_MISSING,
        ObservableDigestFailurePredicate.RESOLUTION_FAILED,
        ObservableDigestFailurePredicate.DIGEST_MISMATCH,
    ]

    forward = _build(predicates=predicates)
    reverse = _build(predicates=reversed(predicates))

    assert forward == reverse
    assert forward.to_contract_dict() == reverse.to_contract_dict()


def test_builder_is_version_aware_and_rejects_unknown_schema() -> None:
    entry = _build(schema_version=OBSERVABLE_DIGEST_AUDIT_SCHEMA_VERSION)
    assert entry.v1_schema_version == "1.0"

    with pytest.raises(ValueError, match="unsupported observable-digest"):
        _build(schema_version="2.0")


def test_timestamp_must_be_timezone_aware_utc() -> None:
    assert _build(timestamp="2026-09-21T00:00:00+00:00").timestamp == (
        "2026-09-21T00:00:00Z"
    )

    with pytest.raises(ValueError, match="timezone-aware UTC"):
        _build(timestamp="2026-09-21T00:00:00")

    with pytest.raises(ValueError, match="timezone-aware UTC"):
        _build(timestamp="2026-09-21T09:00:00+09:00")


def test_optional_observation_details_are_immutable_and_serialized() -> None:
    revocation = ObservableDigestAuditRevocationVector(
        confirmed=True,
        source_count=2,
        compact="rv:abc",
    )
    summary = ObservableDigestAuditPayloadSummary(
        digest_bytes=32,
        locator_scheme="store",
    )

    entry = _build(
        revocation_vector=revocation,
        payload_summary=summary,
    )
    payload = entry.to_contract_dict()

    assert payload["revocation_vector"] == {
        "confirmed": True,
        "source_count": 2,
        "compact": "rv:abc",
    }
    assert payload["payload_summary"] == {
        "digest_bytes": 32,
        "locator_scheme": "store",
    }

    with pytest.raises(FrozenInstanceError):
        revocation.source_count = 3


def test_entry_value_objects_are_frozen() -> None:
    entry = _build()

    with pytest.raises(FrozenInstanceError):
        entry.event_id = "evt-002"

    with pytest.raises(FrozenInstanceError):
        entry.observation.actor = "other"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("event_id", "", "event_id"),
        ("validation_result", "", "validation_result"),
        ("actor", "", "actor"),
    ],
)
def test_required_text_fields_reject_empty_values(
    field: str,
    value: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _build(**{field: value})


def test_execution_observation_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="action_taken"):
        ObservableDigestAuditExecutionObservation(action_taken="")

    with pytest.raises(ValueError, match="remediation_attempts"):
        ObservableDigestAuditExecutionObservation(
            action_taken="blocked",
            remediation_attempts=-1,
        )


def test_compact_observation_types_reject_invalid_values() -> None:
    with pytest.raises(ValueError, match="source_count"):
        ObservableDigestAuditRevocationVector(
            confirmed=False,
            source_count=-1,
            compact="rv:abc",
        )

    with pytest.raises(ValueError, match="digest_bytes"):
        ObservableDigestAuditPayloadSummary(digest_bytes=-1)

    with pytest.raises(ValueError, match="locator_scheme"):
        ObservableDigestAuditPayloadSummary(locator_scheme=" ")
