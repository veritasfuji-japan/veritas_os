from __future__ import annotations

import json
import types
from pathlib import Path
from typing import Any, Dict

import pytest

from veritas_os.core.pipeline_execute import stage_core_execute
from veritas_os.core.pipeline_gate import (
    _allow_prob,
    _dedupe_alts,
    _dedupe_alts_fallback,
    _load_memory_model,
    _load_valstats,
    _mem_model_path,
    _save_valstats,
)
from veritas_os.core.pipeline_types import PipelineContext


@pytest.mark.asyncio
async def test_stage_core_execute_success_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    from veritas_os.core import self_healing

    monkeypatch.setattr(self_healing, "is_healing_enabled", lambda _ctx: False)
    monkeypatch.setattr(self_healing, "load_healing_state", lambda _rid: self_healing.HealingState())

    seen: Dict[str, Any] = {}

    async def fake_call_core_decide_fn(**kwargs: Any) -> Dict[str, Any]:
        seen.update(kwargs)
        return {"chosen": {"title": "A"}}

    ctx = PipelineContext(
        query="hello",
        request_id="req-success",
        context={"tenant": "t1"},
        evidence=[{"id": 1}],
        response_extras={
            "planner": {"steps": ["s1"]},
            "env_tools": {"ok": True},
            "world_simulation": {"status": "ok"},
        },
        input_alts=[{"title": "opt"}],
        min_ev=2,
    )

    kernel = types.SimpleNamespace(decide=object())

    await stage_core_execute(
        ctx,
        call_core_decide_fn=fake_call_core_decide_fn,
        append_trust_log_fn=lambda _entry: None,
        veritas_core=kernel,
    )

    assert ctx.raw == {"chosen": {"title": "A"}}
    assert seen["core_fn"] is kernel.decide
    assert seen["query"] == "hello"
    assert seen["alternatives"] == [{"title": "opt"}]
    assert seen["min_evidence"] == 2
    assert seen["context"]["_orchestrated_by_pipeline"] is True
    assert seen["context"]["evidence"] == [{"id": 1}]


@pytest.mark.asyncio
async def test_stage_core_execute_core_failure_sets_empty_raw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veritas_os.core import self_healing

    monkeypatch.setattr(self_healing, "is_healing_enabled", lambda _ctx: False)
    monkeypatch.setattr(self_healing, "load_healing_state", lambda _rid: self_healing.HealingState())

    async def boom(**_kwargs: Any) -> Dict[str, Any]:
        raise RuntimeError("core down")

    ctx = PipelineContext(query="q", request_id="req-core-fail")
    kernel = types.SimpleNamespace(decide=object())

    await stage_core_execute(
        ctx,
        call_core_decide_fn=boom,
        append_trust_log_fn=lambda _entry: None,
        veritas_core=kernel,
    )

    assert ctx.raw == {}


@pytest.mark.asyncio
async def test_stage_core_execute_kernel_missing_degraded_path() -> None:
    calls = []

    async def should_not_run(**_kwargs: Any) -> Dict[str, Any]:
        calls.append("called")
        return {}

    ctx = PipelineContext(
        query="q",
        request_id="req-kernel-missing",
        response_extras={"env_tools": {}},
    )

    await stage_core_execute(
        ctx,
        call_core_decide_fn=should_not_run,
        append_trust_log_fn=lambda _entry: None,
        veritas_core=types.SimpleNamespace(),
    )

    assert calls == []
    assert ctx.response_extras["env_tools"]["kernel_missing"] is True


