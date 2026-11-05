"""TASK-J3-04: inert AF_UNIX socketpair seam harness, research-only.

E_SIM (J3-03 logical admission) is followed by a separately scheduled local
socket.send() call. A test-controlled pause exposes the gap. The socketpair
never uses DNS, IP, TLS, a provider or an external network interface.

A successful socket.send() is evidence of a successful LOCAL syscall return,
NOT an independently instrumented kernel linearization point (E1), physical
transmission (E2), receiver admission (E3), or an external effect (E4).
Do not import this harness from production code.
"""

from __future__ import annotations

from dataclasses import dataclass
import socket
from threading import Event
from time import monotonic_ns

from veritas_os.tests.research_j3_03_entry_gate import (
    Decision, FrozenIntent, SyntheticEntryGate,
)


@dataclass(frozen=True)
class LocalSendObservation:
    decision: Decision
    after_gate_ns: int
    before_send_ns: int | None
    after_send_ns: int | None
    bytes_accepted_by_local_call: int
    error: str | None

    @property
    def local_send_returned(self) -> bool:
        return (
            self.before_send_ns is not None
            and self.after_send_ns is not None
            and self.error is None
            and self.bytes_accepted_by_local_call > 0
        )


def send_after_synthetic_gate(
    *,
    gate: SyntheticEntryGate,
    intent: FrozenIntent,
    sender: socket.socket,
    payload: bytes,
    gate_reached: Event,
    resume: Event,
    wait_timeout_seconds: float = 10.0,
) -> LocalSendObservation:
    """Single worker invocation; the caller controls the post-gate pause.

    This intentionally does NOT revalidate after E_SIM, because it is a
    counterexample harness for a split gate/send architecture. Never use it
    as a candidate implementation.
    """
    if type(payload) is not bytes or not payload:
        raise ValueError("inert nonempty bytes payload required")
    if sender.family != socket.AF_UNIX:
        raise ValueError("AF_UNIX local socket required")

    decision = gate.attempt_entry(
        intent, owner_incarnation=intent.owner_incarnation
    )
    after_gate_ns = monotonic_ns()
    gate_reached.set()
    if decision.status != "ENTRY_COMMITTED_ONCE":
        return LocalSendObservation(decision, after_gate_ns, None, None, 0, None)

    if not resume.wait(timeout=wait_timeout_seconds):
        # The right was already spent. No new entry is permitted.
        return LocalSendObservation(
            decision, after_gate_ns, None, None, 0, "PAUSE_TIMEOUT"
        )

    before_send_ns = monotonic_ns()
    try:
        # Tiny inert payload; no provider, no TCP/IP, no external network.
        count = sender.send(payload)
    except OSError as exc:
        return LocalSendObservation(
            decision, after_gate_ns, before_send_ns,
            monotonic_ns(), 0, type(exc).__name__
        )
    after_send_ns = monotonic_ns()
    return LocalSendObservation(
        decision, after_gate_ns, before_send_ns, after_send_ns, count, None
    )
