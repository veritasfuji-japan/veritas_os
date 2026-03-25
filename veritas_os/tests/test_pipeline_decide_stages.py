# veritas_os/tests/test_pipeline_decide_stages.py
# -*- coding: utf-8 -*-
"""Tests for core/pipeline_decide_stages.py — all 9 stage functions."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock, AsyncMock

import pytest

from veritas_os.core.pipeline_types import PipelineContext
from veritas_os.core.pipeline_decide_stages import (
    stage_normalize_options,
    stage_absorb_raw_results,
    stage_fallback_alternatives,
    stage_model_boost,
    stage_debate,
    stage_critique_async,
    stage_value_learning_ema,
    stage_compute_metrics,
    stage_evidence_hardening,
)


# ---------- helpers ----------

def _identity_norm_alt(a: Any) -> Dict[str, Any]:
    """Minimal _norm_alt stub that returns dict as-is or wraps."""
    if isinstance(a, dict):
        a.setdefault("id", "test")
        a.setdefault("title", "test")
        a.setdefault("score", 1.0)
        return a
    return {"id": "test", "title": str(a), "score": 1.0}


def _make_ctx(**overrides) -> PipelineContext:
    ctx = PipelineContext()
    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


# =========================================================
# Stage 3: stage_normalize_options
# =========================================================

class TestStageNormalizeOptions:
    def test_explicit_options_from_body(self):
        ctx = _make_ctx(body={"options": [{"id": "a", "title": "A"}]})
        stage_normalize_options(ctx, _norm_alt=_identity_norm_alt)
        assert len(ctx.alternatives) == 1
        assert ctx.alternatives[0]["id"] == "a"

    def test_alternatives_key_also_accepted(self):
        ctx = _make_ctx(body={"alternatives": [{"id": "b", "title": "B"}]})
        stage_normalize_options(ctx, _norm_alt=_identity_norm_alt)
        assert len(ctx.alternatives) == 1
        assert ctx.alternatives[0]["id"] == "b"

    def test_non_list_options_treated_as_empty(self):
        ctx = _make_ctx(body={"options": "not_a_list"})
        stage_normalize_options(ctx, _norm_alt=_identity_norm_alt)
        # Should fallback (not veritas query, so empty)
        assert ctx.explicit_options == []

    def test_veritas_query_plan_steps(self):
        ctx = _make_ctx(
            body={},
            is_veritas_query=True,
            plan={"steps": [{"title": "Step1", "description": "Do thing"}]},
        )
        stage_normalize_options(ctx, _norm_alt=_identity_norm_alt)
        assert len(ctx.input_alts) == 1
        assert "Step1" in ctx.input_alts[0]["title"]

    def test_veritas_query_default_fallback(self):
        ctx = _make_ctx(body={}, is_veritas_query=True, plan={"steps": []})
        stage_normalize_options(ctx, _norm_alt=_identity_norm_alt)
        assert len(ctx.input_alts) == 4  # 4 default alternatives

    def test_web_evidence_reset_if_non_list(self):
        ctx = _make_ctx(body={"options": [{"id": "x", "title": "X"}]}, web_evidence="bad")
        stage_normalize_options(ctx, _norm_alt=_identity_norm_alt)
        assert ctx.web_evidence == []

    def test_non_dict_items_filtered_out(self):
        ctx = _make_ctx(body={"options": [{"id": "a", "title": "A"}, "not_dict", 42]})
        stage_normalize_options(ctx, _norm_alt=_identity_norm_alt)
        assert len(ctx.alternatives) == 1

    def test_plan_non_dict_steps_skipped(self):
        ctx = _make_ctx(
            body={},
            is_veritas_query=True,
            plan={"steps": ["not_dict", {"title": "Valid"}]},
        )
        stage_normalize_options(ctx, _norm_alt=_identity_norm_alt)
        assert len(ctx.input_alts) == 1


# =========================================================
# Stage 4b: stage_absorb_raw_results
# =========================================================

class TestStageAbsorbRawResults:
    def _stubs(self):
        return dict(
            _norm_alt=_identity_norm_alt,
            _normalize_critique_payload=lambda c: c if isinstance(c, dict) else {},
            _merge_extras_preserving_contract=lambda base, ext, **kw: {**base, **ext},
        )

    def test_empty_raw(self):
        ctx = _make_ctx(raw={})
        stage_absorb_raw_results(ctx, **self._stubs())
        assert ctx.critique == {}
        assert ctx.telos == 0.0

    def test_evidence_absorbed(self):
        ctx = _make_ctx(raw={"evidence": [{"source": "web", "snippet": "hello"}]})
        stage_absorb_raw_results(ctx, **self._stubs())
        assert len(ctx.evidence) == 1

    def test_critique_absorbed(self):
        ctx = _make_ctx(raw={"critique": {"ok": True, "summary": "good"}})
        stage_absorb_raw_results(ctx, **self._stubs())
        assert ctx.critique["ok"] is True

    def test_telos_score_parsed(self):
        ctx = _make_ctx(raw={"telos_score": 0.85})
        stage_absorb_raw_results(ctx, **self._stubs())
        assert ctx.telos == 0.85

    def test_telos_score_invalid_fallback(self):
        ctx = _make_ctx(raw={"telos_score": "not_a_number"})
        stage_absorb_raw_results(ctx, **self._stubs())
        assert ctx.telos == 0.0

    def test_fuji_dict_absorbed(self):
        ctx = _make_ctx(raw={"fuji": {"status": "allow"}})
        stage_absorb_raw_results(ctx, **self._stubs())
        assert ctx.fuji_dict["status"] == "allow"

    def test_alternatives_from_core_when_no_explicit(self):
        ctx = _make_ctx(
            raw={"alternatives": [{"id": "c1", "title": "Core alt"}]},
            explicit_options=[],
        )
        stage_absorb_raw_results(ctx, **self._stubs())
        assert len(ctx.alternatives) == 1

    def test_alternatives_not_overwritten_when_explicit(self):
        ctx = _make_ctx(
            raw={"alternatives": [{"id": "c1", "title": "Core alt"}]},
            explicit_options=[{"id": "e1", "title": "Explicit"}],
            alternatives=[{"id": "e1", "title": "Explicit"}],
        )
        stage_absorb_raw_results(ctx, **self._stubs())
        assert ctx.alternatives[0]["id"] == "e1"

    def test_extras_merged(self):
        ctx = _make_ctx(
            raw={"extras": {"debug": True}},
            response_extras={},
        )
        stage_absorb_raw_results(ctx, **self._stubs())
        assert ctx.response_extras.get("debug") is True

    def test_debate_absorbed(self):
        ctx = _make_ctx(raw={"debate": [{"side": "pro"}]})
        stage_absorb_raw_results(ctx, **self._stubs())
        assert len(ctx.debate) == 1


# =========================================================
# Stage 4c: stage_fallback_alternatives
# =========================================================

class TestStageFallbackAlternatives:
    def test_uses_existing_alternatives(self):
        alts = [{"id": "a", "title": "A", "score": 1.0}]
        ctx = _make_ctx(alternatives=alts)
        stage_fallback_alternatives(
            ctx, _norm_alt=_identity_norm_alt, _dedupe_alts=lambda x: x,
        )
        assert ctx.alternatives[0]["id"] == "a"

    def test_fallback_when_empty(self):
        ctx = _make_ctx(alternatives=[])
        stage_fallback_alternatives(
            ctx, _norm_alt=_identity_norm_alt, _dedupe_alts=lambda x: x,
        )
        assert len(ctx.alternatives) == 3

    def test_dedupe_called(self):
        called = []
        def _dedupe(alts):
            called.append(True)
            return alts[:1]
        ctx = _make_ctx(alternatives=[])
        stage_fallback_alternatives(
            ctx, _norm_alt=_identity_norm_alt, _dedupe_alts=_dedupe,
        )
        assert len(called) == 1


# =========================================================
# Stage 4d: stage_model_boost
# =========================================================

class TestStageModelBoost:
    def _base_kwargs(self, world_model=None, mem_vec=None, mem_clf=None):
        return dict(
            world_model=world_model,
            MEM_VEC=mem_vec,
            MEM_CLF=mem_clf,
            _allow_prob=lambda text: 0.8,
            _mem_model_path=lambda: "/tmp/model.pkl",
            _warn=lambda msg: None,
        )

    def test_no_world_model(self):
        ctx = _make_ctx(
            alternatives=[{"id": "a", "title": "A", "score": 1.0}],
            raw={},
        )
        stage_model_boost(ctx, **self._base_kwargs())
        assert ctx.alternatives[0]["score"] == 1.0

    def test_world_model_boost(self):
        wm = MagicMock()
        wm.simulate.return_value = {"utility": 1.0, "confidence": 1.0}
        ctx = _make_ctx(
            alternatives=[{"id": "a", "title": "A", "score": 1.0}],
            raw={},
            context={"user_id": "u1"},
        )
        stage_model_boost(ctx, **self._base_kwargs(world_model=wm))
        assert ctx.alternatives[0]["score"] > 1.0
        assert "world" in ctx.alternatives[0]

    def test_world_model_exception_resilience(self):
        wm = MagicMock()
        wm.simulate.side_effect = RuntimeError("boom")
        ctx = _make_ctx(
            alternatives=[{"id": "a", "title": "A", "score": 1.0}],
            raw={},
        )
        warnings = []
        stage_model_boost(ctx, **{**self._base_kwargs(world_model=wm), "_warn": warnings.append})
        assert any("WorldModelOS" in w for w in warnings)

    def test_mem_model_boost(self):
        mem_clf = MagicMock()
        mem_clf.classes_ = MagicMock()
        mem_clf.classes_.tolist.return_value = ["allow", "deny"]
        ctx = _make_ctx(
            alternatives=[{"id": "a", "title": "A", "score": 1.0}],
            raw={},
            response_extras={},
        )
        stage_model_boost(
            ctx, **self._base_kwargs(mem_vec=MagicMock(), mem_clf=mem_clf),
        )
        assert ctx.alternatives[0]["score"] > 1.0
        assert ctx.response_extras["metrics"]["mem_model"]["applied"] is True

    def test_mem_model_not_loaded(self):
        ctx = _make_ctx(
            alternatives=[{"id": "a", "title": "A", "score": 1.0}],
            raw={},
            response_extras={},
        )
        stage_model_boost(ctx, **self._base_kwargs())
        assert ctx.response_extras["metrics"]["mem_model"]["applied"] is False

    def test_chosen_from_highest_score(self):
        ctx = _make_ctx(
            alternatives=[
                {"id": "a", "title": "A", "score": 0.5},
                {"id": "b", "title": "B", "score": 0.9},
            ],
            raw={},
            response_extras={},
        )
        stage_model_boost(ctx, **self._base_kwargs())
        assert ctx.chosen["id"] == "b"

    def test_chosen_from_raw_if_present(self):
        ctx = _make_ctx(
            alternatives=[{"id": "a", "title": "A", "score": 1.0}],
            raw={"chosen": {"id": "raw_chosen", "title": "Raw"}},
            response_extras={},
        )
        stage_model_boost(ctx, **self._base_kwargs())
        assert ctx.chosen["id"] == "raw_chosen"

    def test_mem_model_error_recorded(self):
        ctx = _make_ctx(
            alternatives=[{"id": "a", "title": "A", "score": 1.0}],
            raw={},
            response_extras={},
        )
        stage_model_boost(
            ctx,
            world_model=None,
            MEM_VEC=MagicMock(),
            MEM_CLF=MagicMock(spec=[]),  # no classes_ attr
            _allow_prob=MagicMock(side_effect=ValueError("bad")),
            _mem_model_path=lambda: "/tmp/m.pkl",
            _warn=lambda m: None,
        )
        assert ctx.response_extras["metrics"]["mem_model"]["applied"] is False
        assert "error" in ctx.response_extras["metrics"]["mem_model"]


# =========================================================
# Stage 5: stage_debate
# =========================================================

class TestStageDebate:
    def test_no_debate_core(self):
        ctx = _make_ctx(alternatives=[{"id": "a"}], fast_mode=False)
        stage_debate(ctx, debate_core=None, _warn=lambda m: None)
        assert ctx.alternatives == [{"id": "a"}]

    def test_fast_mode_skips(self):
        dc = MagicMock()
        ctx = _make_ctx(alternatives=[{"id": "a"}], fast_mode=True)
        stage_debate(ctx, debate_core=dc, _warn=lambda m: None)
        dc.run_debate.assert_not_called()

    def test_debate_updates_alternatives(self):
        dc = MagicMock()
        dc.run_debate.return_value = {
            "options": [{"id": "debated", "title": "D", "verdict": "accept"}],
            "chosen": {"id": "debated", "title": "D"},
            "source": "debate",
            "raw": {},
        }
        ctx = _make_ctx(
            alternatives=[{"id": "a"}],
            fast_mode=False,
            user_id="u1",
            query="test",
            context={},
            response_extras={},
        )
        stage_debate(ctx, debate_core=dc, _warn=lambda m: None)
        assert ctx.alternatives[0]["id"] == "debated"
        assert ctx.chosen["id"] == "debated"

    def test_debate_rejected_verdict_adds_risk_delta(self):
        dc = MagicMock()
        dc.run_debate.return_value = {
            "options": [
                {"id": "o1", "verdict": "reject"},
                {"id": "o2", "verdict": "reject"},
            ],
            "chosen": None,
            "source": "debate",
            "raw": {},
        }
        ctx = _make_ctx(
            alternatives=[{"id": "a"}],
            fast_mode=False,
            query="test",
            context={},
            response_extras={},
        )
        stage_debate(ctx, debate_core=dc, _warn=lambda m: None)
        assert ctx.alternatives[0].get("risk_delta") == 0.10

    def test_debate_exception_resilience(self):
        dc = MagicMock()
        dc.run_debate.side_effect = TypeError("boom")
        ctx = _make_ctx(alternatives=[{"id": "a"}], fast_mode=False, context={}, query="q")
        warnings = []
        stage_debate(ctx, debate_core=dc, _warn=warnings.append)
        assert any("DebateOS" in w for w in warnings)


# =========================================================
# Stage 5b: stage_critique_async
# =========================================================

class TestStageCritiqueAsync:
    @pytest.mark.asyncio
    async def test_existing_critique_preserved(self):
        ctx = _make_ctx(
            critique={"ok": True, "summary": "fine"},
            chosen={"id": "a"},
            evidence=[],
            debate=[],
            context={},
            response_extras={},
        )
        await stage_critique_async(
            ctx,
            _normalize_critique_payload=lambda c: c,
            _run_critique_best_effort=AsyncMock(return_value={}),
            _ensure_critique_required=lambda **kw: kw["critique_obj"],
            _critique_fallback=lambda **kw: {"ok": False},
        )
        assert ctx.critique["ok"] is True

    @pytest.mark.asyncio
    async def test_runs_critique_when_empty(self):
        run_mock = AsyncMock(return_value={"ok": True, "summary": "generated"})
        ctx = _make_ctx(
            critique={},
            chosen={"id": "a"},
            evidence=[],
            debate=[],
            context={},
            user_id="u1",
            query="q",
            response_extras={},
        )
        await stage_critique_async(
            ctx,
            _normalize_critique_payload=lambda c: {},
            _run_critique_best_effort=run_mock,
            _ensure_critique_required=lambda **kw: kw["critique_obj"],
            _critique_fallback=lambda **kw: {"ok": False},
        )
        run_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_triggers_fallback(self):
        ctx = _make_ctx(
            critique={},
            chosen={"id": "a"},
            evidence=[],
            debate=[],
            context={},
            user_id="u1",
            query="q",
            response_extras={},
        )
        await stage_critique_async(
            ctx,
            _normalize_critique_payload=MagicMock(side_effect=RuntimeError("boom")),
            _run_critique_best_effort=AsyncMock(),
            _ensure_critique_required=MagicMock(),
            _critique_fallback=lambda **kw: {"ok": False, "fallback": True},
        )
        assert ctx.critique.get("fallback") is True
        assert ctx.response_extras.get("env_tools", {}).get("critique_degraded") is True

    @pytest.mark.asyncio
    async def test_critique_not_ok_sets_review_required(self):
        ctx = _make_ctx(
            critique={"ok": False},
            chosen={"id": "a"},
            evidence=[],
            debate=[],
            context={},
            response_extras={},
        )
        await stage_critique_async(
            ctx,
            _normalize_critique_payload=lambda c: c,
            _run_critique_best_effort=AsyncMock(),
            _ensure_critique_required=lambda **kw: kw["critique_obj"],
            _critique_fallback=lambda **kw: {},
        )
        assert ctx.response_extras.get("env_tools", {}).get("review_required") is True


# =========================================================
# Stage 6b: stage_value_learning_ema
# =========================================================

class TestStageValueLearningEma:
    def test_ema_update(self):
        valstats = {"alpha": 0.2, "ema": 0.5, "n": 10, "history": []}
        saved = {}
        ctx = _make_ctx(values_payload={"total": 0.8})
        stage_value_learning_ema(
            ctx,
            _load_valstats=lambda: valstats,
            _save_valstats=lambda d: saved.update(d),
            _warn=lambda m: None,
            utc_now_iso_z=lambda: "2026-03-25T00:00:00Z",
        )
        expected = 0.8 * 0.5 + 0.2 * 0.8
        assert abs(ctx.values_payload["ema"] - round(expected, 4)) < 0.001
        assert saved["n"] == 11

    def test_invalid_values_skips(self):
        ctx = _make_ctx(values_payload={"total": "not_a_number"})
        warnings = []
        stage_value_learning_ema(
            ctx,
            _load_valstats=lambda: {"alpha": 0.2, "ema": 0.5, "n": 0},
            _save_valstats=lambda d: None,
            _warn=warnings.append,
            utc_now_iso_z=lambda: "2026-03-25T00:00:00Z",
        )
        assert any("value-learning" in w for w in warnings)

    def test_history_truncated_to_1000(self):
        valstats = {"alpha": 0.1, "ema": 0.5, "n": 0, "history": [{"ts": "t"}] * 1005}
        saved = {}
        ctx = _make_ctx(values_payload={"total": 0.6})
        stage_value_learning_ema(
            ctx,
            _load_valstats=lambda: valstats,
            _save_valstats=lambda d: saved.update(d),
            _warn=lambda m: None,
            utc_now_iso_z=lambda: "now",
        )
        assert len(saved["history"]) == 1000

    def test_non_list_history_reset(self):
        valstats = {"alpha": 0.1, "ema": 0.5, "n": 0, "history": "bad"}
        saved = {}
        ctx = _make_ctx(values_payload={"total": 0.5})
        stage_value_learning_ema(
            ctx,
            _load_valstats=lambda: valstats,
            _save_valstats=lambda d: saved.update(d),
            _warn=lambda m: None,
            utc_now_iso_z=lambda: "now",
        )
        assert isinstance(saved["history"], list)


# =========================================================
# Stage 6c: stage_compute_metrics
# =========================================================

class TestStageComputeMetrics:
    def test_metrics_populated(self):
        ctx = _make_ctx(
            evidence=[
                {"source": "memory_vector", "snippet": "a"},
                {"source": "web", "snippet": "b"},
            ],
            alternatives=[{"id": "a"}],
            value_ema=0.65,
            effective_risk=0.12,
            telos_threshold=0.55,
            response_extras={},
            fast_mode=False,
            context={},
            query="test",
            started_at=time.time() - 0.5,
        )
        called = []
        stage_compute_metrics(
            ctx,
            _ensure_full_contract=lambda *a, **kw: called.append(True),
        )
        m = ctx.response_extras["metrics"]
        assert m["mem_evidence_count"] == 1
        assert m["alts_count"] == 1
        assert m["has_evidence"] is True
        assert m["latency_ms"] > 0
        assert len(called) == 1

    def test_non_dict_metrics_reset(self):
        ctx = _make_ctx(
            evidence=[],
            alternatives=[],
            response_extras={"metrics": "bad"},
            started_at=time.time(),
        )
        stage_compute_metrics(ctx, _ensure_full_contract=lambda *a, **kw: None)
        assert isinstance(ctx.response_extras["metrics"], dict)


# =========================================================
# Stage 6d: stage_evidence_hardening
# =========================================================

class TestStageEvidenceHardening:
    def test_dedupes_and_normalizes(self):
        ctx = _make_ctx(
            evidence=[
                {"source": "web", "snippet": "a"},
                {"source": "web", "snippet": "a"},  # duplicate
            ],
            fast_mode=False,
            query="test",
            context={},
        )
        stage_evidence_hardening(
            ctx,
            evidence_core=None,
            _query_is_step1_hint=lambda q: False,
            _has_step1_minimum_evidence=lambda e: True,
        )
        # After dedup, should have 1
        assert len(ctx.evidence) == 1

    def test_step1_hardening_adds_evidence(self):
        ev_core = MagicMock()
        ev_core.step1_minimum_evidence.return_value = [
            {"source": "fallback", "snippet": "step1 evidence"},
        ]
        ctx = _make_ctx(
            evidence=[],
            fast_mode=False,
            query="初めてのステップ",
            context={},
        )
        stage_evidence_hardening(
            ctx,
            evidence_core=ev_core,
            _query_is_step1_hint=lambda q: True,
            _has_step1_minimum_evidence=lambda e: False,
        )
        assert len(ctx.evidence) == 1

    def test_fast_mode_skips_step1(self):
        ctx = _make_ctx(evidence=[], fast_mode=True, query="test", context={})
        stage_evidence_hardening(
            ctx,
            evidence_core=MagicMock(),
            _query_is_step1_hint=lambda q: True,
            _has_step1_minimum_evidence=lambda e: False,
        )
        assert len(ctx.evidence) == 0

    def test_evidence_max_limit(self):
        evidence = [{"source": f"s{i}", "snippet": f"e{i}"} for i in range(60)]
        ctx = _make_ctx(evidence=evidence, fast_mode=False, query="q", context={})
        stage_evidence_hardening(
            ctx,
            evidence_core=None,
            _query_is_step1_hint=lambda q: False,
            _has_step1_minimum_evidence=lambda e: True,
        )
        assert len(ctx.evidence) <= 50

    def test_non_list_evidence_converted(self):
        ctx = _make_ctx(evidence="bad", fast_mode=True, query="q", context={})
        stage_evidence_hardening(
            ctx,
            evidence_core=None,
            _query_is_step1_hint=lambda q: False,
            _has_step1_minimum_evidence=lambda e: True,
        )
        assert isinstance(ctx.evidence, list)
