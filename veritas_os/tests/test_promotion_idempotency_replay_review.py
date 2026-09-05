"""Promotion replay handoff rejects stale and substituted evidence."""

from datetime import timedelta

import pytest
import veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_runtime_risk_review as risk_tests

from veritas_os.policy.live_adapter_bind_authorization_requirements import (
    LiveAdapterBindAuthorizationError,
    review_promotion_idempotency_and_replay,
    verify_promotion_idempotency_replay_review,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_runtime_risk_review import (
    RECORDED_AT,
    VALID_UNTIL,
    _packet,
)

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def source_packet():
    return risk_tests.source_packet.__wrapped__()


@pytest.fixture(scope="module")
def projection(source_packet):
    return risk_tests.projection.__wrapped__(source_packet)


@pytest.fixture(scope="module")
def valid_packet(source_packet, projection):
    return _packet(source_packet, projection)


@pytest.fixture(scope="module")
def review(valid_packet, source_packet):
    return review_promotion_idempotency_and_replay(
        valid_packet, source_packet, reviewed_at=RECORDED_AT
    )


def test_roundtrip_and_remaining_boundaries(review, valid_packet, source_packet):
    verified = verify_promotion_idempotency_replay_review(
        review.model_dump(mode="json"), valid_packet, source_packet, now=RECORDED_AT
    )
    assert verified == review
    assert (
        verified.remaining_authorization_routes
        == valid_packet.remaining_authorization_routes[1:]
    )
    assert (
        verified.remaining_invocation_routes == valid_packet.remaining_invocation_routes
    )
    assert verified.final_authorization_key_required
    assert verified.atomic_consumption_before_credentials_required
    assert not verified.duplicate_absence_verified
    assert not verified.execution_authorized
    assert not verified.authorization_consumed
    assert (
        review_promotion_idempotency_and_replay(
            valid_packet, source_packet, reviewed_at=RECORDED_AT
        )
        == review
    )


@pytest.mark.parametrize(
    "time",
    [
        RECORDED_AT - timedelta(seconds=1),
        VALID_UNTIL,
        VALID_UNTIL + timedelta(seconds=1),
    ],
)
def test_builder_rejects_outside_window(valid_packet, source_packet, time):
    with pytest.raises(LiveAdapterBindAuthorizationError, match="NOT_FRESH"):
        review_promotion_idempotency_and_replay(
            valid_packet, source_packet, reviewed_at=time
        )


@pytest.mark.parametrize("time", [RECORDED_AT.replace(tzinfo=None), "invalid", None])
def test_invalid_clock(valid_packet, source_packet, time):
    with pytest.raises(LiveAdapterBindAuthorizationError, match="TIME_INVALID"):
        review_promotion_idempotency_and_replay(
            valid_packet, source_packet, reviewed_at=time
        )


@pytest.mark.parametrize("signal", [False, None])
def test_nonpassing_risk(source_packet, projection, signal):
    risk = _packet(source_packet, projection, runtime_risk_signal=signal)
    with pytest.raises(LiveAdapterBindAuthorizationError, match="NOT_PASSED"):
        review_promotion_idempotency_and_replay(
            risk, source_packet, reviewed_at=RECORDED_AT
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("review_hash", "a" * 64),
        ("source_projection_digest", "a" * 64),
        ("source_runtime_risk_review_hash", "a" * 64),
        ("execution_authorized", True),
        ("execution_authorized", 0),
        ("duplicate_absence_verified", True),
        ("remaining_authorization_routes", []),
        ("remaining_invocation_routes", []),
        ("extra", True),
        ("reviewed_at", "invalid"),
    ],
)
def test_tampering(review, valid_packet, source_packet, field, value):
    raw = review.model_dump(mode="json")
    raw[field] = value
    with pytest.raises(LiveAdapterBindAuthorizationError, match="REVIEW_INVALID"):
        verify_promotion_idempotency_replay_review(
            raw, valid_packet, source_packet, now=RECORDED_AT
        )


def test_verifier_rejects_expired_review(review, valid_packet, source_packet):
    with pytest.raises(LiveAdapterBindAuthorizationError, match="REVIEW_INVALID"):
        verify_promotion_idempotency_replay_review(
            review, valid_packet, source_packet, now=VALID_UNTIL
        )


@pytest.mark.parametrize("raw", [None, {}, []])
def test_malformed_review(raw, valid_packet, source_packet):
    with pytest.raises(LiveAdapterBindAuthorizationError, match="REVIEW_INVALID"):
        verify_promotion_idempotency_replay_review(
            raw, valid_packet, source_packet, now=RECORDED_AT
        )


def test_independent_source_required(valid_packet):
    with pytest.raises(LiveAdapterBindAuthorizationError, match="SOURCE_INVALID"):
        review_promotion_idempotency_and_replay(
            valid_packet, {}, reviewed_at=RECORDED_AT
        )
