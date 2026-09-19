"""Tests for the pure observable-digest failure-code mapper."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from veritas_os.audit.observable_digest_failure_codes import (
    FAILURE_CODE_SPECS,
    ObservableDigestFailureCodeSpec,
    ObservableDigestFailurePredicate,
    classify_observable_digest_failure,
)


@pytest.mark.parametrize(
    ("predicate", "code", "name", "remediation_class", "sla"),
    [
        (
            ObservableDigestFailurePredicate.LOCATOR_MISSING,
            "FC01",
            "LOCATOR_MISSING",
            "ManualReview",
            86400,
        ),
        (
            ObservableDigestFailurePredicate.LOCATOR_MALFORMED,
            "FC02",
            "LOCATOR_MALFORMED",
            "ManualReview",
            86400,
        ),
        (
            ObservableDigestFailurePredicate.RESOLUTION_FAILED,
            "FC03",
            "RESOLUTION_FAILED",
            "Retryable",
            300,
        ),
        (
            ObservableDigestFailurePredicate.AUTHZ_DENIED,
            "FC04",
            "AUTHZ_DENIED",
            "ImmediateAction",
            3600,
        ),
        (
            ObservableDigestFailurePredicate.DIGEST_MISMATCH,
            "FC05",
            "DIGEST_MISMATCH",
            "ManualReview",
            86400,
        ),
        (
            ObservableDigestFailurePredicate.BOUNDARY_VALIDATION_FAILURE,
            "FC06",
            "BOUNDARY_VALIDATION_FAILURE",
            "ImmediateAction",
            3600,
        ),
        (
            ObservableDigestFailurePredicate.REPLAY_DUPLICATE,
            "FC07",
            "REPLAY_DUPLICATE",
            "ImmediateAction",
            3600,
        ),
        (
            ObservableDigestFailurePredicate.STALE_DIGEST,
            "FC08",
            "STALE_DIGEST",
            "ManualReview",
            86400,
        ),
        (
            ObservableDigestFailurePredicate.SCHEMA_MISMATCH,
            "FC09",
            "SCHEMA_MISMATCH",
            "Deferred",
            86400,
        ),
        (
            ObservableDigestFailurePredicate.UNKNOWN_TRANSIENT,
            "FC10",
            "UNKNOWN_TRANSIENT",
            "Retryable",
            60,
        ),
    ],
)
def test_maps_each_typed_predicate_to_v1_contract(
    predicate: ObservableDigestFailurePredicate,
    code: str,
    name: str,
    remediation_class: str,
    sla: int,
) -> None:
    result = classify_observable_digest_failure([predicate])

    assert result is not None
    assert result.code == code
    assert result.failure_name == name
    assert result.remediation_class == remediation_class
    assert result.sla_window_seconds == sla
    assert result.recommended_remediation


def test_multiple_predicates_follow_contract_priority_not_input_order() -> None:
    predicates = [
        ObservableDigestFailurePredicate.LOCATOR_MISSING,
        ObservableDigestFailurePredicate.RESOLUTION_FAILED,
        ObservableDigestFailurePredicate.DIGEST_MISMATCH,
    ]

    forward = classify_observable_digest_failure(predicates)
    reverse = classify_observable_digest_failure(reversed(predicates))

    assert forward is not None
    assert reverse is not None
    assert forward.code == "FC05"
    assert reverse == forward


def test_replay_duplicate_has_highest_priority() -> None:
    result = classify_observable_digest_failure(
        list(ObservableDigestFailurePredicate)
    )

    assert result is not None
    assert result.code == "FC07"
    assert result.failure_name == "REPLAY_DUPLICATE"


def test_duplicate_predicates_do_not_change_result() -> None:
    predicate = ObservableDigestFailurePredicate.STALE_DIGEST

    once = classify_observable_digest_failure([predicate])
    repeated = classify_observable_digest_failure([predicate, predicate, predicate])

    assert repeated == once


def test_empty_predicates_mean_no_failure() -> None:
    assert classify_observable_digest_failure([]) is None


def test_raw_strings_are_not_interpreted_as_contract_predicates() -> None:
    with pytest.raises(TypeError, match="ObservableDigestFailurePredicate"):
        classify_observable_digest_failure([
            ["DIGEST_MISMATCH"]  # type: ignore[list-item]
        )


def test_failure_specs_are_immutable() -> None:
    spec = FAILURE_CODE_SPECS[
        ObservableDigestFailurePredicate.DIGEST_MISMATCH
    ]

    with pytest.raises(FrozenInstanceError):
        spec.code = "FC99"  # type: ignore[misc]


def test_public_spec_type_is_frozen_contract_value() -> None:
    spec = ObservableDigestFailureCodeSpec(
        code="FC00",
        failure_name="EXAMPLE",
        remediation_class="Example",
        sla_window_seconds=1,
        recommended_remediation="example",
    )

    assert spec.code == "FC00"
