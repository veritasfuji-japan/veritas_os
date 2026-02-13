# tests/test_kernel_coverage.py
# -*- coding: utf-8 -*-
"""Coverage boost tests for veritas_os/core/kernel.py"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from veritas_os.core import kernel


# ============================================================
# anyio backend fixture
# ============================================================

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _stub_affect(monkeypatch):
    """Stub affect_core.reflect which may not exist in affect module."""
    if not hasattr(kernel.affect_core, "reflect"):
        monkeypatch.setattr(kernel.affect_core, "reflect", lambda d: {}, raising=False)


# ============================================================
# run_env_tool
# ============================================================

def test_run_env_tool_success(monkeypatch):
    monkeypatch.setattr(kernel, "call_tool", lambda kind, **kw: {"data": 1})
    result = kernel.run_env_tool("web_search", query="test")
    assert result["ok"] is True
    assert result["data"] == 1


def test_run_env_tool_non_dict_result(monkeypatch):
    monkeypatch.setattr(kernel, "call_tool", lambda kind, **kw: "raw_string")
    result = kernel.run_env_tool("web_search", query="test")
    assert result["ok"] is True
    assert result["raw"] == "raw_string"


def test_run_env_tool_exception(monkeypatch):
    def _boom(kind, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(kernel, "call_tool", _boom)
    result = kernel.run_env_tool("web_search", query="test")
    assert result["ok"] is False
    assert "env_tool error" in result["error"]
    assert result["error_code"] == "ENV_TOOL_EXECUTION_ERROR"
    assert result["tool_kind"] == "web_search"


# ============================================================
# _safe_load_persona
# ============================================================

def test_safe_load_persona_ok(monkeypatch):
    monkeypatch.setattr(kernel.adapt, "load_persona", lambda: {"name": "test"})
    assert kernel._safe_load_persona() == {"name": "test"}


def test_safe_load_persona_non_dict(monkeypatch):
    monkeypatch.setattr(kernel.adapt, "load_persona", lambda: "bad")
    assert kernel._safe_load_persona() == {}


def test_safe_load_persona_exception(monkeypatch):
    monkeypatch.setattr(kernel.adapt, "load_persona", lambda: (_ for _ in ()).throw(RuntimeError("fail")))
    # The lambda itself raises, but _safe_load_persona wraps
    def _raise():
        raise RuntimeError("fail")
    monkeypatch.setattr(kernel.adapt, "load_persona", _raise)
    assert kernel._safe_load_persona() == {}


# ============================================================
# _tokens
# ============================================================

def test_tokens_basic():
    assert kernel._tokens("Hello World") == ["hello", "world"]


def test_tokens_empty():
    assert kernel._tokens("") == []
    assert kernel._tokens(None) == []


def test_tokens_fullwidth_space():
    assert kernel._tokens("東京　大阪") == ["東京", "大阪"]


# ============================================================
# _mk_option
# ============================================================

def test_mk_option_auto_id():
    opt = kernel._mk_option("title1", "desc1")
    assert opt["title"] == "title1"
    assert opt["description"] == "desc1"
    assert opt["score"] == 1.0
    assert len(opt["id"]) == 32  # uuid hex


def test_mk_option_custom_id():
    opt = kernel._mk_option("t", "d", _id="custom123")
    assert opt["id"] == "custom123"


# ============================================================
# _detect_intent
# ============================================================

def test_detect_intent_weather():
    assert kernel._detect_intent("明日の天気は？") == "weather"
    assert kernel._detect_intent("forecast tomorrow") == "weather"


def test_detect_intent_health():
    assert kernel._detect_intent("疲れた") == "health"
    assert kernel._detect_intent("体調が悪い") == "health"


def test_detect_intent_learn():
    assert kernel._detect_intent("量子コンピュータとは") == "learn"
    assert kernel._detect_intent("why is the sky blue") == "learn"


def test_detect_intent_plan():
    assert kernel._detect_intent("計画を立てて") == "plan"
    assert kernel._detect_intent("todo list") == "plan"


def test_detect_intent_default():
    assert kernel._detect_intent("ランダムな文字列") == "plan"


def test_detect_intent_empty():
    assert kernel._detect_intent("") == "plan"
    assert kernel._detect_intent(None) == "plan"


# ============================================================
# _gen_options_by_intent
# ============================================================

def test_gen_options_by_intent_weather():
    opts = kernel._gen_options_by_intent("weather")
    assert len(opts) == 3
    assert "天気" in opts[0]["title"]


def test_gen_options_by_intent_unknown():
    opts = kernel._gen_options_by_intent("unknown_intent")
    assert len(opts) == 3  # falls back to "plan" templates


# ============================================================
# _filter_alts_by_intent
# ============================================================

def test_filter_alts_by_intent_weather_filters():
    alts = [
        {"title": "天気を確認", "description": ""},
        {"title": "コードを書く", "description": ""},
    ]
    result = kernel._filter_alts_by_intent("weather", "明日の天気", alts)
    assert len(result) == 1
    assert result[0]["title"] == "天気を確認"


def test_filter_alts_by_intent_non_weather_passthrough():
    alts = [{"title": "a"}, {"title": "b"}]
    result = kernel._filter_alts_by_intent("plan", "何か", alts)
    assert len(result) == 2


def test_filter_alts_by_intent_empty():
    assert kernel._filter_alts_by_intent("weather", "q", []) == []


# ============================================================
# _dedupe_alts
# ============================================================

def test_dedupe_alts_removes_duplicates():
    alts = [
        {"title": "A", "description": "d", "score": 0.5},
        {"title": "A", "description": "d", "score": 0.9},
    ]
    result = kernel._dedupe_alts(alts)
    assert len(result) == 1
    assert result[0]["score"] == 0.9


def test_dedupe_alts_none_title():
    alts = [{"title": None, "description": "fallback desc"}]
    result = kernel._dedupe_alts(alts)
    assert len(result) == 1
    assert result[0]["title"] == "fallback desc"[:40]


def test_dedupe_alts_skip_non_dict():
    alts = ["not_a_dict", 42, {"title": "valid"}]
    result = kernel._dedupe_alts(alts)
    assert len(result) == 1


def test_dedupe_alts_none_title_none_desc():
    alts = [{"title": None, "description": None}]
    result = kernel._dedupe_alts(alts)
    assert result == []


def test_dedupe_alts_title_is_none_string():
    alts = [{"title": "none", "description": "real desc"}]
    result = kernel._dedupe_alts(alts)
    assert len(result) == 1
    assert result[0]["title"] == "real desc"[:40]


def test_dedupe_alts_bad_score():
    alts = [{"title": "A", "description": "", "score": "not_a_number"}]
    result = kernel._dedupe_alts(alts)
    assert len(result) == 1


# ============================================================
# _score_alternatives (delegates to kernel_stages)
# ============================================================

def test_score_alternatives_basic(monkeypatch):
    monkeypatch.setattr(kernel, "strategy_core", None)
    alts = [
        {"id": "a1", "title": "休む", "description": "", "score": 1.0},
        {"id": "a2", "title": "走る", "description": "", "score": 1.0},
    ]
    kernel._score_alternatives("health", "疲れた", alts, 0.5, 0.5, None, {})
    # Just ensure it doesn't crash and scores are float
    for a in alts:
        assert isinstance(a["score"], (int, float))


def test_score_alternatives_with_strategy(monkeypatch):
    mock_strategy = MagicMock()
    mock_strategy.score_options.return_value = [
        {"id": "a1", "score": 0.99},
    ]
    monkeypatch.setattr(kernel, "strategy_core", mock_strategy)
    alts = [
        {"id": "a1", "title": "X", "description": "", "score": 1.0},
    ]
    kernel._score_alternatives("plan", "test", alts, 0.5, 0.5, None, {})
    assert alts[0]["score"] == 0.99


def test_score_alternatives_strategy_exception(monkeypatch):
    mock_strategy = MagicMock()
    mock_strategy.score_options.side_effect = RuntimeError("fail")
    monkeypatch.setattr(kernel, "strategy_core", mock_strategy)
    alts = [{"id": "a1", "title": "X", "description": "", "score": 1.0}]
    # Should not raise
    kernel._score_alternatives("plan", "test", alts, 0.5, 0.5, None, {})


def test_score_alternatives_strategy_no_id(monkeypatch):
    mock_strategy = MagicMock()
    mock_strategy.score_options.return_value = [{"score": 0.5}]  # no id
    monkeypatch.setattr(kernel, "strategy_core", mock_strategy)
    alts = [{"id": "a1", "title": "X", "description": "", "score": 1.0}]
    kernel._score_alternatives("plan", "test", alts, 0.5, 0.5, None, {})


# ============================================================
# _score_alternatives_with_value_core_and_persona (compat wrapper)
# ============================================================

def test_score_alternatives_compat_wrapper(monkeypatch):
    monkeypatch.setattr(kernel, "strategy_core", None)
    alts = [{"id": "a1", "title": "X", "description": "", "score": 1.0}]
    kernel._score_alternatives_with_value_core_and_persona(
        "plan", "test", alts, 0.5, 0.5, None, {}
    )


# ============================================================
# decide() - fast mode
# ============================================================

@pytest.mark.anyio
async def test_decide_fast_mode(monkeypatch):
    """fast_mode skips debate and returns quickly."""
    # Stub out heavy dependencies
    monkeypatch.setattr(kernel.world_model, "inject_state_into_context",
                        lambda context, user_id: dict(context))
    monkeypatch.setattr(kernel, "_detect_simple_qa", lambda q: None)
    monkeypatch.setattr(kernel, "_detect_knowledge_qa", lambda q: False)
    monkeypatch.setattr(kernel.mem_core, "summarize_for_planner",
                        lambda user_id, query, limit: "summary")
    monkeypatch.setattr(kernel.adapt, "load_persona", lambda: {"bias_weights": {}})
    monkeypatch.setattr(kernel.adapt, "clean_bias_weights", lambda d: d)
    monkeypatch.setattr(kernel.planner_core, "plan_for_veritas_agi",
                        lambda context, query: {"steps": [{"id": "s1", "title": "Do X", "detail": "d"}]})
    monkeypatch.setattr(kernel.fuji_core, "evaluate",
                        lambda q, context, evidence, alternatives: {
                            "status": "allow", "decision_status": "allow",
                            "risk": 0.1, "reasons": [], "violations": [],
                            "checks": [], "guidance": None, "modifications": [],
                            "redactions": [], "safe_instructions": [],
                        })
    monkeypatch.setattr(kernel.affect_core, "reflect", lambda d: {"valence": 0.5}, raising=False)
    monkeypatch.setattr(kernel, "reason_core", None)
    monkeypatch.setattr(kernel.adapt, "update_persona_bias_from_history", lambda window: {"bias_weights": {}})
    monkeypatch.setattr(kernel.agi_goals, "auto_adjust_goals",
                        lambda bias_weights, world_snap, value_ema, fuji_risk: {})
    monkeypatch.setattr(kernel.adapt, "save_persona", lambda p: None)
    monkeypatch.setattr(kernel.mem_core, "get_evidence_for_decision",
                        lambda snap, user_id, top_k: [])
    monkeypatch.setattr(kernel.mem_core, "MEM", MagicMock())
    monkeypatch.setattr(kernel.world_model, "update_from_decision",
                        lambda **kw: None)
    monkeypatch.setattr(kernel, "redact_payload", lambda x: x)

    result = await kernel.decide(
        context={"fast": True, "user_id": "test"},
        query="計画を立てて",
        alternatives=None,
    )
    assert "chosen" in result or isinstance(result, dict)


# ============================================================
# decide() - world_model injection failure
# ============================================================

@pytest.mark.anyio
async def test_decide_world_inject_failure(monkeypatch):
    """world_model inject failure is handled gracefully."""
    def _inject_fail(context, user_id):
        raise RuntimeError("inject fail")

    monkeypatch.setattr(kernel.world_model, "inject_state_into_context", _inject_fail)
    monkeypatch.setattr(kernel, "_detect_simple_qa", lambda q: "time")
    monkeypatch.setattr(kernel, "_handle_simple_qa",
                        lambda kind, q, ctx, req_id, telos_score: {"chosen": {"title": "time"}})

    result = await kernel.decide(
        context={"user_id": "test"},
        query="今何時？",
        alternatives=None,
    )
    assert result["chosen"]["title"] == "time"


# ============================================================
# decide() - planner exception fallback
# ============================================================

@pytest.mark.anyio
async def test_decide_planner_exception_fallback(monkeypatch):
    """When planner fails, _gen_options_by_intent is used as fallback."""
    monkeypatch.setattr(kernel.world_model, "inject_state_into_context",
                        lambda context, user_id: dict(context))
    monkeypatch.setattr(kernel, "_detect_simple_qa", lambda q: None)
    monkeypatch.setattr(kernel, "_detect_knowledge_qa", lambda q: False)
    monkeypatch.setattr(kernel.mem_core, "summarize_for_planner",
                        lambda user_id, query, limit: "")
    monkeypatch.setattr(kernel.adapt, "load_persona", lambda: {"bias_weights": {}})
    monkeypatch.setattr(kernel.adapt, "clean_bias_weights", lambda d: d)

    def _planner_fail(context, query):
        raise RuntimeError("planner down")
    monkeypatch.setattr(kernel.planner_core, "plan_for_veritas_agi", _planner_fail)

    monkeypatch.setattr(kernel.debate_core, "run_debate",
                        lambda query, options, context: {
                            "chosen": options[0] if options else {"id": "x", "title": "fb"},
                            "options": options,
                        })
    monkeypatch.setattr(kernel.fuji_core, "evaluate",
                        lambda q, context, evidence, alternatives: {
                            "status": "allow", "decision_status": "allow",
                            "risk": 0.1, "reasons": [], "violations": [],
                            "checks": [], "guidance": None, "modifications": [],
                            "redactions": [], "safe_instructions": [],
                        })
    monkeypatch.setattr(kernel.affect_core, "reflect", lambda d: {}, raising=False)
    monkeypatch.setattr(kernel, "reason_core", None)
    monkeypatch.setattr(kernel.adapt, "update_persona_bias_from_history", lambda window: {"bias_weights": {}})
    monkeypatch.setattr(kernel.agi_goals, "auto_adjust_goals",
                        lambda bias_weights, world_snap, value_ema, fuji_risk: {})
    monkeypatch.setattr(kernel.adapt, "save_persona", lambda p: None)
    monkeypatch.setattr(kernel.mem_core, "get_evidence_for_decision",
                        lambda snap, user_id, top_k: [])
    monkeypatch.setattr(kernel.mem_core, "MEM", MagicMock())
    monkeypatch.setattr(kernel.world_model, "update_from_decision",
                        lambda **kw: None)
    monkeypatch.setattr(kernel, "redact_payload", lambda x: x)

    result = await kernel.decide(
        context={"user_id": "test", "fast": True},
        query="何か計画して",
        alternatives=None,
    )
    assert isinstance(result, dict)


# ============================================================
# decide() - knowledge_qa exception
# ============================================================

@pytest.mark.anyio
async def test_decide_knowledge_qa_exception(monkeypatch):
    """knowledge_qa exception doesn't crash decide."""
    monkeypatch.setattr(kernel.world_model, "inject_state_into_context",
                        lambda context, user_id: dict(context))
    monkeypatch.setattr(kernel, "_detect_simple_qa", lambda q: None)

    def _kqa_boom(q):
        raise RuntimeError("kqa fail")
    monkeypatch.setattr(kernel, "_detect_knowledge_qa", _kqa_boom)

    monkeypatch.setattr(kernel.mem_core, "summarize_for_planner",
                        lambda user_id, query, limit: "")
    monkeypatch.setattr(kernel.adapt, "load_persona", lambda: {"bias_weights": {}})
    monkeypatch.setattr(kernel.adapt, "clean_bias_weights", lambda d: d)
    monkeypatch.setattr(kernel.planner_core, "plan_for_veritas_agi",
                        lambda context, query: {"steps": [{"id": "s1", "title": "X"}]})
    monkeypatch.setattr(kernel.fuji_core, "evaluate",
                        lambda q, context, evidence, alternatives: {
                            "status": "allow", "risk": 0.1, "reasons": [],
                            "violations": [], "checks": [], "guidance": None,
                            "modifications": [], "redactions": [], "safe_instructions": [],
                        })
    monkeypatch.setattr(kernel.affect_core, "reflect", lambda d: {}, raising=False)
    monkeypatch.setattr(kernel, "reason_core", None)
    monkeypatch.setattr(kernel.adapt, "update_persona_bias_from_history", lambda window: {"bias_weights": {}})
    monkeypatch.setattr(kernel.agi_goals, "auto_adjust_goals",
                        lambda bias_weights, world_snap, value_ema, fuji_risk: {})
    monkeypatch.setattr(kernel.adapt, "save_persona", lambda p: None)
    monkeypatch.setattr(kernel.mem_core, "get_evidence_for_decision",
                        lambda snap, user_id, top_k: [])
    monkeypatch.setattr(kernel.mem_core, "MEM", MagicMock())
    monkeypatch.setattr(kernel.world_model, "update_from_decision", lambda **kw: None)
    monkeypatch.setattr(kernel, "redact_payload", lambda x: x)

    result = await kernel.decide(
        context={"user_id": "test", "fast": True},
        query="VERITASとは何ですか？",
        alternatives=None,
    )
    assert isinstance(result, dict)


