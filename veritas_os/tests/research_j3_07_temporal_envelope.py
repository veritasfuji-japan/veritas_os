"""J3-07 research-only interval proof obligations for a *hypothetical* entry.

No transport, clock acquisition, trusted runtime, STOP authority or production
integration. A conditional envelope is NOT evidence of E1/E2/E3 admission.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Disposition = Literal["CONDITIONAL_TIME_ENVELOPE", "DENY", "NOT_SCORED"]


@dataclass(frozen=True)
class IssuerSample:
    issuer: str
    checked_utc_ms: int
    checked_mono_ms: int
    expires_utc_ms: int


@dataclass(frozen=True)
class ClockInterval:
    """An assumed snapshot, not an authenticated time source."""

    utc_lower_ms: int
    utc_upper_ms: int
    monotonic_ms: int


@dataclass(frozen=True)
class Assumptions:
    """Proof obligations are explicit; flags are caller assertions, not proof."""

    entry_event: str | None
    clock_root_verified: bool
    issuer_roots_verified: bool
    upper_delay_bound_ms: int | None
    delay_bound_certified: bool
    stop_order_proven: bool
    remote_revocation_visibility_proven: bool
    one_use_proven: bool


@dataclass(frozen=True)
class EnvelopeResult:
    disposition: Disposition
    reason: str
    latest_utc_ms: int | None = None
    latest_mono_ms: int | None = None


def evaluate_conditional_time_envelope(
    samples: tuple[IssuerSample, ...],
    clock: ClockInterval,
    assumptions: Assumptions,
) -> EnvelopeResult:
    """Prove *only* arithmetic feasibility for an assumed bounded delay.

    The entry may occur at any instant in [sample, sample + upper_delay].
    All arithmetic uses integers representing milliseconds. In particular,
    strict expiry requires latest_possible_entry < expiry, not <=.

    Even if all predicates pass, STOP, revocation, physical linearization,
    cryptographic trust and bounded delay remain external proof obligations.
    """
    if (
        type(clock) is not ClockInterval
        or type(assumptions) is not Assumptions
        or any(type(v) is not int for v in (
            clock.utc_lower_ms, clock.utc_upper_ms, clock.monotonic_ms
        ))
        or clock.utc_lower_ms > clock.utc_upper_ms
        or type(samples) is not tuple
        or len(samples) != 2
        or any(type(x) is not IssuerSample for x in samples)
        or {x.issuer for x in samples} != {"Sanction", "VERITAS"}
        or any(type(v) is not int for x in samples for v in (
            x.checked_utc_ms, x.checked_mono_ms, x.expires_utc_ms
        ))
    ):
        return EnvelopeResult("DENY", "MALFORMED_FIXTURE")

    b = assumptions.upper_delay_bound_ms
    if b is None or type(b) is not int or b < 0:
        return EnvelopeResult("NOT_SCORED", "NO_FINITE_DELAY_BOUND")
    if assumptions.delay_bound_certified is not True:
        return EnvelopeResult("NOT_SCORED", "DELAY_BOUND_NOT_CERTIFIED")
    if assumptions.entry_event not in {"E1", "E2", "E3"}:
        return EnvelopeResult("NOT_SCORED", "ENTRY_EVENT_UNDEFINED")
    if not (
        assumptions.clock_root_verified is True
        and assumptions.issuer_roots_verified is True
    ):
        return EnvelopeResult("NOT_SCORED", "TRUST_ROOT_UNVERIFIED")

    latest_utc = clock.utc_upper_ms + b
    latest_mono = clock.monotonic_ms + b
    for sample in samples:
        # Age cannot be negative even at earliest possible entry.
        if (
            clock.utc_lower_ms < sample.checked_utc_ms
            or clock.monotonic_ms < sample.checked_mono_ms
        ):
            return EnvelopeResult("DENY", "CHECK_IN_FUTURE", latest_utc, latest_mono)
        if (
            latest_utc - sample.checked_utc_ms > 2000
            or latest_mono - sample.checked_mono_ms > 2000
        ):
            return EnvelopeResult("DENY", "AGE_UPPER_BOUND_EXCEEDED", latest_utc, latest_mono)
        if latest_utc >= sample.expires_utc_ms:
            return EnvelopeResult("DENY", "STRICT_EXPIRY_NOT_PROVABLE", latest_utc, latest_mono)

    if assumptions.stop_order_proven is not True:
        return EnvelopeResult("NOT_SCORED", "STOP_ORDER_UNPROVEN", latest_utc, latest_mono)
    if assumptions.remote_revocation_visibility_proven is not True:
        return EnvelopeResult(
            "NOT_SCORED", "REMOTE_REVOCATION_UNPROVEN", latest_utc, latest_mono
        )
    if assumptions.one_use_proven is not True:
        return EnvelopeResult("NOT_SCORED", "ONE_USE_UNPROVEN", latest_utc, latest_mono)

    # Even all TRUE booleans cannot verify those assumptions. This is a
    # conditional arithmetic conclusion, never an authorization or admission.
    return EnvelopeResult(
        "CONDITIONAL_TIME_ENVELOPE", "ASSUMED_BOUNDS_ONLY", latest_utc, latest_mono
    )