@pytest.mark.asyncio
async def test_stage_core_execute_self_healing_invoked_and_trustlog_best_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veritas_os.core import self_healing

    monkeypatch.setattr(self_healing, "is_healing_enabled", lambda _ctx: True)
    monkeypatch.setattr(self_healing, "load_healing_state", lambda _rid: self_healing.HealingState())

    rejected = {
        "fuji": {
            "rejection": {
                "status": "REJECTED",
                "error": {"code": "F-4001"},
                "feedback": {"action": "human_review"},
            }
        }
    }

    async def fake_call(**_kwargs: Any) -> Dict[str, Any]:
        return rejected

    entries = []

    def flaky_append(_entry: Dict[str, Any]) -> None:
        entries.append("attempted")
        raise KeyError("best-effort path")

    ctx = PipelineContext(query="q", request_id="req-heal-stop")
    kernel = types.SimpleNamespace(decide=object())

    await stage_core_execute(
        ctx,
        call_core_decide_fn=fake_call,
        append_trust_log_fn=flaky_append,
        veritas_core=kernel,
    )

    assert entries == ["attempted"]
    assert len(ctx.healing_attempts) == 1
    assert ctx.healing_stop_reason == "safety_code_blocked"
    assert ctx.response_extras["self_healing"]["enabled"] is True


def test_load_memory_model_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    original_import = builtins.__import__

    def deny_models(name: str, *args: Any, **kwargs: Any):
        if name.startswith("veritas_os.core.models"):
            raise ImportError("blocked")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", deny_models)
    vec, clf, pgl = _load_memory_model()

    assert vec is None
    assert clf is None
    assert pgl("x") == {"allow": 0.5}


def test_load_memory_model_predict_gate_label_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_mod = types.ModuleType("veritas_os.core.models.memory_model")
    fake_mod.MEM_VEC = "vec"
    fake_mod.MEM_CLF = "clf"
    fake_mod.predict_gate_label = lambda _text: "bad"  # type: ignore[assignment]

    monkeypatch.setitem(__import__("sys").modules, "veritas_os.core.models.memory_model", fake_mod)

    package = types.ModuleType("veritas_os.core.models")
    package.memory_model = fake_mod
    monkeypatch.setitem(__import__("sys").modules, "veritas_os.core.models", package)

    vec, clf, pgl = _load_memory_model()
    assert vec == "vec"
    assert clf == "clf"
    assert pgl("hello") == {"allow": 0.5}


def test_allow_prob_threshold_and_malformed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("veritas_os.core.pipeline_gate.predict_gate_label", lambda _t: {"allow": "0.91"})
    assert _allow_prob("ok") == pytest.approx(0.91)

    monkeypatch.setattr("veritas_os.core.pipeline_gate.predict_gate_label", lambda _t: {"allow": None})
    assert _allow_prob("bad") == 0.0


def test_mem_model_path_prefers_model_file(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_mod = types.ModuleType("veritas_os.core.models.memory_model")
    fake_mod.MODEL_FILE = "/tmp/model.bin"
    package = types.ModuleType("veritas_os.core.models")
    package.memory_model = fake_mod

    monkeypatch.setitem(__import__("sys").modules, "veritas_os.core.models", package)
    assert _mem_model_path() == "/tmp/model.bin"


def test_load_valstats_malformed_data(tmp_path: Path) -> None:
    p = tmp_path / "valstats.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")

    data = _load_valstats(p)
    assert data["ema"] == 0.5
    assert data["history"] == []


def test_save_valstats_then_load_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "stats" / "valstats.json"
    payload = {"ema": 0.8, "alpha": 0.4, "n": 4, "history": [0.8]}

    _save_valstats(payload, p)

    loaded = json.loads(p.read_text(encoding="utf-8"))
    assert loaded["ema"] == 0.8


def test_dedupe_fallback_and_kernel_helper_degradation() -> None:
    alts = [
        {"title": "A", "description": "d"},
        {"title": "A", "description": "d"},
        {"title": "B", "description": "d2"},
        "invalid",
    ]

    fallback = _dedupe_alts_fallback(alts)  # type: ignore[arg-type]
    assert len(fallback) == 2

    kernel = types.SimpleNamespace(_dedupe_alts=lambda _x: "not-a-list")
    deduped = _dedupe_alts(alts, veritas_core=kernel)  # type: ignore[arg-type]
    assert len(deduped) == 2