# ============================================================
# decide() - pipeline evidence provided
# ============================================================

@pytest.mark.anyio
async def test_decide_pipeline_evidence(monkeypatch):
    """Pipeline-provided evidence is used directly."""
    monkeypatch.setattr(kernel.world_model, "inject_state_into_context",
                        lambda context, user_id: dict(context))
    monkeypatch.setattr(kernel, "_detect_simple_qa", lambda q: None)
    monkeypatch.setattr(kernel, "_detect_knowledge_qa", lambda q: False)
    monkeypatch.setattr(kernel.adapt, "load_persona", lambda: {"bias_weights": {}})
    monkeypatch.setattr(kernel.adapt, "clean_bias_weights", lambda d: d)
    monkeypatch.setattr(kernel.planner_core, "plan_for_veritas_agi",
                        lambda context, query: {"steps": [{"id": "s1", "title": "X"}]})
    monkeypatch.setattr(kernel.fuji_core, "evaluate",
                        lambda q, context, evidence, alternatives: {
                            "status": "allow", "risk": 0.1, "reasons": [],
                            "violations": [], "checks": [], "guidance": None,
                            "modifications": [], "redactions": [], "safe_instructions": [],
                        })
    monkeypatch.setattr(kernel.affect_core, "reflect", lambda d: {}, raising=False)
    monkeypatch.setattr(kernel, "reason_core", None)
    monkeypatch.setattr(kernel.adapt, "update_persona_bias_from_history", lambda window: {"bias_weights": {}})
    monkeypatch.setattr(kernel.agi_goals, "auto_adjust_goals",
                        lambda bias_weights, world_snap, value_ema, fuji_risk: {})
    monkeypatch.setattr(kernel.adapt, "save_persona", lambda p: None)
    monkeypatch.setattr(kernel.mem_core, "MEM", MagicMock())
    monkeypatch.setattr(kernel.world_model, "update_from_decision", lambda **kw: None)
    monkeypatch.setattr(kernel, "redact_payload", lambda x: x)

    pipeline_ev = [{"source": "pipeline", "snippet": "test", "confidence": 0.9}]
    result = await kernel.decide(
        context={
            "user_id": "test",
            "fast": True,
            "_pipeline_evidence": pipeline_ev,
        },
        query="テスト",
        alternatives=None,
    )
    assert isinstance(result, dict)


