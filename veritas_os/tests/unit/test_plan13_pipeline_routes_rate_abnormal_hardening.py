"""Plan #13: hardening tests for sub-80 pipeline/routes/rate abnormal branches."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from veritas_os.api import rate_limiting as rl
from veritas_os.api import routes_decide as rd
from veritas_os.core.pipeline import pipeline_policy as pp
from veritas_os.core.pipeline.pipeline_types import PipelineContext


def test_rollout_auto_promotion_handles_invalid_timestamp(caplog: pytest.LogCaptureFixture) -> None:
    """Invalid ISO timestamp should be ignored safely in rollout auto-promotion."""
    with caplog.at_level("WARNING"):
        promoted = pp._is_rollout_auto_promoted({"full_enforce_after": "not-a-date"})

    assert promoted is False
    assert "invalid full_enforce_after" in caplog.text


def test_compiled_policy_bridge_logs_when_deny_is_not_enforced(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Bridge should warn and keep status unchanged when enforcement is disabled."""

    class _Decision:
        @staticmethod
        def to_dict() -> dict[str, Any]:
            return {
                "final_outcome": "deny",
                "policy_results": [],
            }

    monkeypatch.setattr(pp, "load_runtime_bundle", lambda _path: object())
    monkeypatch.setattr(pp, "evaluate_runtime_policies", lambda _bundle, _ctx: _Decision())

    ctx = PipelineContext(
        query="q",
        request_id="req-plan13",
        context={
            "compiled_policy_bundle_dir": "/tmp/bundle",
            "policy_runtime_enforce": False,
        },
        fuji_dict={"status": "allow", "reasons": []},
    )

    with caplog.at_level("WARNING"):
        pp._apply_compiled_policy_runtime_bridge(ctx)

    assert ctx.fuji_dict["status"] == "allow"
    assert "not enforced" in caplog.text


@pytest.mark.anyio
async def test_decide_pipeline_unavailable_resets_lazy_state_when_mutated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unavailable pipeline path should reset lazy state and return 503 payload."""

    class _DummyServer:
        class _LazyState:
            def __init__(self) -> None:
                self.obj = "reset"
                self.attempted = False
                self.err = None

        _pipeline_state = SimpleNamespace(obj=None, attempted=True, err=RuntimeError("broken"))

        @staticmethod
        def get_decision_pipeline() -> None:
            return None

        @staticmethod
        def _publish_event(*_args: Any, **_kwargs: Any) -> None:
            return None

    req = SimpleNamespace(
        query="query",
        fast_mode=False,
        context={"intent": "test"},
    )
    request = SimpleNamespace(state=SimpleNamespace(user_id="u1"))

    monkeypatch.setattr(rd, "_get_server", lambda: _DummyServer)

    response = await rd.decide(req, request)

    assert response.status_code == 503
    assert isinstance(_DummyServer._pipeline_state, _DummyServer._LazyState)


def test_schedule_rate_bucket_cleanup_stops_when_timer_is_cleared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rate scheduler should skip creating a next timer when scheduler is stopped."""
    monkeypatch.setattr(rl, "_cleanup_rate_bucket", lambda: None)

    class _DummyTimer:
        daemon = False

        def start(self) -> None:
            raise AssertionError("timer should not start when scheduler is stopped")

    monkeypatch.setattr(rl.threading, "Timer", lambda _i, _cb: _DummyTimer())

    with rl._rate_cleanup_timer_lock:
        rl._rate_cleanup_timer = None

    rl._schedule_rate_bucket_cleanup()


def test_stop_rate_cleanup_scheduler_cancels_existing_timer() -> None:
    """Stopping rate scheduler should cancel active timer and clear reference."""

    class _DummyTimer:
        def __init__(self) -> None:
            self.cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

    timer = _DummyTimer()
    old_timer = rl._rate_cleanup_timer
    try:
        rl._rate_cleanup_timer = timer  # type: ignore[assignment]
        rl._stop_rate_cleanup_scheduler()
    finally:
        rl._rate_cleanup_timer = old_timer

    assert timer.cancelled is True
