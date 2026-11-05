"""J3-06 inert SQLite E3-model oracles; NOT real receiver or RC1 tests."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from time import monotonic_ns, sleep

import pytest

from veritas_os.tests.research_j3_06_inert_receiver import (
    FixtureClock, InertReceiverAdmission, Operation, sign_fixture_evidence,
)

KEYS = {"Sanction": b"fixture-sanction-secret", "VERITAS": b"fixture-veritas-secret"}
OP = Operation("attempt-001", "receiver-fixture", "owner-incarnation-1", b"INERT")
CLOCK = FixtureClock(10000, 10000)


@pytest.fixture
def receiver(tmp_path):
    return InertReceiverAdmission(tmp_path / "receiver.sqlite3", fixture_keys=KEYS)


def evidence(op=OP, *, check_s=10000, check_v=10000, expiry=15000):
    return tuple(
        sign_fixture_evidence(
            issuer=issuer, key=KEYS[issuer], operation=op,
            checked_utc_ms=check, checked_mono_ms=check,
            expires_utc_ms=expiry,
        )
        for issuer, check in (("Sanction", check_s), ("VERITAS", check_v))
    )


@pytest.mark.parametrize("age", [0, 1999, 2000])
def test_j3_06_receiver_model_accepts_exact_age_bound(receiver, age):
    assert receiver.register(OP)
    result = receiver.attempt_admit(
        OP, evidence(check_s=10000-age, check_v=10000-age), CLOCK
    )
    assert result.status == "ENTRY_COMMITTED_ONCE"
    assert receiver.snapshot(OP.attempt_id)[0] == "ADMITTED"


@pytest.mark.parametrize("which", ["Sanction", "VERITAS"])
def test_j3_06_either_stale_issuer_denied(receiver, which):
    assert receiver.register(OP)
    e = evidence(
        check_s=7999 if which == "Sanction" else 10000,
        check_v=7999 if which == "VERITAS" else 10000,
    )
    result = receiver.attempt_admit(OP, e, CLOCK)
    assert result.status == "DENY_NO_ENTRY"
    assert result.reason == "TIME_OR_EXPIRY_INVALID"


@pytest.mark.parametrize("expiry", [10000, 9999])
def test_j3_06_expiry_equal_or_past_denied(receiver, expiry):
    assert receiver.register(OP)
    result = receiver.attempt_admit(OP, evidence(expiry=expiry), CLOCK)
    assert result.reason == "TIME_OR_EXPIRY_INVALID"


def test_j3_06_missing_issuer_denied(receiver):
    assert receiver.register(OP)
    assert receiver.attempt_admit(OP, evidence()[:1], CLOCK).reason == "ISSUER_SET_INVALID"


def test_j3_06_bad_fixture_signature_denied(receiver):
    assert receiver.register(OP)
    a, b = evidence()
    forged = replace(a, signature="0" * 64)
    assert receiver.attempt_admit(OP, (forged, b), CLOCK).reason == "SIGNATURE_INVALID"


@pytest.mark.parametrize("field", ["target", "owner_incarnation", "body", "attempt_id"])
def test_j3_06_registered_operation_substitution_denied(receiver, field):
    assert receiver.register(OP)
    altered = replace(OP, **{
        field: b"ALTERED" if field == "body" else "altered"
    })
    result = receiver.attempt_admit(altered, evidence(), CLOCK)
    assert result.status == "DENY_NO_ENTRY"
    assert receiver.snapshot(OP.attempt_id)[0] == "PENDING" if field == "attempt_id" else (
        receiver.snapshot(OP.attempt_id)[0] == "DENIED"
    )


def test_j3_06_signed_evidence_target_mismatch_denied(receiver):
    assert receiver.register(OP)
    wrong = replace(OP, target="different")
    assert receiver.attempt_admit(OP, evidence(wrong), CLOCK).reason == "BINDING_INVALID"


def test_j3_06_stop_before_receiver_admission_denied(receiver):
    assert receiver.register(OP)
    assert receiver.stop() == 1
    result = receiver.attempt_admit(OP, evidence(), CLOCK)
    assert result.reason == "STOP_EFFECTIVE"
    assert receiver.snapshot(OP.attempt_id)[0] == "DENIED"


def test_j3_06_stop_after_receiver_model_commit_does_not_undo(receiver):
    assert receiver.register(OP)
    result = receiver.attempt_admit(OP, evidence(), CLOCK)
    assert result.status == "ENTRY_COMMITTED_ONCE"
    assert receiver.stop() == 1
    assert receiver.snapshot(OP.attempt_id)[0] == "ADMITTED"
    assert receiver.attempt_admit(OP, evidence(), CLOCK).reason == "ALREADY_CLAIMED"


def test_j3_06_32_contenders_at_most_one(receiver):
    assert receiver.register(OP)
    with ThreadPoolExecutor(max_workers=32) as pool:
        results = list(pool.map(
            lambda _: receiver.attempt_admit(OP, evidence(), CLOCK),
            range(32),
        ))
    assert sum(r.status == "ENTRY_COMMITTED_ONCE" for r in results) == 1
    assert sum(r.status == "DENY_NO_ENTRY" for r in results) == 31


def test_j3_06_restart_replay_denied(receiver):
    assert receiver.register(OP)
    assert receiver.attempt_admit(OP, evidence(), CLOCK).status == "ENTRY_COMMITTED_ONCE"
    restarted = InertReceiverAdmission(receiver.path, fixture_keys=KEYS)
    assert not restarted.register(OP)
    assert restarted.attempt_admit(OP, evidence(), CLOCK).reason == "ALREADY_CLAIMED"


def test_j3_06_crash_after_durable_claim_no_retry(receiver):
    assert receiver.register(OP)
    assert receiver.simulate_crash_after_claim(OP.attempt_id)
    restarted = InertReceiverAdmission(receiver.path, fixture_keys=KEYS)
    assert restarted.snapshot(OP.attempt_id)[0] == "IN_PROGRESS"
    assert restarted.attempt_admit(OP, evidence(), CLOCK).reason == "ALREADY_CLAIMED"
    assert not restarted.register(OP)


def test_j3_06_lost_receipt_no_retry(receiver):
    assert receiver.register(OP)
    result = receiver.attempt_admit(OP, evidence(), CLOCK, lose_receipt=True)
    assert result.status == "UNKNOWN_NO_RETRY"
    assert receiver.snapshot(OP.attempt_id)[0] == "ADMITTED"
    assert receiver.attempt_admit(OP, evidence(), CLOCK).reason == "ALREADY_CLAIMED"


def test_j3_06_clock_uncertainty_expiry_denied(receiver):
    assert receiver.register(OP)
    result = receiver.attempt_admit(
        OP, evidence(expiry=10001), replace(CLOCK, uncertainty_ms=1)
    )
    assert result.reason == "TIME_OR_EXPIRY_INVALID"


def test_j3_06_clock_rollback_denied(receiver):
    assert receiver.register(OP)
    result = receiver.attempt_admit(
        OP, evidence(), replace(CLOCK, mono_ms=9999)
    )
    assert result.reason == "TIME_OR_EXPIRY_INVALID"


def test_j3_06_untrusted_fixture_clock_denied(receiver):
    assert receiver.register(OP)
    result = receiver.attempt_admit(
        OP, evidence(), replace(CLOCK, trusted_in_fixture=False)
    )
    assert result.reason == "CLOCK_UNTRUSTED"


def test_j3_06_interrupted_hook_unknown_no_retry(receiver):
    assert receiver.register(OP)

    def interrupt():
        raise RuntimeError("synthetic interruption")

    result = receiver.attempt_admit(
        OP, evidence(), CLOCK, before_commit=interrupt
    )
    assert result.status == "UNKNOWN_NO_RETRY"
    assert receiver.snapshot(OP.attempt_id)[0] == "UNKNOWN"
    assert receiver.attempt_admit(OP, evidence(), CLOCK).reason == "ALREADY_CLAIMED"


def test_j3_06_physical_time_gap_inside_transaction_is_not_closed(receiver):
    """Negative oracle: a 2s real pause after clock sample is still accepted.

    The SQLite transaction serializes local STOP, but not physical time.
    This intentionally demonstrates that the E3_MODEL is NOT strict RC1.
    """
    assert receiver.register(OP)
    times = []

    def pause_after_check():
        times.append(monotonic_ns())
        sleep(2.05)
        times.append(monotonic_ns())

    result = receiver.attempt_admit(
        OP, evidence(), CLOCK, before_commit=pause_after_check
    )
    assert times[1] - times[0] >= 2_000_000_000
    assert result.status == "ENTRY_COMMITTED_ONCE"
    assert receiver.snapshot(OP.attempt_id)[0] == "ADMITTED"