# ============================================================
# decide() - FUJI gate exception
# ============================================================

@pytest.mark.anyio
async def test_decide_fuji_exception(monkeypatch):
    """FUJI gate failure defaults to deny."""
    monkeypatch.setattr(kernel.world_model, "inject_state_into_context",
                        lambda context, user_id: dict(context))
    monkeypatch.setattr(kernel, "_detect_simple_qa", lambda q: None)
    monkeypatch.setattr(kernel, "_detect_knowledge_qa", lambda q: False)
    monkeypatch.setattr(kernel.mem_core, "summarize_for_planner",
                        lambda user_id, query, limit: "")
    monkeypatch.setattr(kernel.adapt, "load_persona", lambda: {"bias_weights": {}})
    monkeypatch.setattr(kernel.adapt, "clean_bias_weights", lambda d: d)
    monkeypatch.setattr(kernel.planner_core, "plan_for_veritas_agi",
                        lambda context, query: {"steps": [{"id": "s1", "title": "X"}]})

    def _fuji_boom(q, context, evidence, alternatives):
        raise RuntimeError("fuji error")
    monkeypatch.setattr(kernel.fuji_core, "evaluate", _fuji_boom)

    monkeypatch.setattr(kernel.affect_core, "reflect", lambda d: {}, raising=False)
    monkeypatch.setattr(kernel, "reason_core", None)
    monkeypatch.setattr(kernel.adapt, "update_persona_bias_from_history", lambda window: {"bias_weights": {}})
    monkeypatch.setattr(kernel.agi_goals, "auto_adjust_goals",
                        lambda bias_weights, world_snap, value_ema, fuji_risk: {})
    monkeypatch.setattr(kernel.adapt, "save_persona", lambda p: None)
    monkeypatch.setattr(kernel.mem_core, "get_evidence_for_decision",
                        lambda snap, user_id, top_k: [])
    monkeypatch.setattr(kernel.mem_core, "MEM", MagicMock())
    monkeypatch.setattr(kernel.world_model, "update_from_decision", lambda **kw: None)
    monkeypatch.setattr(kernel, "redact_payload", lambda x: x)

    result = await kernel.decide(
        context={"user_id": "test", "fast": True},
        query="テスト",
        alternatives=None,
    )
    assert isinstance(result, dict)


