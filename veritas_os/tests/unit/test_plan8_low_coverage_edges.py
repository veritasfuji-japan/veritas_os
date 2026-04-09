"""Edge-case tests for low-coverage modules in plan item #8."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from veritas_os.api import rate_limiting as rl
from veritas_os.api import routes_decide as rd
from veritas_os.core.pipeline import pipeline_execute as pe
from veritas_os.core.pipeline import pipeline_gate as pg
from veritas_os.core.pipeline import pipeline_response as pr
from veritas_os.core.pipeline.pipeline_types import PipelineContext


@dataclass
class _DummyPipeline:
    """Minimal replay pipeline stub used by replay endpoint tests."""

    seen_mock_external_apis: bool | None = None

    async def replay_decision(
        self,
        *,
        decision_id: str,
        mock_external_apis: bool,
    ) -> dict[str, Any]:
        self.seen_mock_external_apis = mock_external_apis
        return {
            "decision_id": decision_id,
            "mock_external_apis": mock_external_apis,
        }


class _BrokenQueryParams:
    def get(self, _key: str) -> str:
        raise RuntimeError("query params unavailable")


class _DummyRequest:
    query_params = _BrokenQueryParams()


@pytest.mark.anyio
async def test_replay_decision_endpoint_query_params_error_defaults_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When query param access fails, replay endpoint should fail closed to True."""
    dummy_pipeline = _DummyPipeline()

    class _DummyServer:
        @staticmethod
        def get_decision_pipeline() -> _DummyPipeline:
            return dummy_pipeline

    monkeypatch.setattr(rd, "_get_server", lambda: _DummyServer())

    out = await rd.replay_decision_endpoint("dec-1", _DummyRequest())

    assert out["decision_id"] == "dec-1"
    assert out["mock_external_apis"] is True
    assert dummy_pipeline.seen_mock_external_apis is True


def test_finalize_evidence_invalid_payload_falls_back_to_empty_list() -> None:
    """Invalid evidence payload shapes should degrade to empty evidence safely."""

    class _BadIterable:
        def __iter__(self):
            raise TypeError("bad iterable")

    payload: dict[str, Any] = {"evidence": _BadIterable()}
    pr.finalize_evidence(payload, web_evidence=[], evidence_max=5)

    assert payload["evidence"] == []


