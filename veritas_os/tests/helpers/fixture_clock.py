"""Bounded synchronization of synthetic issuance timestamps with real CI UTC."""

from datetime import UTC, datetime
import time


def wait_for_fixture_issuance(issued_at: datetime) -> None:
    """Wait at most five seconds for the fixture's future issuance timestamp.

    This only paces controlled test setup. Consumption and dispatch still use
    actual UTC and their unchanged production clock/expiry checks.
    """
    if issued_at.tzinfo is None or issued_at.utcoffset() is None:
        raise ValueError("fixture issuance must be timezone-aware")
    deadline = time.monotonic() + 5.0
    while datetime.now(UTC) < issued_at:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("fixture issuance remains ahead of real UTC")
        time.sleep(min(0.05, remaining))