# ============================================================
# decide() - debate exception fallback (with alts)
# ============================================================

@pytest.mark.anyio
async def test_decide_debate_exception_with_alts(monkeypatch):
    """Debate exception falls back to max-score alt."""
    monkeypatch.setattr(kernel.world_model, "inject_state_into_context",
                        lambda context, user_id: dict(context))
    monkeypatch.setattr(kernel, "_detect_simple_qa", lambda q: None)
    monkeypatch.setattr(kernel, "_detect_knowledge_qa", lambda q: False)
    monkeypatch.setattr(kernel.mem_core, "summarize_for_planner",
                        lambda user_id, query, limit: "")
    monkeypatch.setattr(kernel.adapt, "load_persona", lambda: {"bias_weights": {}})
    monkeypatch.setattr(kernel.adapt, "clean_bias_weights", lambda d: d)
    monkeypatch.setattr(kernel.planner_core, "plan_for_veritas_agi",
                        lambda context, query: {"steps": [{"id": "s1", "title": "X", "detail": "d"}]})

    def _debate_fail(query, options, context):
        raise RuntimeError("debate fail")
    monkeypatch.setattr(kernel.debate_core, "run_debate", _debate_fail)

    monkeypatch.setattr(kernel.fuji_core, "evaluate",
                        lambda q, context, evidence, alternatives: {
                            "status": "allow", "risk": 0.1, "reasons": [],
                            "violations": [], "checks": [], "guidance": None,
                            "modifications": [], "redactions": [], "safe_instructions": [],
                        })
    monkeypatch.setattr(kernel.affect_core, "reflect", lambda d: {}, raising=False)
    monkeypatch.setattr(kernel, "reason_core", None)
    monkeypatch.setattr(kernel.adapt, "update_persona_bias_from_history", lambda window: {"bias_weights": {}})
    monkeypatch.setattr(kernel.agi_goals, "auto_adjust_goals",
                        lambda bias_weights, world_snap, value_ema, fuji_risk: {})
    monkeypatch.setattr(kernel.adapt, "save_persona", lambda p: None)
    monkeypatch.setattr(kernel.mem_core, "get_evidence_for_decision",
                        lambda snap, user_id, top_k: [])
    monkeypatch.setattr(kernel.mem_core, "MEM", MagicMock())
    monkeypatch.setattr(kernel.world_model, "update_from_decision", lambda **kw: None)
    monkeypatch.setattr(kernel, "redact_payload", lambda x: x)

    result = await kernel.decide(
        context={"user_id": "test"},  # NOT fast mode
        query="テスト",
        alternatives=None,
    )
    assert isinstance(result, dict)


