"""J3-03 inert logical entry oracle; NOT a transport, kernel gate, or authority verifier.

All time and STOP changes in this model are serialized by one Python lock.
The event E_SIM is a logical in-memory append. This does NOT model arbitrary
preemption *inside* the lock, a clock that advances independently of it,
durable storage, authenticated issuer evidence, real transport or real effects.
Never import this research model into production execution paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Literal

DecisionStatus = Literal["DENY_NO_ENTRY", "ENTRY_COMMITTED_ONCE", "UNKNOWN_NO_RETRY"]


@dataclass(frozen=True)
class FrozenIntent:
    attempt_id: str
    target: str
    payload_digest: str
    owner_incarnation: str


@dataclass(frozen=True)
class SyntheticIssuer:
    issuer: str
    checked_utc_ms: int
    checked_mono_ms: int
    expires_utc_ms: int
    binding_digest: str
    authenticated_in_fixture: bool = True


@dataclass(frozen=True)
class EntryReceipt:
    event: Literal["E_SIM"]
    sequence: int
    utc_ms: int
    mono_ms: int
    attempt_id: str
    payload_digest: str
    owner_incarnation: str
    stop_epoch: int


@dataclass(frozen=True)
class Decision:
    status: DecisionStatus
    reason: str
    receipt: EntryReceipt | None = None


class SyntheticEntryGate:
    """Serialized logical state-machine oracle, with no I/O and no persistence.

    The same lock orders synthetic clock mutations, STOP and E_SIM append.
    An external real clock is NOT protected by this lock; hence this model
    cannot establish a preemption-safe real transport linearization point.
    """

    def __init__(
        self,
        *,
        intent: FrozenIntent,
        issuers: tuple[SyntheticIssuer, ...],
        utc_ms: int,
        mono_ms: int,
        uncertainty_ms: int = 0,
    ) -> None:
        if type(intent) is not FrozenIntent or type(issuers) is not tuple:
            raise TypeError("frozen fixture required")
        self._intent = intent
        self._issuers = issuers
        self._utc_ms = utc_ms
        self._mono_ms = mono_ms
        self._uncertainty_ms = uncertainty_ms
        self._healthy = True
        self._consistent = True
        self._stopped = False
        self._stop_epoch = 0
        self._spent = False
        self._entries: list[EntryReceipt] = []
        self._history: list[str] = []
        self._lock = Lock()

    def advance(self, utc_delta_ms: int, mono_delta_ms: int | None = None) -> None:
        """Synthetic clock mutation; negative/skew changes poison clock health."""
        if type(utc_delta_ms) is not int or (
            mono_delta_ms is not None and type(mono_delta_ms) is not int
        ):
            raise TypeError("integer millisecond deltas required")
        if mono_delta_ms is None:
            mono_delta_ms = utc_delta_ms
        with self._lock:
            self._utc_ms += utc_delta_ms
            self._mono_ms += mono_delta_ms
            if utc_delta_ms < 0 or mono_delta_ms < 0:
                self._healthy = False
            if utc_delta_ms != mono_delta_ms:
                self._consistent = False
            self._history.append("CLOCK")

    def set_clock_health(self, healthy: bool) -> None:
        with self._lock:
            self._healthy = healthy is True
            self._history.append("HEALTH")

    def set_uncertainty(self, uncertainty_ms: int) -> None:
        with self._lock:
            self._uncertainty_ms = uncertainty_ms
            self._history.append("UNCERTAINTY")

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            self._stop_epoch += 1
            self._history.append("STOP")

    def attempt_entry(
        self, intent: FrozenIntent, *, owner_incarnation: str,
        lose_receipt: bool = False,
    ) -> Decision:
        """Logically check-and-append E_SIM in one serialized model transition.

        'lose_receipt' simulates a missing caller acknowledgment AFTER append.
        The event is not an external send; the attempt cannot be retried.
        """
        with self._lock:
            if self._spent:
                return Decision("DENY_NO_ENTRY", "ALREADY_SPENT")
            self._spent = True
            if (
                type(intent) is not FrozenIntent
                or intent != self._intent
                or type(owner_incarnation) is not str
                or owner_incarnation != self._intent.owner_incarnation
            ):
                return Decision("DENY_NO_ENTRY", "BINDING_OR_OWNER_MISMATCH")
            if self._stopped:
                return Decision("DENY_NO_ENTRY", "STOP_EFFECTIVE")
            if (
                not self._healthy or not self._consistent
                or type(self._uncertainty_ms) is not int
                or self._uncertainty_ms < 0
            ):
                return Decision("DENY_NO_ENTRY", "CLOCK_UNTRUSTED")
            if len(self._issuers) != 2 or {
                e.issuer for e in self._issuers if type(e) is SyntheticIssuer
            } != {"Sanction", "VERITAS"}:
                return Decision("DENY_NO_ENTRY", "ISSUER_SET_INVALID")
            lower = self._utc_ms - self._uncertainty_ms
            upper = self._utc_ms + self._uncertainty_ms
            for evidence in self._issuers:
                if (
                    type(evidence) is not SyntheticIssuer
                    or evidence.authenticated_in_fixture is not True
                    or evidence.binding_digest != intent.payload_digest
                ):
                    return Decision("DENY_NO_ENTRY", "ISSUER_EVIDENCE_INVALID")
                # Conservative age and expiry checks for the simulated UTC
                # interval; monotonic age is checked independently.
                if not (
                    0 <= lower - evidence.checked_utc_ms
                    and upper - evidence.checked_utc_ms <= 2000
                    and 0 <= self._mono_ms - evidence.checked_mono_ms <= 2000
                    and upper < evidence.expires_utc_ms
                ):
                    return Decision("DENY_NO_ENTRY", "TIME_OR_EXPIRY_INVALID")
            # E_SIM: conceptual atomic state-machine transition, NOT a real
            # clock read plus physical transport operation.
            receipt = EntryReceipt(
                event="E_SIM",
                sequence=len(self._entries) + 1,
                utc_ms=self._utc_ms,
                mono_ms=self._mono_ms,
                attempt_id=intent.attempt_id,
                payload_digest=intent.payload_digest,
                owner_incarnation=intent.owner_incarnation,
                stop_epoch=self._stop_epoch,
            )
            self._entries.append(receipt)
            self._history.append("E_SIM")
            if lose_receipt:
                return Decision("UNKNOWN_NO_RETRY", "ACK_LOST")
            return Decision("ENTRY_COMMITTED_ONCE", "SYNTHETIC_ONLY", receipt)

    def claim_without_entry(self) -> Decision:
        """Synthetic interrupted attempt; no persistence or crash is modeled."""
        with self._lock:
            if self._spent:
                return Decision("DENY_NO_ENTRY", "ALREADY_SPENT")
            self._spent = True
            self._history.append("CLAIM_INTERRUPTED")
            return Decision("UNKNOWN_NO_RETRY", "INTERRUPTED_BEFORE_E_SIM")

    def snapshot(self) -> tuple[tuple[EntryReceipt, ...], tuple[str, ...], bool]:
        with self._lock:
            return tuple(self._entries), tuple(self._history), self._spent
