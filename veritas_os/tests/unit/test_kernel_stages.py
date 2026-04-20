# veritas_os/tests/unit/test_kernel_stages.py
# -*- coding: utf-8 -*-
"""Unit tests for ``veritas_os.core.kernel_stages``.

``kernel_stages`` hosts the per-stage helpers extracted from
``kernel.decide`` (context prep, memory/evidence, world simulation, env
tools, scoring, debate, FUJI Gate, persona updates, episode save).
Each stage is validated in isolation so that future refactors surface
regressions without relying on the aggregate ``test_kernel_decide_ext``
suite.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from veritas_os.core import kernel_stages

pytestmark = pytest.mark.unit


# ============================================================
# Helpers
# ============================================================


def _mk_alt(
    _id: str = "a1",
    title: str = "default",
    description: str = "",
    score: float = 1.0,
) -> Dict[str, Any]:
    return {
        "id": _id,
        "title": title,
        "description": description,
        "score": score,
    }


# ============================================================
# prepare_context
# ============================================================


class TestPrepareContext:
    def test_populates_defaults_and_preserves_overrides(self):
        ctx = kernel_stages.prepare_context(
            context={"user_id": "alice", "stakes": 0.8},
            query="hello",
        )
        assert ctx["user_id"] == "alice"
        assert ctx["stakes"] == 0.8
        assert ctx["query"] == "hello"
        assert ctx["mode"] == ""
        assert isinstance(ctx["request_id"], str) and len(ctx["request_id"]) > 0

    def test_generates_request_id_when_missing(self):
        ctx_a = kernel_stages.prepare_context({}, "q")
        ctx_b = kernel_stages.prepare_context({}, "q")
        assert ctx_a["request_id"] != ctx_b["request_id"]

    def test_computes_telos_score_from_weights(self):
        ctx = kernel_stages.prepare_context(
            context={
                "telos_weights": {"W_Transcendence": 0.8, "W_Struggle": 0.2},
            },
            query="q",
        )
        # 0.5 * 0.8 + 0.5 * 0.2 = 0.5
        assert ctx["_computed_telos_score"] == pytest.approx(0.5)

    def test_handles_non_dict_telos_weights_gracefully(self):
        ctx = kernel_stages.prepare_context(
            context={"telos_weights": None},
            query="q",
        )
        # Defaults: 0.5 * 0.6 + 0.5 * 0.4 = 0.5
        assert ctx["_computed_telos_score"] == pytest.approx(0.5)

    def test_none_context_is_safe(self):
        ctx = kernel_stages.prepare_context(context=None, query="q")  # type: ignore[arg-type]
        assert ctx["user_id"] == "cli"


# ============================================================
# collect_memory_evidence
# ============================================================


class TestCollectMemoryEvidence:
    def test_uses_pipeline_provided_evidence(self):
        provided = [{"snippet": "cached", "confidence": 0.7}]
        result = kernel_stages.collect_memory_evidence(
            user_id="u1",
            query="q",
            context={"_pipeline_evidence": provided},
        )
        assert result["source"] == "pipeline_provided"
        assert result["evidence"] is provided
        assert result["evidence_count"] == 1

    def test_fast_mode_skips_memory_lookup(self):
        result = kernel_stages.collect_memory_evidence(
            user_id="u1",
            query="q",
            context={},
            fast_mode=True,
        )
        assert result["source"] == "skipped_fast_mode"
        assert result["evidence"] == []

    def test_calls_memoryos_summarizer(self, monkeypatch):
        from veritas_os.core import memory as real_mem

        calls: List[Dict[str, Any]] = []

        def _summarize(user_id: str, query: str, limit: int) -> str:
            calls.append({"user_id": user_id, "query": query, "limit": limit})
            return "summary-text"

        monkeypatch.setattr(real_mem, "summarize_for_planner", _summarize)

        result = kernel_stages.collect_memory_evidence(
            user_id="u1",
            query="investigate",
            context={},
        )
        assert result["source"] == "MemoryOS.summarize_for_planner"
        assert result["memory_summary"] == "summary-text"
        assert calls and calls[0]["user_id"] == "u1"

    def test_captures_exception_in_source(self, monkeypatch):
        from veritas_os.core import memory as real_mem

        def _boom(**_kwargs):
            raise RuntimeError("memory-down")

        monkeypatch.setattr(real_mem, "summarize_for_planner", _boom)

        result = kernel_stages.collect_memory_evidence(
            user_id="u1",
            query="q",
            context={},
        )
        assert result["source"].startswith("error: ")
        assert "memory-down" in result["source"]


# ============================================================
# run_world_simulation
# ============================================================


class TestRunWorldSimulation:
    def test_uses_pipeline_provided_simulation(self):
        result = kernel_stages.run_world_simulation(
            user_id="u1",
            query="q",
            context={
                "_world_sim_done": True,
                "_world_sim_result": {"projection": "foo"},
            },
        )
        assert result["source"] == "pipeline_provided"
        assert result["simulation"] == {"projection": "foo"}

    def test_fast_mode_skips(self):
        result = kernel_stages.run_world_simulation(
            user_id="u1",
            query="q",
            context={},
            fast_mode=True,
        )
        assert result["source"] == "skipped_fast_mode"
        assert result["simulation"] is None

    def test_invokes_world_simulate(self, monkeypatch):
        from veritas_os.core import world as real_world

        monkeypatch.setattr(
            real_world, "simulate", lambda **kw: {"ok": True, "kw": kw}
        )

        result = kernel_stages.run_world_simulation(
            user_id="u1",
            query="q",
            context={},
        )
        assert result["source"] == "world.simulate()"
        assert result["simulation"]["ok"] is True

    def test_captures_simulate_exception(self, monkeypatch):
        from veritas_os.core import world as real_world

        def _boom(**_kwargs):
            raise RuntimeError("sim-down")

        monkeypatch.setattr(real_world, "simulate", _boom)

        result = kernel_stages.run_world_simulation(
            user_id="u1",
            query="q",
            context={},
        )
        assert result["simulation"] is None
        assert "sim-down" in result["source"]


# ============================================================
# run_environment_tools & _run_tool_safe
# ============================================================


class TestRunEnvironmentTools:
    def test_uses_pipeline_provided_env_tools(self):
        provided = {"web_search": {"ok": True, "results": []}}
        result = kernel_stages.run_environment_tools(
            query="q",
            context={"_pipeline_env_tools": provided},
        )
        assert result is provided

    def test_fast_mode_returns_skipped_marker(self):
        result = kernel_stages.run_environment_tools(
            query="q",
            context={},
            fast_mode=True,
        )
        assert result == {"skipped": {"reason": "fast_mode"}}

    def test_github_keyword_triggers_github_search(self, monkeypatch):
        import veritas_os.tools as real_tools

        seen: List[Dict[str, Any]] = []

        def _call_tool(kind: str, **kwargs):
            seen.append({"kind": kind, **kwargs})
            return {"ok": True, "results": [{"name": "repo"}]}

        monkeypatch.setattr(real_tools, "call_tool", _call_tool)

        result = kernel_stages.run_environment_tools(
            query="search github for pytest",
            context={},
        )
        assert "github_search" in result
        assert "web_search" not in result
        assert seen and seen[0]["kind"] == "github_search"

    def test_use_env_tools_flag_runs_both_tools(self, monkeypatch):
        import veritas_os.tools as real_tools

        monkeypatch.setattr(
            real_tools, "call_tool", lambda kind, **kw: {"ok": True, "results": []}
        )

        result = kernel_stages.run_environment_tools(
            query="hello",
            context={"use_env_tools": True},
        )
        assert "web_search" in result
        assert "github_search" in result

    def test_paper_keyword_triggers_web_search(self, monkeypatch):
        import veritas_os.tools as real_tools

        monkeypatch.setattr(
            real_tools, "call_tool", lambda kind, **kw: {"ok": True, "results": []}
        )

        result = kernel_stages.run_environment_tools(
            query="研究 paper on transformers",
            context={},
        )
        assert "web_search" in result

    def test_error_captured_in_result(self, monkeypatch):
        import veritas_os.tools as real_tools

        def _boom(kind, **kwargs):
            raise RuntimeError("call-tool-broken")

        monkeypatch.setattr(real_tools, "call_tool", _boom)

        # ``use_env_tools`` forces tool invocation, which surfaces the error
        # from ``_run_tool_safe`` into the per-tool payload.
        result = kernel_stages.run_environment_tools(
            query="q",
            context={"use_env_tools": True},
        )
        assert "web_search" in result
        assert result["web_search"]["ok"] is False
        assert "call-tool-broken" in result["web_search"]["error"]


class TestRunToolSafe:
    def test_wraps_non_dict_result(self):
        def _tool(kind, **_kwargs):
            return [1, 2, 3]

        out = kernel_stages._run_tool_safe(_tool, "web_search")
        assert out["raw"] == [1, 2, 3]
        assert out["ok"] is True
        assert out["results"] == []

    def test_preserves_existing_dict_fields(self):
        def _tool(kind, **_kwargs):
            return {"ok": True, "results": [{"x": 1}]}

        out = kernel_stages._run_tool_safe(_tool, "web_search")
        assert out["ok"] is True
        assert out["results"] == [{"x": 1}]

    def test_returns_error_envelope_on_exception(self):
        def _tool(kind, **_kwargs):
            raise ValueError("bad-input")

        out = kernel_stages._run_tool_safe(_tool, "web_search")
        assert out["ok"] is False
        assert out["results"] == []
        assert "bad-input" in out["error"]


# ============================================================
# score_alternatives
# ============================================================


@pytest.fixture
def value_core_disabled(monkeypatch):
    """Disable ``value_core`` scoring so tests assert base heuristics only."""
    from veritas_os.core import value_core as real_vc

    monkeypatch.setattr(real_vc, "compute_value_score", None, raising=False)
    monkeypatch.setattr(real_vc, "OptionScore", None, raising=False)
    yield


class TestScoreAlternatives:
    def test_empty_alternatives_is_no_op(self, value_core_disabled):
        alternatives: List[Dict[str, Any]] = []
        kernel_stages.score_alternatives(
            intent="weather",
            query="q",
            alternatives=alternatives,
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
        )
        assert alternatives == []

    def test_intent_weather_bonus_applied(self, value_core_disabled):
        alt = _mk_alt(title="今日の予報を確認")
        kernel_stages.score_alternatives(
            intent="weather",
            query="雨が降る？",
            alternatives=[alt],
            telos_score=0.0,
            stakes=0.0,
            persona_bias=None,
        )
        assert alt["score"] > 1.0
        assert alt["score_raw"] == 1.0

    def test_query_match_bonus_applied_for_umbrella(self, value_core_disabled):
        alt = _mk_alt(title="傘を持つ")
        kernel_stages.score_alternatives(
            intent="weather",
            query="傘が必要？ forecast",
            alternatives=[alt],
            telos_score=0.0,
            stakes=0.0,
            persona_bias=None,
        )
        assert alt["score"] > 1.0

    def test_high_stakes_bonus_applied(self, value_core_disabled):
        alt = _mk_alt(title="休息する")
        kernel_stages.score_alternatives(
            intent="health",
            query="疲れた",
            alternatives=[alt],
            telos_score=0.0,
            stakes=0.9,
            persona_bias=None,
        )
        assert alt["score"] > 1.0

    def test_persona_bias_boosts_known_title(self, value_core_disabled):
        alt = _mk_alt(title="Refactor")
        kernel_stages.score_alternatives(
            intent="plan",
            query="refactor?",
            alternatives=[alt],
            telos_score=0.0,
            stakes=0.0,
            persona_bias={"refactor": 0.5},
        )
        assert alt["score"] > 1.0

    def test_score_raw_records_pre_adjustment_value(self, value_core_disabled):
        alt = _mk_alt(title="無関係", score=0.7)
        kernel_stages.score_alternatives(
            intent="other",
            query="q",
            alternatives=[alt],
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
        )
        assert alt["score_raw"] == 0.7


# ============================================================
# run_debate_stage
# ============================================================


class TestRunDebateStage:
    def test_fast_mode_picks_highest_score(self):
        alts = [_mk_alt("a", "low", score=0.3), _mk_alt("b", "high", score=0.9)]
        result = kernel_stages.run_debate_stage(
            query="q",
            alternatives=alts,
            context={},
            fast_mode=True,
        )
        assert result["chosen"]["id"] == "b"
        assert result["source"] == "fast_mode"
        assert result["debate_logs"][0]["source"] == "fast_mode_local"

    def test_fast_mode_with_empty_alternatives_returns_placeholder(self):
        result = kernel_stages.run_debate_stage(
            query="q",
            alternatives=[],
            context={},
            fast_mode=True,
        )
        assert result["chosen"] is not None
        assert result["chosen"]["title"] == "デフォルト選択"

    def test_invokes_debate_core_and_uses_returned_choice(self, monkeypatch):
        from veritas_os.core import debate as real_debate

        expected_choice = {"id": "winner", "title": "Winner", "score": 2.0}

        def _run_debate(*, query, options, context):
            assert query == "q"
            return {
                "chosen": expected_choice,
                "options": options,
                "source": "openai_llm",
            }

        monkeypatch.setattr(real_debate, "run_debate", _run_debate)

        result = kernel_stages.run_debate_stage(
            query="q",
            alternatives=[_mk_alt("a"), _mk_alt("b")],
            context={"stakes": 0.6},
        )
        assert result["chosen"] == expected_choice
        assert result["source"] == "openai_llm"
        assert result["debate_logs"][0]["suggested_choice_id"] == "winner"

    def test_debate_exception_falls_back_to_max_score(self, monkeypatch):
        from veritas_os.core import debate as real_debate

        def _run_debate(**_kwargs):
            raise RuntimeError("llm-down")

        monkeypatch.setattr(real_debate, "run_debate", _run_debate)

        alts = [_mk_alt("a", score=0.3), _mk_alt("b", score=0.8)]
        result = kernel_stages.run_debate_stage(
            query="q",
            alternatives=alts,
            context={},
        )
        assert result["chosen"]["id"] == "b"
        assert result["source"] == "fallback"
        assert "フォールバック" in result["debate_logs"][0]["summary"]

    def test_debate_exception_with_empty_alts_uses_placeholder(self, monkeypatch):
        from veritas_os.core import debate as real_debate

        def _boom(**_kwargs):
            raise RuntimeError("x")

        monkeypatch.setattr(real_debate, "run_debate", _boom)

        result = kernel_stages.run_debate_stage(
            query="q",
            alternatives=[],
            context={},
        )
        assert result["chosen"]["title"] == "フォールバック選択"


# ============================================================
# run_fuji_gate
# ============================================================


class TestRunFujiGate:
    def test_happy_path_delegates_to_fuji_core(self, monkeypatch):
        from veritas_os.core import fuji as real_fuji

        captured: Dict[str, Any] = {}

        def _evaluate(query, *, context, evidence, alternatives):
            captured["query"] = query
            captured["context"] = context
            return {
                "status": "allow",
                "decision_status": "allow",
                "risk": 0.1,
                "modifications": [],
            }

        monkeypatch.setattr(real_fuji, "evaluate", _evaluate)

        result = kernel_stages.run_fuji_gate(
            query="q",
            context={"user_id": "u1", "stakes": 0.4, "_computed_telos_score": 0.7},
            evidence=[],
            alternatives=[_mk_alt()],
        )
        assert result["decision_status"] == "allow"
        assert captured["context"]["telos_score"] == 0.7

    def test_fuji_exception_returns_deny_and_max_risk(self, monkeypatch):
        from veritas_os.core import fuji as real_fuji

        def _boom(*_a, **_kw):
            raise RuntimeError("fuji-internal")

        monkeypatch.setattr(real_fuji, "evaluate", _boom)

        result = kernel_stages.run_fuji_gate(
            query="q",
            context={"user_id": "u1"},
            evidence=[],
            alternatives=[_mk_alt()],
        )
        assert result["status"] == "deny"
        assert result["decision_status"] == "deny"
        assert result["risk"] == 1.0
        assert "FUJI_INTERNAL_ERROR" in result["violations"]
        assert result["meta"]["fuji_internal_error"] is True
        assert result["meta"]["exception_type"] == "RuntimeError"
        assert result["rejection_reason"].startswith("fuji_internal_error:")


# ============================================================
# update_persona_and_goals
# ============================================================


class TestUpdatePersonaAndGoals:
    def test_fast_mode_skips(self):
        result = kernel_stages.update_persona_and_goals(
            chosen=_mk_alt(),
            context={},
            fuji_result={"risk": 0.1},
            telos_score=0.5,
            fast_mode=True,
        )
        assert result["skipped"] is True
        assert result["updated"] is False

    def test_pipeline_already_adjusted_short_circuits(self):
        result = kernel_stages.update_persona_and_goals(
            chosen=_mk_alt(),
            context={"_agi_goals_adjusted_by_pipeline": True},
            fuji_result={"risk": 0.1},
            telos_score=0.5,
        )
        assert result["skipped"] is True

    def test_exception_captured_in_error_field(self, monkeypatch):
        from veritas_os.core import adapt as real_adapt

        def _boom(**_):
            raise RuntimeError("persona-store-down")

        monkeypatch.setattr(real_adapt, "update_persona_bias_from_history", _boom)

        result = kernel_stages.update_persona_and_goals(
            chosen=_mk_alt(title="Refactor"),
            context={},
            fuji_result={"risk": 0.2},
            telos_score=0.4,
        )
        assert result["updated"] is False
        assert result["error"] is not None
        assert "persona-store-down" in result["error"]


# ============================================================
# save_episode_to_memory
# ============================================================


class _FakeMem:
    def __init__(self, *, raise_typeerror_first: bool = False):
        self.calls: List[tuple] = []
        self.raise_typeerror_first = raise_typeerror_first
        self._first_call = True

    def put(self, *args, **kwargs):
        if self.raise_typeerror_first and self._first_call:
            self._first_call = False
            raise TypeError("legacy signature mismatch")
        self.calls.append((args, kwargs))


class TestSaveEpisodeToMemory:
    def test_pipeline_already_saved_short_circuits(self):
        result = kernel_stages.save_episode_to_memory(
            query="q",
            chosen=_mk_alt(),
            context={"_episode_saved_by_pipeline": True},
            intent="plan",
            mode="",
            telos_score=0.5,
        )
        assert result is True

    def test_happy_path_uses_single_arg_api(self, monkeypatch):
        from veritas_os.core import memory as real_mem

        fake = _FakeMem()
        monkeypatch.setattr(real_mem, "MEM", fake)

        ok = kernel_stages.save_episode_to_memory(
            query="q",
            chosen=_mk_alt(title="Refactor"),
            context={"user_id": "u1", "request_id": "req-1"},
            intent="plan",
            mode="",
            telos_score=0.5,
        )
        assert ok is True
        assert fake.calls and fake.calls[0][0][0] == "episodic"

    def test_falls_back_to_legacy_signature_on_typeerror(self, monkeypatch):
        from veritas_os.core import memory as real_mem

        fake = _FakeMem(raise_typeerror_first=True)
        monkeypatch.setattr(real_mem, "MEM", fake)

        ok = kernel_stages.save_episode_to_memory(
            query="q",
            chosen=_mk_alt(),
            context={"user_id": "u1", "request_id": "req-1"},
            intent="plan",
            mode="",
            telos_score=0.5,
        )
        assert ok is True
        assert fake.calls and fake.calls[0][0][0] == "u1"
        assert fake.calls[0][0][1] == "decision:req-1"

    def test_returns_false_on_unexpected_exception(self, monkeypatch):
        from veritas_os.core import memory as real_mem

        class _ExplodingMem:
            def put(self, *_a, **_kw):
                raise RuntimeError("disk-full")

        monkeypatch.setattr(real_mem, "MEM", _ExplodingMem())

        ok = kernel_stages.save_episode_to_memory(
            query="q",
            chosen=_mk_alt(),
            context={"user_id": "u1"},
            intent="plan",
            mode="",
            telos_score=0.5,
        )
        assert ok is False


# ============================================================
# _mk_option utility
# ============================================================


class TestMkOption:
    def test_generates_unique_id_when_not_provided(self):
        a = kernel_stages._mk_option("T")
        b = kernel_stages._mk_option("T")
        assert a["id"] != b["id"]
        assert a["title"] == "T"
        assert a["score"] == 1.0
        assert a["description"] == ""

    def test_preserves_provided_id(self):
        opt = kernel_stages._mk_option("T", description="desc", _id="fixed")
        assert opt["id"] == "fixed"
        assert opt["description"] == "desc"


# ============================================================
# Module surface
# ============================================================


class TestPublicSurface:
    def test_all_exports_exist(self):
        for name in kernel_stages.__all__:
            assert hasattr(kernel_stages, name), f"missing export: {name}"
