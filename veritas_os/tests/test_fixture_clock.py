"""Controlled issuance must not depend on slow CI accidentally pacing it."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from veritas_os.tests.helpers import fixture_clock as module


@pytest.mark.parametrize("offset", [-1, 0, 3])
def test_fixture_waits_for_actual_utc(monkeypatch, offset):
    start = datetime(2026, 9, 20, tzinfo=UTC)
    elapsed = [0.0]
    monkeypatch.setattr(module, "datetime", SimpleNamespace(
        now=lambda _: start + timedelta(seconds=elapsed[0]),
    ))
    monkeypatch.setattr(module, "time", SimpleNamespace(
        monotonic=lambda: elapsed[0],
        sleep=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds),
    ))
    module.wait_for_fixture_issuance(start + timedelta(seconds=offset))
    assert start + timedelta(seconds=elapsed[0]) >= start + timedelta(seconds=offset)
    assert elapsed[0] < max(0, offset) + 0.1


def test_stalled_utc_fails_within_bound(monkeypatch):
    start = datetime(2026, 9, 20, tzinfo=UTC)
    elapsed = [0.0]
    monkeypatch.setattr(module, "datetime", SimpleNamespace(now=lambda _: start))
    monkeypatch.setattr(module, "time", SimpleNamespace(
        monotonic=lambda: elapsed[0],
        sleep=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds),
    ))
    with pytest.raises(TimeoutError, match="ahead of real UTC"):
        module.wait_for_fixture_issuance(start + timedelta(seconds=3))
    assert elapsed[0] == 5.0


def test_naive_issuance_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        module.wait_for_fixture_issuance(datetime(2026, 9, 20))
