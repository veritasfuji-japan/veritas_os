"""J3-04: AF_UNIX socketpair counterexamples, NO external network or effects."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import socket
from threading import Event
from time import monotonic_ns, sleep

import pytest

from veritas_os.tests.research_j3_03_entry_gate import (
    FrozenIntent, SyntheticEntryGate, SyntheticIssuer,
)
from veritas_os.tests.research_j3_04_local_socket_seam import (
    send_after_synthetic_gate,
)

pytestmark = pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX"), reason="requires AF_UNIX socketpair"
)

INTENT = FrozenIntent("j3-04-attempt", "local-only", "fixture-digest", "owner-1")
PAYLOAD = b"INERT-J3-04-ONLY"


@contextmanager
def local_pair():
    left, right = socket.socketpair()
    try:
        yield left, right
    finally:
        left.close()
        right.close()


def gate():
    issuers = (
        SyntheticIssuer("Sanction", 10_000, 10_000, 15_000, INTENT.payload_digest),
        SyntheticIssuer("VERITAS", 10_000, 10_000, 15_000, INTENT.payload_digest),
    )
    return SyntheticEntryGate(
        intent=INTENT, issuers=issuers, utc_ms=10_000, mono_ms=10_000
    )


def start(pool, model, sender, payload=PAYLOAD, *, timeout=10.0):
    reached = Event()
    resume = Event()
    future = pool.submit(
        send_after_synthetic_gate,
        gate=model, intent=INTENT, sender=sender, payload=payload,
        gate_reached=reached, resume=resume, wait_timeout_seconds=timeout,
    )
    assert reached.wait(timeout=5), "worker must reach the post-gate seam"
    return future, resume


def test_j3_04_local_socket_positive_call_return_is_not_e1_proof():
    model = gate()
    with local_pair() as pair:
        sender, receiver = pair
        with ThreadPoolExecutor(max_workers=1) as pool:
            future, resume = start(pool, model, sender)
            resume.set()
            observation = future.result(timeout=5)
        receiver.settimeout(1)
        assert receiver.recv(len(PAYLOAD)) == PAYLOAD
    assert observation.decision.status == "ENTRY_COMMITTED_ONCE"
    assert observation.local_send_returned
    assert observation.bytes_accepted_by_local_call == len(PAYLOAD)
    assert observation.after_gate_ns <= observation.before_send_ns
    assert observation.before_send_ns <= observation.after_send_ns
    assert model.snapshot()[1] == ("E_SIM",)


def test_j3_04_stop_after_e_sim_before_local_send_does_not_cancel_bytes():
    model = gate()
    with local_pair() as pair:
        sender, receiver = pair
        with ThreadPoolExecutor(max_workers=1) as pool:
            future, resume = start(pool, model, sender)
            model.stop()  # STOP is effective in the logical gate BEFORE send().
            stopped_at_ns = monotonic_ns()
            assert model.snapshot()[1] == ("E_SIM", "STOP")
            resume.set()
            observation = future.result(timeout=5)
        receiver.settimeout(1)
        assert receiver.recv(len(PAYLOAD)) == PAYLOAD
    assert observation.local_send_returned
    assert observation.before_send_ns >= stopped_at_ns
    assert model.attempt_entry(
        INTENT, owner_incarnation=INTENT.owner_incarnation
    ).status == "DENY_NO_ENTRY"


def test_j3_04_real_monotonic_pause_over_two_seconds_after_e_sim():
    """Real elapsed time crosses 2000ms, despite unchanged synthetic clock."""
    model = gate()
    with local_pair() as pair:
        sender, receiver = pair
        with ThreadPoolExecutor(max_workers=1) as pool:
            future, resume = start(pool, model, sender)
            # Deliberately slow research test: independent physical monotonic
            # time passes while the synthetic gate's time remains frozen.
            sleep(2.05)
            resume.set()
            observation = future.result(timeout=5)
        receiver.settimeout(1)
        assert receiver.recv(len(PAYLOAD)) == PAYLOAD
    assert observation.decision.status == "ENTRY_COMMITTED_ONCE"
    assert observation.local_send_returned
    assert observation.before_send_ns - observation.after_gate_ns >= 2_000_000_000
    assert model.snapshot()[1] == ("E_SIM",)


def test_j3_04_stop_before_e_sim_blocks_local_send():
    model = gate()
    model.stop()
    with local_pair() as pair:
        sender, receiver = pair
        with ThreadPoolExecutor(max_workers=1) as pool:
            future, _resume = start(pool, model, sender)
            observation = future.result(timeout=5)
        receiver.setblocking(False)
        with pytest.raises(BlockingIOError):
            receiver.recv(1)
    assert observation.decision.status == "DENY_NO_ENTRY"
    assert not observation.local_send_returned
    assert model.snapshot()[0] == ()


def test_j3_04_pause_timeout_spends_attempt_without_local_send():
    model = gate()
    with local_pair() as pair:
        sender, receiver = pair
        with ThreadPoolExecutor(max_workers=1) as pool:
            future, _resume = start(pool, model, sender, timeout=0.1)
            observation = future.result(timeout=5)
        receiver.setblocking(False)
        with pytest.raises(BlockingIOError):
            receiver.recv(1)
    assert observation.decision.status == "ENTRY_COMMITTED_ONCE"
    assert observation.error == "PAUSE_TIMEOUT"
    assert not observation.local_send_returned
    assert model.attempt_entry(
        INTENT, owner_incarnation=INTENT.owner_incarnation
    ).status == "DENY_NO_ENTRY"


def test_j3_04_receiver_closed_after_e_sim_local_send_failure_no_retry():
    model = gate()
    with local_pair() as pair:
        sender, receiver = pair
        with ThreadPoolExecutor(max_workers=1) as pool:
            future, resume = start(pool, model, sender)
            receiver.close()
            resume.set()
            observation = future.result(timeout=5)
    assert observation.decision.status == "ENTRY_COMMITTED_ONCE"
    assert not observation.local_send_returned
    assert observation.error is not None
    assert model.attempt_entry(
        INTENT, owner_incarnation=INTENT.owner_incarnation
    ).status == "DENY_NO_ENTRY"


def test_j3_04_opaque_digest_does_not_authenticate_sent_bytes():
    """Explicit nonconformance: gate never verifies bytes against digest."""
    model = gate()
    altered = b"INERT-ALTERED"
    with local_pair() as pair:
        sender, receiver = pair
        with ThreadPoolExecutor(max_workers=1) as pool:
            future, resume = start(pool, model, sender, altered)
            resume.set()
            observation = future.result(timeout=5)
        receiver.settimeout(1)
        assert receiver.recv(len(altered)) == altered
    assert observation.local_send_returned
    assert observation.decision.receipt.payload_digest == INTENT.payload_digest
    assert altered != PAYLOAD
