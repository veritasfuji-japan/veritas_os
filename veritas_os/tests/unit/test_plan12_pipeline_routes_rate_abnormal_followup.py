"""Plan #12: follow-up abnormal-path tests for pipeline/routes/rate modules."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.responses import JSONResponse

from veritas_os.api import rate_limiting as rl
from veritas_os.api import routes_decide as rd
from veritas_os.core.pipeline import pipeline_execute as pe
from veritas_os.core.pipeline.pipeline_types import PipelineContext


def test_schedule_nonce_cleanup_logs_and_stops_when_timer_cleared(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Nonce scheduler should survive cleanup failures and avoid rescheduling when stopped."""

    def _boom() -> None:
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(rl, "_cleanup_nonces", _boom)
    monkeypatch.setattr(rl, "_nonce_cleanup_timer", object())

    class _DummyTimer:
        daemon = False

        def start(self) -> None:
            raise AssertionError("timer should not start when scheduler was stopped")

    monkeypatch.setattr(rl.threading, "Timer", lambda _i, _cb: _DummyTimer())

    with rl._nonce_cleanup_timer_lock:
        rl._nonce_cleanup_timer = None
    with caplog.at_level("WARNING"):
        rl._schedule_nonce_cleanup()

    assert "nonce cleanup failed" in caplog.text


def test_enforce_rate_limit_rejects_exceeded_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rate limiting should return HTTP 429 when auth store reports quota exceeded."""
    reasons: list[str] = []
    monkeypatch.setattr(rl, "_auth_store_increment_rate_limit", lambda **_kwargs: True)
    monkeypatch.setattr(rl, "_record_auth_reject_reason", reasons.append)

    with pytest.raises(Exception) as exc_info:  # fastapi.HTTPException
        rl.enforce_rate_limit(" api-key ")

    err = exc_info.value
    assert getattr(err, "status_code", None) == 429
    assert reasons == ["rate_limit_exceeded"]


def test_call_fuji_falls_back_to_positional_validate_action() -> None:
    """_call_fuji should retry validate_action with positional args after TypeError."""

    class _FujiCore:
        @staticmethod
        def validate_action(*args: Any, **kwargs: Any) -> dict[str, str]:
            if kwargs:
                raise TypeError("keyword args unsupported")
            return {"status": "allow", "action": args[0], "context": str(args[1])}

    result = rd._call_fuji(_FujiCore(), "approve", {"risk": "low"})

    assert result["status"] == "allow"
    assert result["action"] == "approve"


@pytest.mark.anyio
async def test_replay_decision_endpoint_defaults_mock_true_on_query_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replay endpoint should fail-safe to mock_external_apis=True on query parsing errors."""

    class _DummyPipeline:
        async def replay_decision(self, *, decision_id: str, mock_external_apis: bool) -> dict[str, Any]:
            return {"decision_id": decision_id, "mock_external_apis": mock_external_apis}

    class _DummyServer:
        @staticmethod
        def get_decision_pipeline() -> _DummyPipeline:
            return _DummyPipeline()

    class _BrokenQuery:
        @staticmethod
        def get(_key: str) -> str:
            raise RuntimeError("query unavailable")

    class _DummyRequest:
        query_params = _BrokenQuery()

    monkeypatch.setattr(rd, "_get_server", lambda: _DummyServer())

    response = await rd.replay_decision_endpoint("decision-1", _DummyRequest())

    assert response["decision_id"] == "decision-1"
    assert response["mock_external_apis"] is True


def test_fuji_validate_returns_500_when_core_interface_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fuji_validate should return 500 when Fuji core lacks expected validation methods."""

    class _FujiCoreWithoutMethods:
        pass

    class _DummyServer:
        _fuji_state = SimpleNamespace(err=None)
        _publish_event = staticmethod(lambda *_args, **_kwargs: None)

        @staticmethod
        def get_fuji_core() -> _FujiCoreWithoutMethods:
            return _FujiCoreWithoutMethods()

    monkeypatch.setattr(rd, "_is_direct_fuji_api_enabled", lambda: True)
    monkeypatch.setattr(rd, "_get_server", lambda: _DummyServer())

    response = rd.fuji_validate({"action": "approve", "context": {}})

    assert isinstance(response, JSONResponse)
    assert response.status_code == 500
    assert b"FUJI core interface error" in response.body


@pytest.mark.anyio
async def test_stage_core_execute_marks_retry_execution_failed_on_retry_exception() -> None:
    """Self-healing should capture retry errors and store stable stop_reason metadata."""
    from veritas_os.core.pipeline import self_healing

    ctx = PipelineContext(query="q", request_id="req-retry", context={})
    persisted_states: list[tuple[str, Any]] = []

    monkeypatches = {
        "is_healing_enabled": lambda _ctx: True,
        "load_healing_state": lambda _req_id: SimpleNamespace(attempt=0),
        "HealingBudget": lambda: SimpleNamespace(),
        "decide_healing_action": lambda **_kwargs: SimpleNamespace(
            allow=True,
            stop_reason=None,
            reason="retry",
            action=SimpleNamespace(value="retry"),
        ),
        "build_healing_input": lambda **_kwargs: {"patched": True},
        "healing_input_signature": lambda _inp: "sig-1",
        "diff_summary": lambda *_args, **_kwargs: "diff",
        "check_guardrails": lambda **_kwargs: None,
        "budget_remaining": lambda *_args, **_kwargs: {"remaining": 1},
        "build_healing_trust_log_entry": lambda **_kwargs: {"kind": "heal"},
        "clear_healing_state": lambda _req_id: None,
        "advance_state": lambda **_kwargs: None,
        "persist_healing_state": lambda req_id, state: persisted_states.append((req_id, state)),
    }
    for name, fn in monkeypatches.items():
        setattr(self_healing, name, fn)

    calls = {"count": 0}

    async def _call_core_decide_fn(**_kwargs: Any) -> dict[str, Any]:
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "fuji": {
                    "rejection": {
                        "status": "REJECTED",
                        "error": {"code": "policy_error"},
                        "feedback": {"action": "revise"},
                    }
                }
            }
        raise RuntimeError("retry backend unavailable")

    await pe.stage_core_execute(
        ctx,
        call_core_decide_fn=_call_core_decide_fn,
        append_trust_log_fn=lambda _entry: None,
        veritas_core=SimpleNamespace(decide=lambda **_kwargs: {}),
    )

    assert ctx.healing_stop_reason == "retry_execution_failed"
    assert ctx.response_extras["self_healing"]["stop_reason"] == "retry_execution_failed"
    assert persisted_states and persisted_states[0][0] == "req-retry"
