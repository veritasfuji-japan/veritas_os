"""Plan #12: follow-up abnormal-path tests for pipeline/routes/rate modules."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from veritas_os.api import rate_limiting as rl
from veritas_os.api import routes_decide as rd
from veritas_os.core.pipeline import pipeline_execute as pe
from veritas_os.core.pipeline.pipeline_types import PipelineContext


def test_stop_nonce_cleanup_scheduler_cancels_existing_timer() -> None:
    """Stopping nonce scheduler should cancel active timer and clear state."""

    class _DummyTimer:
        def __init__(self) -> None:
            self.cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

    timer = _DummyTimer()
    old_timer = rl._nonce_cleanup_timer
    try:
        rl._nonce_cleanup_timer = timer  # type: ignore[assignment]
        rl._stop_nonce_cleanup_scheduler()
    finally:
        rl._nonce_cleanup_timer = old_timer

    assert timer.cancelled is True


def test_stop_rate_cleanup_scheduler_cancels_existing_timer() -> None:
    """Stopping rate scheduler should cancel active timer and clear state."""

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


@pytest.mark.anyio
async def test_replay_endpoint_success_maps_result_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replay endpoint should serialize result object fields into response payload."""

    class _ReplayResult:
        decision_id = "d-777"
        replay_path = "/tmp/replay.json"
        match = True
        diff_summary = "no diff"
        replay_time_ms = 12.0
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

    out = await rd.replay_endpoint("d-777", _DummyRequest())

    assert out["ok"] is True
    assert out["decision_id"] == "d-777"
    assert out["match"] is True
    assert out["audit_summary"] == {"ok": True}


@pytest.mark.anyio
async def test_stage_core_execute_handles_non_dict_self_healing_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Self-healing metadata update should be skipped safely when slot is non-dict."""
    from veritas_os.core.pipeline import self_healing

    clear_calls: list[str] = []
    ctx = PipelineContext(query="q", request_id="req-non-dict", context={})
    ctx.response_extras["self_healing"] = "invalid"

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
    monkeypatch.setattr(self_healing, "clear_healing_state", lambda req_id: clear_calls.append(req_id))

    call_count = {"n": 0}

    async def _call_core_decide_fn(**_kwargs: Any) -> dict[str, Any]:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {
                "fuji": {
                    "rejection": {
                        "status": "REJECTED",
                        "error": {"code": "policy_error"},
                        "feedback": {"action": "revise"},
                    }
                }
            }
        return {"fuji": {"status": "allow"}}

    await pe.stage_core_execute(
        ctx,
        call_core_decide_fn=_call_core_decide_fn,
        append_trust_log_fn=lambda _entry: None,
        veritas_core=SimpleNamespace(decide=lambda **_kwargs: {}),
    )

    assert isinstance(ctx.response_extras["self_healing"], str)
    assert clear_calls == ["req-non-dict"]
    assert len(ctx.healing_attempts) == 1
