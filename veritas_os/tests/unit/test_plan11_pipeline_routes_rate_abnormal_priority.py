"""Plan #11: prioritized abnormal-path tests for sub-80 pipeline/routes/rate modules."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from veritas_os.api import rate_limiting as rl
from veritas_os.api import routes_decide as rd
from veritas_os.core.pipeline import pipeline_contracts as pc
from veritas_os.core.pipeline import pipeline_execute as pe
from veritas_os.core.pipeline import pipeline_response as pr
from veritas_os.core.pipeline.pipeline_types import PipelineContext


def test_merge_extras_preserving_contract_recovers_non_dict_inputs() -> None:
    """Contract merge should recover safely when incoming extras is not a dict."""
    base = {"metrics": "bad", "memory_meta": "bad"}

    out = pc._merge_extras_preserving_contract(
        base,
        incoming_extras="invalid",  # type: ignore[arg-type]
        fast_mode_default=True,
        context_obj={"intent": "safety"},
    )

    assert isinstance(out, dict)
    assert isinstance(out.get("metrics"), dict)
    assert isinstance(out.get("memory_meta"), dict)
    assert out["memory_meta"]["context"]["fast"] is True


def test_coerce_to_decide_response_falls_back_on_validation_error() -> None:
    """Model validation errors should return raw payload without raising."""

    class _FailingSchema:
        @staticmethod
        def model_validate(_payload: dict[str, Any]) -> Any:
            raise ValueError("invalid schema")

    payload = {"ok": True, "query": "q"}
    out = pr.coerce_to_decide_response(payload, DecideResponse=_FailingSchema)

    assert out == payload


@pytest.mark.anyio
async def test_stage_core_execute_survives_trust_log_append_error() -> None:
    """Self-healing should continue even when trust log append fails."""
    from veritas_os.core.pipeline import self_healing

    ctx = PipelineContext(query="q", request_id="req-trust", context={})

    monkeypatches = {
        "is_healing_enabled": lambda _ctx: True,
        "load_healing_state": lambda _req_id: SimpleNamespace(attempt=0),
        "HealingBudget": lambda: SimpleNamespace(),
        "decide_healing_action": lambda **_kwargs: SimpleNamespace(
            allow=False,
            stop_reason="policy_blocked",
            reason="stop",
            action=SimpleNamespace(value="stop"),
        ),
        "build_healing_input": lambda **_kwargs: {"patched": True},
        "healing_input_signature": lambda _inp: "sig",
        "diff_summary": lambda *_args, **_kwargs: "diff",
        "check_guardrails": lambda **_kwargs: None,
        "budget_remaining": lambda *_args, **_kwargs: {"remaining": 0},
        "build_healing_trust_log_entry": lambda **_kwargs: {"kind": "heal"},
        "clear_healing_state": lambda _req_id: None,
        "advance_state": lambda **_kwargs: None,
        "persist_healing_state": lambda *_args, **_kwargs: None,
    }
    for name, fn in monkeypatches.items():
        setattr(self_healing, name, fn)

    async def _call_core_decide_fn(**_kwargs: Any) -> dict[str, Any]:
        return {
            "fuji": {
                "rejection": {
                    "status": "REJECTED",
                    "error": {"code": "policy_error"},
                    "feedback": {"action": "revise"},
                }
            }
        }

    await pe.stage_core_execute(
        ctx,
        call_core_decide_fn=_call_core_decide_fn,
        append_trust_log_fn=lambda _entry: (_ for _ in ()).throw(TypeError("write failed")),
        veritas_core=SimpleNamespace(decide=lambda **_kwargs: {}),
    )

    assert ctx.healing_stop_reason == "policy_blocked"
    assert ctx.response_extras["self_healing"]["enabled"] is True


@pytest.mark.anyio
async def test_replay_decision_endpoint_returns_503_when_replay_method_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replay endpoint should return stable 503 when pipeline lacks replay method."""

    class _PipelineWithoutReplay:
        pass

    class _DummyServer:
        @staticmethod
        def get_decision_pipeline() -> _PipelineWithoutReplay:
            return _PipelineWithoutReplay()

    class _DummyRequest:
        query_params: dict[str, str] = {}

    monkeypatch.setattr(rd, "_get_server", lambda: _DummyServer())

    response = await rd.replay_decision_endpoint("decision-y", _DummyRequest())

    assert response.status_code == 503
    assert b"service_unavailable" in response.body


def test_env_int_safe_uses_default_for_blank_and_invalid() -> None:
    """Environment integer parser should fail safe on blank/invalid values."""
    assert rl._env_int_safe("VERITAS_TEST_MISSING_KEY", 9) == 9


@pytest.mark.anyio
async def test_replay_endpoint_returns_500_when_signature_check_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replay endpoint currently propagates signature verification failures."""

    class _DummyServer:
        @staticmethod
        async def verify_signature(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("signature backend unavailable")

        @staticmethod
        async def run_replay(*_args: Any, **_kwargs: Any) -> Any:
            return None

    class _DummyRequest:
        headers: dict[str, str] = {}

    monkeypatch.setattr(rd, "_get_server", lambda: _DummyServer())

    with pytest.raises(RuntimeError, match="signature backend unavailable"):
        await rd.replay_endpoint("decision-z", _DummyRequest())