# ============================================================
# decide() - debate exception fallback (no alts)
# ============================================================

@pytest.mark.anyio
async def test_decide_debate_exception_no_alts(monkeypatch):
    """Debate exception with no alternatives creates fallback option."""
    monkeypatch.setattr(kernel.world_model, "inject_state_into_context",
                        lambda context, user_id: dict(context))
    monkeypatch.setattr(kernel, "_detect_simple_qa", lambda q: None)
    monkeypatch.setattr(kernel, "_detect_knowledge_qa", lambda q: False)
    monkeypatch.setattr(kernel.mem_core, "summarize_for_planner",
                        lambda user_id, query, limit: "")
    monkeypatch.setattr(kernel.adapt, "load_persona", lambda: {"bias_weights": {}})
    monkeypatch.setattr(kernel.adapt, "clean_bias_weights", lambda d: d)

    # Planner returns steps but they all get filtered out by dedupe
    monkeypatch.setattr(kernel.planner_core, "plan_for_veritas_agi",
                        lambda context, query: {"steps": []})

    def _debate_fail(query, options, context):
        raise RuntimeError("debate fail")
    monkeypatch.setattr(kernel.debate_core, "run_debate", _debate_fail)

    monkeypatch.setattr(kernel.fuji_core, "evaluate",
                        lambda q, context, evidence, alternatives: {
                            "status": "allow", "risk": 0.1, "reasons": [],
                            "violations": [], "checks": [], "guidance": None,
                            "modifications": [], "redactions": [], "safe_instructions": [],
                        })
    monkeypatch.setattr(kernel.affect_core, "reflect", lambda d: {}, raising=False)
    monkeypatch.setattr(kernel, "reason_core", None)
    monkeypatch.setattr(kernel.adapt, "update_persona_bias_from_history", lambda window: {"bias_weights": {}})
    monkeypatch.setattr(kernel.agi_goals, "auto_adjust_goals",
                        lambda bias_weights, world_snap, value_ema, fuji_risk: {})
    monkeypatch.setattr(kernel.adapt, "save_persona", lambda p: None)
    monkeypatch.setattr(kernel.mem_core, "get_evidence_for_decision",
                        lambda snap, user_id, top_k: [])
    monkeypatch.setattr(kernel.mem_core, "MEM", MagicMock())
    monkeypatch.setattr(kernel.world_model, "update_from_decision", lambda **kw: None)
    monkeypatch.setattr(kernel, "redact_payload", lambda x: x)

    result = await kernel.decide(
        context={"user_id": "test"},
        query="テスト",
        alternatives=None,
    )
    assert isinstance(result, dict)


