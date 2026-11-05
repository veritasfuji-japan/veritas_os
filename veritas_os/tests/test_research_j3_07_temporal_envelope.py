"""J3-07 research-only temporal envelope counterexamples and trust gates."""

from dataclasses import replace

import pytest

from veritas_os.tests.research_j3_07_temporal_envelope import (
    Assumptions,
    ClockInterval,
    IssuerSample,
    evaluate_conditional_time_envelope as evaluate,
)

SAMPLES = (
    IssuerSample("Sanction", 10000, 10000, 14000),
    IssuerSample("VERITAS", 10000, 10000, 14000),
)
CLOCK = ClockInterval(11000, 11000, 11000)
ASSUMPTIONS = Assumptions(
    entry_event="E3",
    clock_root_verified=True,
    issuer_roots_verified=True,
    upper_delay_bound_ms=500,
    delay_bound_certified=True,
    stop_order_proven=True,
    remote_revocation_visibility_proven=True,
    one_use_proven=True,
)


def test_j3_07_conditional_envelope_is_never_admission():
    result = evaluate(SAMPLES, CLOCK, ASSUMPTIONS)
    assert result.disposition == "CONDITIONAL_TIME_ENVELOPE"
    assert result.reason == "ASSUMED_BOUNDS_ONLY"
    assert (result.latest_utc_ms, result.latest_mono_ms) == (11500, 11500)


@pytest.mark.parametrize("delay", [0, 999, 1000])
def test_j3_07_exact_age_2000_is_allowed_under_assumed_bound(delay):
    result = evaluate(
        SAMPLES, CLOCK, replace(ASSUMPTIONS, upper_delay_bound_ms=delay)
    )
    assert result.disposition == "CONDITIONAL_TIME_ENVELOPE"


def test_j3_07_age_2001_at_latest_entry_denied():
    result = evaluate(
        SAMPLES, CLOCK, replace(ASSUMPTIONS, upper_delay_bound_ms=1001)
    )
    assert result.reason == "AGE_UPPER_BOUND_EXCEEDED"


def test_j3_07_either_issuer_stale_denied():
    samples = (replace(SAMPLES[0], checked_utc_ms=9000), SAMPLES[1])
    result = evaluate(samples, CLOCK, ASSUMPTIONS)
    assert result.reason == "AGE_UPPER_BOUND_EXCEEDED"


@pytest.mark.parametrize("expiry", [11500, 11499])
def test_j3_07_strict_expiry_boundary_denied(expiry):
    samples = (replace(SAMPLES[0], expires_utc_ms=expiry), SAMPLES[1])
    result = evaluate(samples, CLOCK, ASSUMPTIONS)
    assert result.reason == "STRICT_EXPIRY_NOT_PROVABLE"


def test_j3_07_expiry_one_millisecond_after_latest_is_conditional():
    samples = (replace(SAMPLES[0], expires_utc_ms=11501), SAMPLES[1])
    assert evaluate(samples, CLOCK, ASSUMPTIONS).disposition == (
        "CONDITIONAL_TIME_ENVELOPE"
    )


def test_j3_07_clock_uncertainty_consumes_delay_margin():
    clock = ClockInterval(10900, 11200, 11000)
    result = evaluate(SAMPLES, clock, ASSUMPTIONS)
    assert result.latest_utc_ms == 11700
    assert result.disposition == "CONDITIONAL_TIME_ENVELOPE"
    assert evaluate(
        SAMPLES, clock, replace(ASSUMPTIONS, upper_delay_bound_ms=801)
    ).reason == "AGE_UPPER_BOUND_EXCEEDED"


@pytest.mark.parametrize("field", [
    "clock_root_verified", "issuer_roots_verified",
])
def test_j3_07_unverified_trust_root_not_scored(field):
    result = evaluate(SAMPLES, CLOCK, replace(ASSUMPTIONS, **{field: False}))
    assert result.disposition == "NOT_SCORED"
    assert result.reason == "TRUST_ROOT_UNVERIFIED"


