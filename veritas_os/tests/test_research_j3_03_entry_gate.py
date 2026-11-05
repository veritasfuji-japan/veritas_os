"""J3-03 synthetic state-machine oracles; not Strict RC1 conformance tests."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest

from veritas_os.tests.research_j3_03_entry_gate import (
    FrozenIntent, SyntheticEntryGate, SyntheticIssuer,
)

INTENT = FrozenIntent("attempt-001", "sandbox.example", "digest-001", "owner-001")


def gate(
    *, utc_ms=10_000, mono_ms=10_000, uncertainty_ms=0,
    sanction_check=10_000, veritas_check=10_000,
    sanction_mono=10_000, veritas_mono=10_000,
    sanction_expiry=15_000, veritas_expiry=15_000,
    issuers=None,
):
    if issuers is None:
        issuers = (
            SyntheticIssuer(
                "Sanction", sanction_check, sanction_mono, sanction_expiry,
                INTENT.payload_digest,
            ),
            SyntheticIssuer(
                "VERITAS", veritas_check, veritas_mono, veritas_expiry,
                INTENT.payload_digest,
            ),
        )
    return SyntheticEntryGate(
        intent=INTENT, issuers=issuers,
        utc_ms=utc_ms, mono_ms=mono_ms, uncertainty_ms=uncertainty_ms,
    )


def enter(model, intent=INTENT, owner=INTENT.owner_incarnation, **kwargs):
    return model.attempt_entry(intent, owner_incarnation=owner, **kwargs)


@pytest.mark.parametrize("elapsed_ms", [0, 1999, 2000])
def test_t01_t02_t03_both_issuer_age_boundary_accepts(elapsed_ms):
    model = gate(utc_ms=10_000 + elapsed_ms, mono_ms=10_000 + elapsed_ms)
    decision = enter(model)
    assert decision.status == "ENTRY_COMMITTED_ONCE"
    assert decision.receipt.event == "E_SIM"
    assert len(model.snapshot()[0]) == 1


@pytest.mark.parametrize("issuer", ["Sanction", "VERITAS"])
def test_t04_t05_one_issuer_stale_rejects(issuer):
    model = gate(
        utc_ms=12_001, mono_ms=12_001,
        sanction_check=10_000 if issuer == "Sanction" else 12_001,
        veritas_check=10_000 if issuer == "VERITAS" else 12_001,
        sanction_mono=10_000 if issuer == "Sanction" else 12_001,
        veritas_mono=10_000 if issuer == "VERITAS" else 12_001,
    )
    assert enter(model).status == "DENY_NO_ENTRY"
    assert model.snapshot()[0] == ()


def test_t06_future_check_rejected():
    assert enter(gate(sanction_check=10_001)).status == "DENY_NO_ENTRY"


def test_t07_pause_before_gate_rechecked():
    model = gate()
    model.advance(2001)
    assert enter(model).status == "DENY_NO_ENTRY"
    assert model.snapshot()[0] == ()


def test_t09_missing_issuer_rejected():
    only_sanction = (SyntheticIssuer(
        "Sanction", 10_000, 10_000, 15_000, INTENT.payload_digest
    ),)
    assert enter(gate(issuers=only_sanction)).status == "DENY_NO_ENTRY"


@pytest.mark.parametrize("alteration", ["target", "digest", "attempt", "owner"])
def test_t10_s06_f06_exact_binding_rejected(alteration):
    changed = replace(INTENT, **{
        {"target": "target", "digest": "payload_digest",
         "attempt": "attempt_id", "owner": "owner_incarnation"}[alteration]:
        "substituted"
    })
    model = gate()
    assert enter(model, changed).status == "DENY_NO_ENTRY"
    assert model.snapshot()[0] == ()


def test_t10_evidence_digest_mismatch_rejected():
    evidence = (
        SyntheticIssuer("Sanction", 10_000, 10_000, 15_000, "wrong"),
        SyntheticIssuer("VERITAS", 10_000, 10_000, 15_000, INTENT.payload_digest),
    )
    assert enter(gate(issuers=evidence)).status == "DENY_NO_ENTRY"


@pytest.mark.parametrize("offset,expected", [
    (-1, "ENTRY_COMMITTED_ONCE"),
    (0, "DENY_NO_ENTRY"),
    (1, "DENY_NO_ENTRY"),
])
def test_x01_x02_x03_expiry_strict(offset, expected):
    model = gate(
        utc_ms=12_000 + offset, mono_ms=12_000 + offset,
        sanction_check=12_000 + offset, veritas_check=12_000 + offset,
        sanction_mono=12_000 + offset, veritas_mono=12_000 + offset,
        sanction_expiry=12_000, veritas_expiry=12_000,
    )
    assert enter(model).status == expected


def test_x04_uncertainty_upper_reaches_expiry():
    model = gate(
        utc_ms=11_999, mono_ms=11_999,
        sanction_check=11_999, veritas_check=11_999,
        sanction_mono=11_999, veritas_mono=11_999,
        sanction_expiry=12_000, veritas_expiry=12_000,
        uncertainty_ms=1,
    )
    assert enter(model).status == "DENY_NO_ENTRY"


@pytest.mark.parametrize("mode", ["health", "rollback", "skew", "uncertainty"])
def test_x05_x06_clock_faults_fail_closed(mode):
    model = gate()
    if mode == "health":
        model.set_clock_health(False)
    elif mode == "rollback":
        model.advance(-1)
    elif mode == "skew":
        model.advance(1, 0)
    else:
        model.set_uncertainty(-1)
    assert enter(model).status == "DENY_NO_ENTRY"



@pytest.mark.parametrize("fault", ["health", "rollback", "uncertainty"])
def test_clock_fault_cannot_be_cleared_to_rearm_attempt(fault):
    model = gate()
    if fault == "health":
        model.set_clock_health(False)
        model.set_clock_health(True)
    elif fault == "rollback":
        model.advance(-1)
        model.set_clock_health(True)
    else:
        model.set_uncertainty(-1)
        model.set_uncertainty(0)
    assert enter(model).status == "DENY_NO_ENTRY"
    assert model.snapshot()[0] == ()

def test_s01_stop_precedes_entry():
    model = gate()
    model.stop()
    assert enter(model).status == "DENY_NO_ENTRY"
    assert model.snapshot()[1] == ("STOP",)


def test_s02_entry_precedes_stop():
    model = gate()
    decision = enter(model)
    model.stop()
    assert decision.status == "ENTRY_COMMITTED_ONCE"
    assert model.snapshot()[1] == ("E_SIM", "STOP")
    assert enter(model).status == "DENY_NO_ENTRY"


def test_s03_stop_and_entry_have_a_serialized_synthetic_order():
    model = gate()
    barrier = Barrier(2)

    def entry_worker():
        barrier.wait()
        return enter(model)

    def stop_worker():
        barrier.wait()
        model.stop()

    with ThreadPoolExecutor(max_workers=2) as pool:
        entry_future = pool.submit(entry_worker)
        stop_future = pool.submit(stop_worker)
        decision = entry_future.result()
        stop_future.result()
    entries, history, _ = model.snapshot()
    if decision.status == "ENTRY_COMMITTED_ONCE":
        assert history == ("E_SIM", "STOP")
        assert len(entries) == 1
    else:
        assert decision.status == "DENY_NO_ENTRY"
        assert history == ("STOP",)
        assert entries == ()


def test_s05_owner_incarnation_mismatch():
    model = gate()
    assert enter(model, owner="restarted-owner").status == "DENY_NO_ENTRY"


def test_f01_32_concurrent_attempts_at_most_one():
    model = gate()
    with ThreadPoolExecutor(max_workers=32) as pool:
        decisions = list(pool.map(lambda _: enter(model), range(32)))
    assert sum(d.status == "ENTRY_COMMITTED_ONCE" for d in decisions) == 1
    assert sum(d.status == "DENY_NO_ENTRY" for d in decisions) == 31
    assert len(model.snapshot()[0]) == 1


def test_f02_lost_ack_stays_unknown_no_retry():
    model = gate()
    result = enter(model, lose_receipt=True)
    assert result.status == "UNKNOWN_NO_RETRY"
    assert result.receipt is None
    assert len(model.snapshot()[0]) == 1
    assert enter(model).status == "DENY_NO_ENTRY"


def test_f03_failed_attempt_cannot_rearm():
    model = gate()
    assert enter(model, replace(INTENT, target="bad")).status == "DENY_NO_ENTRY"
    assert enter(model).status == "DENY_NO_ENTRY"


def test_f04_interrupted_claim_no_entry_no_retry():
    model = gate()
    assert model.claim_without_entry().status == "UNKNOWN_NO_RETRY"
    assert enter(model).status == "DENY_NO_ENTRY"
    assert model.snapshot()[0] == ()


def test_f11_repeated_attempt_same_gate_denied():
    model = gate()
    assert enter(model).status == "ENTRY_COMMITTED_ONCE"
    assert enter(model).status == "DENY_NO_ENTRY"


def test_negative_split_check_then_pause_is_unsafe():
    """Demonstrate, do not fix, an unguarded split check/commit design."""
    model = gate()
    checked_at = 10_000
    assert checked_at < 15_000  # Unsafe precheck succeeded.
    model.advance(2_001)
    # A broken implementation would append on the old decision.
    # The synthetic gate instead samples at its own E_SIM transition.
    assert enter(model).status == "DENY_NO_ENTRY"