def test_allow_prob_handles_invalid_predict_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid gate prediction payloads should map to a safe default probability."""
    monkeypatch.setattr(pg, "predict_gate_label", lambda _text: "not-a-dict")

    assert pg._allow_prob("sample") == 0.0


def test_schedule_rate_bucket_cleanup_logs_and_reschedules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scheduler keeps running even when a cleanup pass raises an exception."""

    class _DummyTimer:
        def __init__(self, interval: float, callback: Any):
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

    monkeypatch.setattr(rl, "_cleanup_rate_bucket", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(rl.threading, "Timer", _timer_factory)

    old_timer = rl._rate_cleanup_timer
    try:
        rl._rate_cleanup_timer = object()
        rl._schedule_rate_bucket_cleanup()
    finally:
        rl._rate_cleanup_timer = old_timer

    assert len(created) == 1
    assert created[0].interval == rl._RATE_CLEANUP_INTERVAL
    assert created[0].started is True


def test_cleanup_nonces_unsafe_uses_fallback_on_invalid_server_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid nonce max override should fall back to module default safely."""
    now = 1_700_000_000.0
    monkeypatch.setattr(rl.time, "time", lambda: now)

    class _DummyServer:
        _NONCE_MAX = "bad-value"

    monkeypatch.setattr(rl, "_NONCE_MAX", 2)
    monkeypatch.setattr(
        "veritas_os.api.server",
        _DummyServer(),
        raising=False,
    )

    with rl._nonce_lock:
        rl._nonce_store.clear()
        rl._nonce_store["n1"] = now + 30
        rl._nonce_store["n2"] = now + 30
        rl._nonce_store["n3"] = now + 30
        rl._cleanup_nonces_unsafe()
        remaining = dict(rl._nonce_store)
        rl._nonce_store.clear()

    assert len(remaining) == 2


def test_schedule_nonce_cleanup_stops_when_timer_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No follow-up timer should be scheduled once scheduler is stopped."""
    created: list[Any] = []
    monkeypatch.setattr(rl, "_cleanup_nonces", lambda: None)
    monkeypatch.setattr(
        rl.threading,
        "Timer",
        lambda *_args, **_kwargs: created.append("called"),
    )

    old_timer = rl._nonce_cleanup_timer
    try:
        rl._nonce_cleanup_timer = None
        rl._schedule_nonce_cleanup()
    finally:
        rl._nonce_cleanup_timer = old_timer

    assert created == []


@pytest.mark.anyio
async def test_stage_core_execute_retry_failure_sets_stop_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retry failure in self-healing should set explicit stop reason."""
    from veritas_os.core.pipeline import self_healing

    ctx = PipelineContext(query="q", request_id="req-1", context={"user_id": "u1"})
    ctx.raw = {
        "fuji": {
            "rejection": {
                "status": "REJECTED",
                "error": {"code": "policy_error"},
                "feedback": {"action": "revise"},
            }
        }
    }

    state = SimpleNamespace(attempt=0)
    monkeypatch.setattr(self_healing, "is_healing_enabled", lambda _ctx: True)
    monkeypatch.setattr(self_healing, "load_healing_state", lambda _req_id: state)
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
    monkeypatch.setattr(self_healing, "healing_input_signature", lambda _inp: "sig-1")
    monkeypatch.setattr(self_healing, "diff_summary", lambda *_args, **_kwargs: "diff")
    monkeypatch.setattr(self_healing, "check_guardrails", lambda **_kwargs: None)
    monkeypatch.setattr(self_healing, "budget_remaining", lambda *_args, **_kwargs: {"budget": 1})
    monkeypatch.setattr(
        self_healing,
        "build_healing_trust_log_entry",
        lambda **_kwargs: {"kind": "self-healing"},
    )
    monkeypatch.setattr(self_healing, "clear_healing_state", lambda _req_id: None)
    monkeypatch.setattr(self_healing, "advance_state", lambda **_kwargs: None)
    monkeypatch.setattr(self_healing, "persist_healing_state", lambda *_args, **_kwargs: None)

    async def _call_core_decide_fn(**kwargs: Any) -> dict[str, Any]:
        if isinstance(kwargs.get("context"), dict) and "healing" in kwargs["context"]:
            raise RuntimeError("retry failed")
        return dict(ctx.raw)

    await pe.stage_core_execute(
        ctx,
        call_core_decide_fn=_call_core_decide_fn,
        append_trust_log_fn=lambda _entry: None,
        veritas_core=SimpleNamespace(decide=lambda **_kwargs: {}),
    )

    assert ctx.healing_stop_reason == "retry_execution_failed"
    assert ctx.response_extras["self_healing"]["enabled"] is True
    assert ctx.response_extras["self_healing"]["attempts"]


@pytest.mark.anyio
async def test_decide_pipeline_unavailable_resets_lazy_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pipeline unavailable path should return 503 and reset lazy state."""

    class _DummyServer:
        class _LazyState:
            def __init__(self) -> None:
                self.obj = "recovered"
                self.attempted = False
                self.err = None

        def __init__(self) -> None:
            self._pipeline_state = SimpleNamespace(obj=None, attempted=True, err=RuntimeError("x"))

        def get_decision_pipeline(self) -> None:
            return None

        @staticmethod
        def _publish_event(_name: str, _payload: dict[str, Any]) -> None:
            raise RuntimeError("event-bus down")

    server = _DummyServer()
    monkeypatch.setattr(rd, "_get_server", lambda: server)
    monkeypatch.setattr(rd._svc, "error_response", lambda code, **kwargs: {"code": code, **kwargs})

    req = rd.DecideRequest(query="q")
    request = SimpleNamespace(state=SimpleNamespace(user_id=None))
    resp = await rd.decide(req, request)

    assert resp["code"] == 503
    assert isinstance(server._pipeline_state, _DummyServer._LazyState)