@pytest.mark.parametrize("delay,certified,reason", [
    (None, False, "NO_FINITE_DELAY_BOUND"),
    (-1, True, "NO_FINITE_DELAY_BOUND"),
    (500, False, "DELAY_BOUND_NOT_CERTIFIED"),
])
def test_j3_07_missing_bound_is_not_scored(delay, certified, reason):
    result = evaluate(
        SAMPLES, CLOCK,
        replace(ASSUMPTIONS, upper_delay_bound_ms=delay,
                delay_bound_certified=certified),
    )
    assert result.disposition == "NOT_SCORED"
    assert result.reason == reason


@pytest.mark.parametrize("event", [None, "E0", "E4"])
def test_j3_07_entry_event_must_be_named(event):
    result = evaluate(SAMPLES, CLOCK, replace(ASSUMPTIONS, entry_event=event))
    assert result.reason == "ENTRY_EVENT_UNDEFINED"


@pytest.mark.parametrize("field,reason", [
    ("stop_order_proven", "STOP_ORDER_UNPROVEN"),
    ("remote_revocation_visibility_proven", "REMOTE_REVOCATION_UNPROVEN"),
    ("one_use_proven", "ONE_USE_UNPROVEN"),
])
def test_j3_07_time_margin_does_not_prove_other_authority_properties(field, reason):
    result = evaluate(SAMPLES, CLOCK, replace(ASSUMPTIONS, **{field: False}))
    assert result.disposition == "NOT_SCORED"
    assert result.reason == reason


def test_j3_07_clock_rollback_denied():
    clock = replace(CLOCK, monotonic_ms=9999)
    assert evaluate(SAMPLES, clock, ASSUMPTIONS).reason == "CHECK_IN_FUTURE"


def test_j3_07_future_issuer_utc_denied():
    samples = (replace(SAMPLES[0], checked_utc_ms=11001), SAMPLES[1])
    assert evaluate(samples, CLOCK, ASSUMPTIONS).reason == "CHECK_IN_FUTURE"


@pytest.mark.parametrize("samples,clock", [
    ((SAMPLES[0], SAMPLES[0]), CLOCK),
    (SAMPLES[:1], CLOCK),
    (SAMPLES, ClockInterval(12000, 11000, 11000)),
    (SAMPLES, ClockInterval(11000, 11000, True)),
])
def test_j3_07_malformed_fixtures_fail_closed(samples, clock):
    assert evaluate(samples, clock, ASSUMPTIONS).reason == "MALFORMED_FIXTURE"


def test_j3_07_arbitrary_postcheck_pause_defeats_precheck_claim():
    """Same initial sample passes B=500 but a 2500ms delay is outside B.

    The original conditional verdict cannot certify a later physical entry
    if the platform cannot actually enforce the 500ms maximum.
    """
    assumed = evaluate(SAMPLES, CLOCK, ASSUMPTIONS)
    actual = evaluate(
        SAMPLES, CLOCK, replace(ASSUMPTIONS, upper_delay_bound_ms=2500)
    )
    assert assumed.disposition == "CONDITIONAL_TIME_ENVELOPE"
    assert actual.reason == "AGE_UPPER_BOUND_EXCEEDED"


def test_j3_07_stop_after_sample_before_entry_not_proven_by_clock():
    """Time envelope alone cannot establish STOP linearization."""
    result = evaluate(
        SAMPLES, CLOCK, replace(ASSUMPTIONS, stop_order_proven=False)
    )
    assert result.reason == "STOP_ORDER_UNPROVEN"


def test_j3_07_remote_revocation_unseen_not_fixed_by_zero_delay():
    result = evaluate(
        SAMPLES, CLOCK,
        replace(ASSUMPTIONS, upper_delay_bound_ms=0,
                remote_revocation_visibility_proven=False),
    )
    assert result.reason == "REMOTE_REVOCATION_UNPROVEN"
