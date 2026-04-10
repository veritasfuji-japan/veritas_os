"""Plan #14: prioritized abnormal-path tests for pipeline/routes/rate modules.

This suite follows the requested priority order:
1) pipeline_* helpers
2) routes_decide endpoints
3) rate_limiting schedulers
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from veritas_os.api import rate_limiting as rl
from veritas_os.api import routes_decide as rd
from veritas_os.core.pipeline import pipeline_policy as pp


def test_pipeline_rollout_unknown_strategy_falls_back_to_safe_full(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unknown rollout strategy must enforce safely and emit warning."""
    decision = {
        "policy_results": [
            {
                "triggered": True,
                "metadata": {"rollout_controls": {"strategy": "mystery_mode"}},
            }
        ]
    }

    with caplog.at_level("WARNING"):
        enforce, state = pp._is_enforcement_enabled_for_rollout(
            {"policy_runtime_enforce": True},
            decision,
        )

    assert enforce is True
    assert state == "full_unknown_strategy"
    assert "unknown rollout strategy" in caplog.text


@pytest.mark.anyio
async def test_routes_replay_decision_query_param_error_defaults_to_mock_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Query-params failure should default mock_external_apis to True."""
    captured: dict[str, Any] = {}

    class _Pipeline:
        @staticmethod
        async def replay_decision(**kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"match": True, "replay_time_ms": 1, "diff": {}}

    class _Server:
        @staticmethod
        def get_decision_pipeline() -> _Pipeline:
            return _Pipeline()

    class _BrokenQueryParams:
        @staticmethod
        def get(_key: str) -> Any:
            raise RuntimeError("query parse failure")

    request = SimpleNamespace(query_params=_BrokenQueryParams())
    monkeypatch.setattr(rd, "_get_server", lambda: _Server)

    response = await rd.replay_decision_endpoint("d-14", request)

    assert response == {"match": True, "replay_time_ms": 1, "diff": {}}
    assert captured["decision_id"] == "d-14"
    assert captured["mock_external_apis"] is True


def test_rate_nonce_scheduler_logs_when_cleanup_raises(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Nonce scheduler should warn and still schedule next timer."""
    monkeypatch.setattr(
        rl,
        "_cleanup_nonces",
        lambda: (_ for _ in ()).throw(RuntimeError("cleanup boom")),
    )

    started = {"value": False}

    class _DummyTimer:
        daemon = False

        def __init__(self, _interval: float, _cb: Any) -> None:
            self.interval = _interval
            self.cb = _cb

        def start(self) -> None:
            started["value"] = True

    monkeypatch.setattr(rl.threading, "Timer", _DummyTimer)

    old_timer = rl._nonce_cleanup_timer
    try:
        rl._nonce_cleanup_timer = object()  # type: ignore[assignment]
        with caplog.at_level("WARNING"):
            rl._schedule_nonce_cleanup()
    finally:
        rl._nonce_cleanup_timer = old_timer

    assert "nonce cleanup failed" in caplog.text
    assert started["value"] is True
