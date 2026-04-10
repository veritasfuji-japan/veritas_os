"""Plan #15: prioritized abnormal-path tests for pipeline/routes/rate modules.

Priority order:
1) pipeline_*
2) routes_decide
3) rate_limiting
"""

from __future__ import annotations

from typing import Any

import pytest

from veritas_os.api import rate_limiting as rl
from veritas_os.api import routes_decide as rd
from veritas_os.core.pipeline import pipeline_policy as pp


def test_pipeline_rollout_invalid_canary_percent_logs_and_skips(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Invalid canary_percent should fail safe to skip with a warning."""
    monkeypatch.setattr(pp, "_coerce_policy_enforce_flag", lambda _raw: True)
    monkeypatch.setattr(pp, "_deterministic_bucket_ratio", lambda _key: 0.5)

    decision = {
        "policy_results": [
            {
                "triggered": True,
                "metadata": {
                    "rollout_controls": {
                        "strategy": "canary",
                        "canary_percent": "not-an-int",
                    }
                },
            }
        ]
    }

    with caplog.at_level("WARNING"):
        enforce, state = pp._is_enforcement_enabled_for_rollout(
            {"request_id": "req-plan15"},
            decision,
        )

    assert enforce is False
    assert state == "canary_skip"
    assert "invalid canary_percent" in caplog.text


@pytest.mark.anyio
async def test_routes_replay_endpoint_success_payload_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replay endpoint should return stable success payload fields."""

    class _ReplayResult:
        decision_id = "d-15"
        replay_path = "/tmp/replay/d-15.json"
        match = True
        diff_summary = {"changed": 0}
        replay_time_ms = 12
        schema_version = "1.0"
        severity = "low"
        divergence_level = "none"
        audit_summary = {"ok": True}

    class _DummyServer:
        @staticmethod
        async def verify_signature(*_args: Any, **_kwargs: Any) -> None:
            return None

        @staticmethod
        async def run_replay(*_args: Any, **_kwargs: Any) -> _ReplayResult:
            return _ReplayResult()

    class _DummyRequest:
        headers: dict[str, str] = {}

    monkeypatch.setattr(rd, "_get_server", lambda: _DummyServer())

    response = await rd.replay_endpoint("d-15", _DummyRequest())

    assert response["ok"] is True
    assert response["decision_id"] == "d-15"
    assert response["replay_time_ms"] == 12
    assert response["schema_version"] == "1.0"


def test_rate_nonce_scheduler_start_stop_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nonce scheduler should start once and stop by canceling active timer."""

    class _DummyTimer:
        def __init__(self, _interval: float, _cb: Any) -> None:
            self.daemon = False
            self.started = False
            self.cancelled = False

        def start(self) -> None:
            self.started = True

        def cancel(self) -> None:
            self.cancelled = True

    created: list[_DummyTimer] = []

    def _timer_factory(interval: float, callback: Any) -> _DummyTimer:
        timer = _DummyTimer(interval, callback)
        created.append(timer)
        return timer

    monkeypatch.setattr(rl.threading, "Timer", _timer_factory)

    old_timer = rl._nonce_cleanup_timer
    try:
        rl._nonce_cleanup_timer = None
        rl._start_nonce_cleanup_scheduler()
        rl._start_nonce_cleanup_scheduler()
        assert len(created) == 1
        assert created[0].started is True

        rl._stop_nonce_cleanup_scheduler()
        assert created[0].cancelled is True
        assert rl._nonce_cleanup_timer is None
    finally:
        rl._nonce_cleanup_timer = old_timer
