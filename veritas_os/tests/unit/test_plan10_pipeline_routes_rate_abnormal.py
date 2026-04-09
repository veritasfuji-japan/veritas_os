"""Plan #10: abnormal-path tests for pipeline/routes/rate modules."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from veritas_os.api import rate_limiting as rl
from veritas_os.api import routes_decide as rd
from veritas_os.core.pipeline import pipeline_execute as pe
from veritas_os.core.pipeline.pipeline_types import PipelineContext


@pytest.mark.anyio
async def test_stage_core_execute_stops_at_max_healing_iterations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Self-healing should stop safely when rejection persists across retries."""
    from veritas_os.core.pipeline import self_healing

    ctx = PipelineContext(query="q", request_id="req-max", context={})

    def _rejected_payload() -> dict[str, Any]:
        return {
            "fuji": {
                "rejection": {
                    "status": "REJECTED",
                    "error": {"code": "policy_error"},
                    "feedback": {"action": "revise"},
                }
            }
        }

    monkeypatch.setattr(self_healing, "is_healing_enabled", lambda _ctx: True)
    monkeypatch.setattr(self_healing, "load_healing_state", lambda _req_id: SimpleNamespace(attempt=0))
    monkeypatch.setattr(self_healing, "HealingBudget", lambda: SimpleNamespace())
    monkeypatch.setattr(
        self_healing,
        "decide_healing_action",
        lambda **_kwargs: SimpleNamespace(
            allow=True,
            stop_reason=None,
            reason="retry",
            action=SimpleNamespace(value="retry"),
        ),
    )
    monkeypatch.setattr(self_healing, "build_healing_input", lambda **_kwargs: {"patched": True})
    monkeypatch.setattr(self_healing, "healing_input_signature", lambda _inp: "sig")
    monkeypatch.setattr(self_healing, "diff_summary", lambda *_args, **_kwargs: "diff")
    monkeypatch.setattr(self_healing, "check_guardrails", lambda **_kwargs: None)
    monkeypatch.setattr(self_healing, "budget_remaining", lambda *_args, **_kwargs: {"remaining": 1})
    monkeypatch.setattr(self_healing, "build_healing_trust_log_entry", lambda **_kwargs: {"kind": "heal"})
    monkeypatch.setattr(self_healing, "advance_state", lambda **_kwargs: None)
    monkeypatch.setattr(self_healing, "persist_healing_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(self_healing, "clear_healing_state", lambda _req_id: None)

    async def _call_core_decide_fn(**_kwargs: Any) -> dict[str, Any]:
        return _rejected_payload()

    await pe.stage_core_execute(
        ctx,
        call_core_decide_fn=_call_core_decide_fn,
        append_trust_log_fn=lambda _entry: None,
        veritas_core=SimpleNamespace(decide=lambda **_kwargs: {}),
    )

    assert ctx.healing_stop_reason == "max_iterations_exceeded"
    assert len(ctx.healing_attempts) == 20


@pytest.mark.anyio
async def test_replay_decision_endpoint_returns_500_when_pipeline_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replay endpoint should map replay exceptions to a stable 500 payload."""

    class _DummyPipeline:
        @staticmethod
        async def replay_decision(**_kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("replay failure")

    class _DummyServer:
        @staticmethod
        def get_decision_pipeline() -> _DummyPipeline:
            return _DummyPipeline()

    class _DummyRequest:
        query_params: dict[str, str] = {}

    monkeypatch.setattr(rd, "_get_server", lambda: _DummyServer())

    response = await rd.replay_decision_endpoint("decision-x", _DummyRequest())

    assert response.status_code == 500
    assert b"replay_failed" in response.body


def test_call_fuji_supports_action_only_validate_fallback() -> None:
    """FUJI adapter should support validate(action) fallback after TypeErrors."""

    class _FujiCore:
        @staticmethod
        def validate(*_args: Any, **kwargs: Any) -> dict[str, Any]:
            if kwargs:
                raise TypeError("keywords unsupported")
            if len(_args) == 2:
                raise TypeError("context unsupported")
            return {"status": "ok", "used": "action_only"}

    out = rd._call_fuji(_FujiCore(), "block", {"foo": "bar"})

    assert out == {"status": "ok", "used": "action_only"}


def test_schedule_nonce_cleanup_reschedules_even_after_cleanup_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nonce scheduler should continue operating after one cleanup exception."""

    class _DummyTimer:
        def __init__(self, interval: float, callback: Any) -> None:
            self.interval = interval
            self.callback = callback
            self.daemon = False
            self.started = False

        def start(self) -> None:
            self.started = True

        def cancel(self) -> None:
            self.started = False

    created: list[_DummyTimer] = []

    def _timer_factory(interval: float, callback: Any) -> _DummyTimer:
        timer = _DummyTimer(interval, callback)
        created.append(timer)
        return timer

    monkeypatch.setattr(rl, "_cleanup_nonces", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(rl.threading, "Timer", _timer_factory)

    old_timer = rl._nonce_cleanup_timer
    try:
        rl._nonce_cleanup_timer = object()
        rl._schedule_nonce_cleanup()
    finally:
        rl._nonce_cleanup_timer = old_timer

    assert len(created) == 1
    assert created[0].interval == 60.0
    assert created[0].started is True