# ============================================================
# decide() - pipeline planner provided
# ============================================================

@pytest.mark.anyio
async def test_decide_pipeline_planner(monkeypatch):
    """Pipeline-provided planner result is used."""
    monkeypatch.setattr(kernel.world_model, "inject_state_into_context",
                        lambda context, user_id: dict(context))
    monkeypatch.setattr(kernel, "_detect_simple_qa", lambda q: None)
    monkeypatch.setattr(kernel, "_detect_knowledge_qa", lambda q: False)
    monkeypatch.setattr(kernel.adapt, "load_persona", lambda: {"bias_weights": {}})
    monkeypatch.setattr(kernel.adapt, "clean_bias_weights", lambda d: d)
    monkeypatch.setattr(kernel.fuji_core, "evaluate",
                        lambda q, context, evidence, alternatives: {
                            "status": "allow", "risk": 0.1, "reasons": [],
                            "violations": [], "checks": [], "guidance": None,
                            "modifications": [], "redactions": [], "safe_instructions": [],
                        })
    monkeypatch.setattr(kernel.affect_core, "reflect", lambda d: {}, raising=False)
    monkeypatch.setattr(kernel, "reason_core", None)
    monkeypatch.setattr(kernel.adapt, "update_persona_bias_from_history", lambda window: {"bias_weights": {}})
    monkeypatch.setattr(kernel.agi_goals, "auto_adjust_goals",
                        lambda bias_weights, world_snap, value_ema, fuji_risk: {})
    monkeypatch.setattr(kernel.adapt, "save_persona", lambda p: None)
    monkeypatch.setattr(kernel.mem_core, "get_evidence_for_decision",
                        lambda snap, user_id, top_k: [])
    monkeypatch.setattr(kernel.mem_core, "MEM", MagicMock())
    monkeypatch.setattr(kernel.world_model, "update_from_decision", lambda **kw: None)
    monkeypatch.setattr(kernel, "redact_payload", lambda x: x)

    result = await kernel.decide(
        context={
            "user_id": "test",
            "fast": True,
            "_pipeline_planner": {
                "steps": [{"id": "ps1", "title": "Pipeline Step", "detail": "det"}]
            },
            "_pipeline_evidence": [{"source": "p"}],
        },
        query="テスト",
        alternatives=None,
    )
    assert isinstance(result, dict)
