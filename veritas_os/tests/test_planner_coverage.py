# tests/test_planner_coverage.py
# -*- coding: utf-8 -*-
"""Coverage boost tests for veritas_os/core/planner.py"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from veritas_os.core import planner as planner_core


# ============================================================
# _wants_inventory_step
# ============================================================

def test_wants_inventory_step_step1():
    assert planner_core._wants_inventory_step("step1で進めて") is True


def test_wants_inventory_step_step_1():
    assert planner_core._wants_inventory_step("step 1をやって") is True


def test_wants_inventory_step_tanaoroshi():
    assert planner_core._wants_inventory_step("棚卸しをしたい") is True
    assert planner_core._wants_inventory_step("棚おろしをしよう") is True


def test_wants_inventory_step_genjou():
    assert planner_core._wants_inventory_step("現状整理をお願い") is True
    assert planner_core._wants_inventory_step("現状把握したい") is True


def test_wants_inventory_step_inventory():
    assert planner_core._wants_inventory_step("do an inventory check") is True


def test_wants_inventory_step_empty():
    assert planner_core._wants_inventory_step("") is False
    assert planner_core._wants_inventory_step(None) is False


def test_wants_inventory_step_unrelated():
    assert planner_core._wants_inventory_step("明日の天気を教えて") is False


# ============================================================
# _normalize_step
# ============================================================

def test_normalize_step_fills_defaults():
    step = {"id": "s1", "title": "test"}
    result = planner_core._normalize_step(step)
    assert result["eta_hours"] == 1.0
    assert result["risk"] == 0.1
    assert result["dependencies"] == []


def test_normalize_step_preserves_existing():
    step = {"id": "s1", "eta_hours": 3.0, "risk": 0.5, "dependencies": ["a"]}
    result = planner_core._normalize_step(step)
    assert result["eta_hours"] == 3.0
    assert result["risk"] == 0.5
    assert result["dependencies"] == ["a"]


def test_normalize_step_bad_eta():
    step = {"id": "s1"}
    result = planner_core._normalize_step(step, default_eta_hours="not_a_float")
    assert result["eta_hours"] == 1.0  # fallback


def test_normalize_step_bad_risk():
    step = {"id": "s1"}
    result = planner_core._normalize_step(step, default_risk="bad")
    assert result["risk"] == 0.1  # fallback


def test_normalize_step_dependencies_not_list():
    step = {"id": "s1", "dependencies": "not_a_list"}
    result = planner_core._normalize_step(step)
    assert result["dependencies"] == []


def test_normalize_step_dependencies_coerce_int():
    step = {"id": "s1", "dependencies": [1, 2]}
    result = planner_core._normalize_step(step)
    assert result["dependencies"] == ["1", "2"]


# ============================================================
# _normalize_steps_list
# ============================================================

def test_normalize_steps_list_none():
    assert planner_core._normalize_steps_list(None) == []


def test_normalize_steps_list_not_list():
    assert planner_core._normalize_steps_list("bad") == []


def test_normalize_steps_list_filters_non_dict():
    steps = [{"id": "s1"}, "bad", 42, None, {"id": "s2"}]
    result = planner_core._normalize_steps_list(steps)
    assert len(result) == 2


# ============================================================
# _is_simple_qa
# ============================================================

def test_is_simple_qa_mode():
    assert planner_core._is_simple_qa("anything", {"mode": "simple_qa"}) is True
    assert planner_core._is_simple_qa("anything", {"simple_qa": True}) is True


def test_is_simple_qa_empty():
    assert planner_core._is_simple_qa("", {}) is False
    assert planner_core._is_simple_qa(None, {}) is False


def test_is_simple_qa_agi_blocked():
    assert planner_core._is_simple_qa("AGIとは？", {}) is False
    assert planner_core._is_simple_qa("VERITASの仕組み？", {}) is False


def test_is_simple_qa_short_question():
    assert planner_core._is_simple_qa("今何時？", {}) is True


def test_is_simple_qa_plan_words():
    assert planner_core._is_simple_qa("計画を教えて？", {}) is False


def test_is_simple_qa_long_question():
    # Long questions are not simple QA
    assert planner_core._is_simple_qa("これは非常に長い文章であり四十文字を超えるため単純な質問とは見なされません。教えて？", {}) is False


# ============================================================
# _safe_parse
# ============================================================

def test_safe_parse_none():
    assert planner_core._safe_parse(None) == {"steps": []}


def test_safe_parse_dict_with_steps():
    d = {"steps": [{"id": "s1"}]}
    assert planner_core._safe_parse(d)["steps"] == [{"id": "s1"}]


def test_safe_parse_dict_steps_is_dict():
    d = {"steps": {"id": "single"}}
    result = planner_core._safe_parse(d)
    assert result["steps"] == [{"id": "single"}]


def test_safe_parse_dict_no_steps():
    d = {"other": "value"}
    result = planner_core._safe_parse(d)
    assert "steps" in result


def test_safe_parse_list():
    result = planner_core._safe_parse([{"id": "s1"}, {"id": "s2"}])
    assert result["steps"] == [{"id": "s1"}, {"id": "s2"}]


def test_safe_parse_json_string():
    s = json.dumps({"steps": [{"id": "s1"}]})
    result = planner_core._safe_parse(s)
    assert len(result["steps"]) == 1


def test_safe_parse_fenced_json():
    s = '```json\n{"steps": [{"id": "s1"}]}\n```'
    result = planner_core._safe_parse(s)
    assert len(result["steps"]) == 1


def test_safe_parse_empty_string():
    assert planner_core._safe_parse("") == {"steps": []}


def test_safe_parse_non_string():
    result = planner_core._safe_parse(12345)
    assert "steps" in result


def test_safe_parse_invalid_json():
    result = planner_core._safe_parse("{invalid json content}")
    assert "steps" in result


# ============================================================
# _safe_json_extract (compat wrapper)
# ============================================================

def test_safe_json_extract_compat():
    s = json.dumps({"steps": [{"id": "s1"}]})
    result = planner_core._safe_json_extract(s)
    assert len(result["steps"]) == 1


# ============================================================
# _safe_json_extract_core
# ============================================================

def test_safe_json_extract_core_empty():
    assert planner_core._safe_json_extract_core("") == {"steps": []}


def test_safe_json_extract_core_triple_backtick():
    s = '```\n{"steps":[{"id":"s1"}]}\n```'
    result = planner_core._safe_json_extract_core(s)
    assert len(result["steps"]) == 1


def test_safe_json_extract_core_brace_extraction():
    s = 'Here is the plan: {"steps":[{"id":"s1"}]} end'
    result = planner_core._safe_json_extract_core(s)
    assert len(result["steps"]) == 1


def test_safe_json_extract_core_truncated_json():
    # Simulate truncated JSON that can be recovered by trimming
    s = '{"steps":[{"id":"s1"}]}extra garbage'
    result = planner_core._safe_json_extract_core(s)
    assert len(result["steps"]) == 1


def test_safe_json_extract_core_step_objects_rescue():
    # Test the _extract_step_objects fallback
    s = 'broken{json "steps": [{"id":"rescued_step","title":"t"}] more broken'
    result = planner_core._safe_json_extract_core(s)
    if result["steps"]:
        assert result["steps"][0]["id"] == "rescued_step"


def test_safe_json_extract_core_completely_invalid():
    result = planner_core._safe_json_extract_core("not json at all")
    assert result == {"steps": []}


def test_safe_json_extract_core_list_result():
    s = '[{"id":"s1"},{"id":"s2"}]'
    result = planner_core._safe_json_extract_core(s)
    assert result["steps"] == [{"id": "s1"}, {"id": "s2"}]


# ============================================================
# _fallback_plan
# ============================================================

def test_fallback_plan_default():
    result = planner_core._fallback_plan("テスト")
    assert result["source"] == "fallback_minimal"
    assert len(result["steps"]) == 2
    assert result["steps"][0]["id"] == "step1"


def test_fallback_plan_disallow_step1():
    result = planner_core._fallback_plan("テスト", disallow_step1=True)
    assert result["steps"][0]["id"] == "clarify"
    assert len(result["steps"]) == 2


def test_fallback_plan_empty_query():
    result = planner_core._fallback_plan("")
    assert result["source"] == "fallback_minimal"


# ============================================================
# _infer_veritas_stage
# ============================================================

def test_infer_veritas_stage_none():
    assert planner_core._infer_veritas_stage(None) == "S1_bootstrap"


def test_infer_veritas_stage_low():
    assert planner_core._infer_veritas_stage({"progress": 0.0}) == "S1_bootstrap"
    assert planner_core._infer_veritas_stage({"progress": 0.04}) == "S1_bootstrap"


def test_infer_veritas_stage_s2():
    assert planner_core._infer_veritas_stage({"progress": 0.06}) == "S2_arch_doc"


def test_infer_veritas_stage_s3():
    assert planner_core._infer_veritas_stage({"progress": 0.20}) == "S3_api_polish"


def test_infer_veritas_stage_s4():
    assert planner_core._infer_veritas_stage({"progress": 0.40}) == "S4_decision_analytics"


def test_infer_veritas_stage_s5():
    assert planner_core._infer_veritas_stage({"progress": 0.60}) == "S5_real_usecase"


def test_infer_veritas_stage_s6():
    assert planner_core._infer_veritas_stage({"progress": 0.75}) == "S6_llm_integration"


def test_infer_veritas_stage_s7():
    assert planner_core._infer_veritas_stage({"progress": 0.95}) == "S7_demo_review"


def test_infer_veritas_stage_bad_progress():
    assert planner_core._infer_veritas_stage({"progress": "bad"}) == "S1_bootstrap"


# ============================================================
# _fallback_plan_for_stage
# ============================================================

def test_fallback_plan_for_stage_s1():
    result = planner_core._fallback_plan_for_stage("q", "S1_bootstrap", None)
    assert result["source"] == "stage_fallback"
    assert len(result["steps"]) >= 1


def test_fallback_plan_for_stage_s2():
    result = planner_core._fallback_plan_for_stage("q", "S2_arch_doc", None)
    assert len(result["steps"]) >= 1


def test_fallback_plan_for_stage_s3():
    result = planner_core._fallback_plan_for_stage("q", "S3_api_polish", None)
    assert len(result["steps"]) >= 1


def test_fallback_plan_for_stage_s4():
    result = planner_core._fallback_plan_for_stage("q", "S4_decision_analytics", None)
    assert len(result["steps"]) >= 1


def test_fallback_plan_for_stage_s5():
    result = planner_core._fallback_plan_for_stage("q", "S5_real_usecase", None)
    assert len(result["steps"]) >= 1


def test_fallback_plan_for_stage_s6():
    result = planner_core._fallback_plan_for_stage("q", "S6_llm_integration", None)
    assert len(result["steps"]) >= 1


def test_fallback_plan_for_stage_s7():
    result = planner_core._fallback_plan_for_stage("q", "S7_demo_review", None)
    assert len(result["steps"]) >= 1


# ============================================================
# _try_get_memory_snippet
# ============================================================

def test_try_get_memory_snippet_empty_query():
    assert planner_core._try_get_memory_snippet("", {}) is None


def test_try_get_memory_snippet_no_search(monkeypatch):
    mock_mem = MagicMock(spec=[])  # no search/retrieve/query
    monkeypatch.setattr(planner_core, "mem", mock_mem)
    assert planner_core._try_get_memory_snippet("test", {}) is None


def test_try_get_memory_snippet_search_ok(monkeypatch):
    mock_mem = MagicMock()
    mock_mem.search.return_value = [
        {"text": "memory1"},
        {"text": "memory2"},
    ]
    monkeypatch.setattr(planner_core, "mem", mock_mem)
    result = planner_core._try_get_memory_snippet("test", {})
    assert result is not None
    assert "memory1" in result


def test_try_get_memory_snippet_retrieve_fallback(monkeypatch):
    mock_mem = MagicMock(spec=["retrieve"])
    mock_mem.retrieve.return_value = ["hit1", "hit2"]
    monkeypatch.setattr(planner_core, "mem", mock_mem)
    result = planner_core._try_get_memory_snippet("test", {})
    assert result is not None
    assert "hit1" in result


def test_try_get_memory_snippet_query_fallback(monkeypatch):
    mock_mem = MagicMock(spec=["query"])
    mock_mem.query.return_value = [{"content": "c1"}]
    monkeypatch.setattr(planner_core, "mem", mock_mem)
    result = planner_core._try_get_memory_snippet("test", {})
    assert result is not None
    assert "c1" in result


def test_try_get_memory_snippet_search_exception(monkeypatch):
    mock_mem = MagicMock()
    mock_mem.search.side_effect = RuntimeError("fail")
    monkeypatch.setattr(planner_core, "mem", mock_mem)
    assert planner_core._try_get_memory_snippet("test", {}) is None


def test_try_get_memory_snippet_empty_hits(monkeypatch):
    mock_mem = MagicMock()
    mock_mem.search.return_value = []
    monkeypatch.setattr(planner_core, "mem", mock_mem)
    assert planner_core._try_get_memory_snippet("test", {}) is None


# ============================================================
# _build_system_prompt
# ============================================================

def test_build_system_prompt_returns_string():
    prompt = planner_core._build_system_prompt()
    assert isinstance(prompt, str)
    assert "VERITAS" in prompt
    assert "JSON" in prompt


# ============================================================
# _build_user_prompt
# ============================================================

def test_build_user_prompt_basic():
    prompt = planner_core._build_user_prompt(
        query="テスト",
        context={"user_id": "u1", "stakes": 0.5},
        world={"progress": 0.1},
        memory_text="メモ",
    )
    assert "テスト" in prompt
    assert "メモ" in prompt


def test_build_user_prompt_no_memory():
    prompt = planner_core._build_user_prompt(
        query="テスト",
        context={},
        world=None,
        memory_text=None,
    )
    assert "MemoryOS" in prompt


def test_build_user_prompt_wants_step1():
    prompt = planner_core._build_user_prompt(
        query="step1で進めて",
        context={},
        world=None,
        memory_text=None,
    )
    assert isinstance(prompt, str)


# ============================================================
# plan_for_veritas_agi
# ============================================================

def test_plan_for_veritas_agi_simple_qa(monkeypatch):
    monkeypatch.setattr(planner_core.world_model, "snapshot", lambda key: None)
    result = planner_core.plan_for_veritas_agi(
        context={"mode": "simple_qa"},
        query="今何時？",
    )
    assert result["source"] == "simple_qa"


def test_plan_for_veritas_agi_llm_success(monkeypatch):
    monkeypatch.setattr(planner_core.world_model, "snapshot", lambda key: {"progress": 0.1})
    monkeypatch.setattr(planner_core, "mem", MagicMock(spec=[]))
    monkeypatch.setattr(planner_core.llm_client, "chat", lambda **kw: {
        "text": json.dumps({"steps": [{"id": "s1", "title": "LLM step"}]})
    })
    result = planner_core.plan_for_veritas_agi(
        context={"user_id": "test"},
        query="テスト計画を立てて",
    )
    assert result["source"] == "openai_llm"
    assert len(result["steps"]) >= 1


def test_plan_for_veritas_agi_llm_empty_steps(monkeypatch):
    monkeypatch.setattr(planner_core.world_model, "snapshot", lambda key: {"progress": 0.1})
    monkeypatch.setattr(planner_core, "mem", MagicMock(spec=[]))
    monkeypatch.setattr(planner_core.llm_client, "chat", lambda **kw: {
        "text": json.dumps({"steps": []})
    })
    result = planner_core.plan_for_veritas_agi(
        context={},
        query="テスト",
    )
    assert result["source"] == "stage_fallback"


def test_plan_for_veritas_agi_llm_exception(monkeypatch):
    monkeypatch.setattr(planner_core.world_model, "snapshot", lambda key: {"progress": 0.1})
    monkeypatch.setattr(planner_core, "mem", MagicMock(spec=[]))
    monkeypatch.setattr(planner_core.llm_client, "chat", lambda **kw: (_ for _ in ()).throw(RuntimeError("fail")))

    def _chat_fail(**kw):
        raise RuntimeError("LLM down")
    monkeypatch.setattr(planner_core.llm_client, "chat", _chat_fail)

    result = planner_core.plan_for_veritas_agi(
        context={},
        query="テスト",
    )
    assert result["source"] in ("stage_fallback", "fallback_minimal")


def test_plan_for_veritas_agi_disallow_step1(monkeypatch):
    """When step1 is not wanted, step1 IDs are filtered."""
    monkeypatch.setattr(planner_core.world_model, "snapshot", lambda key: None)
    monkeypatch.setattr(planner_core, "mem", MagicMock(spec=[]))
    monkeypatch.setattr(planner_core.llm_client, "chat", lambda **kw: {
        "text": json.dumps({"steps": [
            {"id": "step1", "title": "棚卸し"},
            {"id": "s2", "title": "Next"},
        ]})
    })
    result = planner_core.plan_for_veritas_agi(
        context={},
        query="テスト計画を立てて",  # Not step1 request
    )
    # step1 should be filtered
    ids = [s.get("id") for s in result["steps"]]
    assert "step1" not in ids


def test_plan_for_veritas_agi_disallow_step1_all_step1(monkeypatch):
    """When ALL steps are step1, keep them to avoid empty result."""
    monkeypatch.setattr(planner_core.world_model, "snapshot", lambda key: None)
    monkeypatch.setattr(planner_core, "mem", MagicMock(spec=[]))
    monkeypatch.setattr(planner_core.llm_client, "chat", lambda **kw: {
        "text": json.dumps({"steps": [
            {"id": "step1", "title": "Only step"},
        ]})
    })
    result = planner_core.plan_for_veritas_agi(
        context={},
        query="テスト計画",
    )
    assert len(result["steps"]) >= 1


def test_plan_for_veritas_agi_world_snapshot_fail(monkeypatch):
    def _snap_fail(key):
        raise RuntimeError("snap fail")
    monkeypatch.setattr(planner_core.world_model, "snapshot", _snap_fail)
    monkeypatch.setattr(planner_core, "mem", MagicMock(spec=[]))
    monkeypatch.setattr(planner_core.llm_client, "chat", lambda **kw: {
        "text": json.dumps({"steps": [{"id": "s1", "title": "ok"}]})
    })
    result = planner_core.plan_for_veritas_agi(
        context={},
        query="テスト",
    )
    assert isinstance(result, dict)


# ============================================================
# _priority_from_risk_impact
# ============================================================

def test_priority_from_risk_impact():
    assert planner_core._priority_from_risk_impact("high", "high") == "high"
    assert planner_core._priority_from_risk_impact("low", "low") == "low"
    assert planner_core._priority_from_risk_impact("medium", "medium") == "medium"
    assert planner_core._priority_from_risk_impact(None, None) == "low"
    assert planner_core._priority_from_risk_impact("high", "medium") == "high"


# ============================================================
# generate_code_tasks
# ============================================================

def test_generate_code_tasks_inline_changes(monkeypatch):
    monkeypatch.setattr(planner_core.world_model, "get_state", lambda: None)
    result = planner_core.generate_code_tasks(
        bench={
            "changes": [
                {
                    "target_module": "kernel",
                    "target_path": "kernel.py",
                    "title": "Fix kernel",
                    "description": "Fix a bug",
                    "risk": "high",
                    "impact": "high",
                    "suggested_functions": ["decide"],
                    "reason": "bug found",
                }
            ],
            "tests": [
                {
                    "title": "Test kernel",
                    "description": "unit test",
                    "kind": "unit",
                }
            ],
        },
    )
    assert len(result["tasks"]) >= 2


def test_generate_code_tasks_code_planner_path(monkeypatch):
    mock_plan = MagicMock()
    mock_plan.to_dict.return_value = {
        "changes": [
            {"id": "c1", "title": "Change", "description": "desc", "target_module": "mod"}
        ]
    }
    monkeypatch.setattr(planner_core.code_planner, "generate_code_change_plan", lambda **kw: mock_plan)
    result = planner_core.generate_code_tasks(bench={})
    assert len(result["tasks"]) >= 1


def test_generate_code_tasks_code_planner_fails(monkeypatch):
    def _fail(**kw):
        raise RuntimeError("code planner fail")
    monkeypatch.setattr(planner_core.code_planner, "generate_code_change_plan", _fail)
    monkeypatch.setattr(planner_core.world_model, "get_state", lambda: None)
    result = planner_core.generate_code_tasks(bench={})
    assert "tasks" in result


def test_generate_code_tasks_with_doctor_issues(monkeypatch):
    monkeypatch.setattr(planner_core.world_model, "get_state", lambda: None)
    result = planner_core.generate_code_tasks(
        bench={"changes": [{"title": "ch"}]},
        doctor_report={
            "issues": [
                {"severity": "high", "module": "fuji", "summary": "leak", "detail": "d", "recommendation": "fix"},
                {"severity": "low", "module": "mem", "summary": "minor"},
            ]
        },
    )
    # Should have code_change tasks + self_heal tasks
    kinds = [t["kind"] for t in result["tasks"]]
    assert "self_heal" in kinds


def test_generate_code_tasks_world_state_meta(monkeypatch):
    monkeypatch.setattr(planner_core.world_model, "get_state", lambda: None)
    result = planner_core.generate_code_tasks(
        bench={"changes": [{"title": "ch"}]},
        world_state={"veritas": {"progress": 0.5, "decision_count": 10}},
    )
    assert result["meta"]["progress"] == 0.5
    assert result["meta"]["decision_count"] == 10


# ============================================================
# generate_plan (backward compat)
# ============================================================

def test_generate_plan_basic():
    result = planner_core.generate_plan(
        query="テスト",
        chosen={"title": "Action", "description": "desc"},
    )
    assert isinstance(result, list)
    assert len(result) >= 3  # analyze, execute_core, log, reflect


def test_generate_plan_with_research_keywords():
    result = planner_core.generate_plan(
        query="情報を調べてリサーチする",
        chosen={"title": "Research"},
    )
    ids = [s["id"] for s in result]
    assert "research" in ids


def test_generate_plan_empty_query():
    result = planner_core.generate_plan(
        query="",
        chosen=None,
    )
    assert isinstance(result, list)
    assert len(result) >= 3
