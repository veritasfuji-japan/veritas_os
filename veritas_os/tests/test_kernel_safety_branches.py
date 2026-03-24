# -*- coding: utf-8 -*-
"""
kernel.py safety / fallback / compatibility 分岐の追加カバレッジ。

既存テストで未カバーまたは薄いパスを補強する:
- _score_alternatives: telemetry/degraded_subsystems 記録
- _score_alternatives: strategy success で score_map を反映
- decide: reason_core unavailable → natural_error 記録
- decide: reason_core.generate_reason 例外 → natural_error
- decide: reflection_template 成功パス (high stakes + non-fast)
- decide: reflection_template スキップ (fast_mode / low stakes)
- decide: reflection_template 例外 → reflection_template_error
- decide: legacy_skip_reasons 全フラグ型
- decide: degraded_subsystems ソート＋重複排除
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from veritas_os.core import kernel


# ===========================================================
# helper: _patch_minimal_decide_dependencies と同等だが衝突回避
# ===========================================================

class _DummyMEM:
    def put(self, *a: Any, **kw: Any) -> None:
        return None


def _patch_deps(monkeypatch, *, stub_scoring: bool = True) -> None:
    """kernel.decide を deterministic に走らせるためのパッチ群。"""
    monkeypatch.setattr(
        kernel.world_model, "inject_state_into_context",
        lambda context, user_id: dict(context),
    )
    monkeypatch.setattr(
        kernel.mem_core, "summarize_for_planner",
        lambda user_id, query, limit: "summary",
    )
    monkeypatch.setattr(kernel.adapt, "load_persona", lambda: {"bias_weights": {}})
    monkeypatch.setattr(kernel.adapt, "clean_bias_weights", lambda w: {})
    monkeypatch.setattr(kernel.adapt, "save_persona", lambda p: None)
    monkeypatch.setattr(
        kernel.planner_core, "plan_for_veritas_agi",
        lambda context, query: {
            "steps": [{"id": "s1", "title": "Step1", "detail": "D"}],
        },
    )
    if stub_scoring:
        monkeypatch.setattr(kernel, "_score_alternatives", lambda *a, **kw: False)
    monkeypatch.setattr(
        kernel.fuji_core, "evaluate",
        lambda *a, **kw: {
            "status": "allow",
            "decision_status": "allow",
            "risk": 0.1,
            "modifications": [],
        },
    )
    monkeypatch.setattr(kernel.mem_core, "get_evidence_for_decision", lambda *a, **kw: [])
    monkeypatch.setattr(kernel.mem_core, "MEM", _DummyMEM())
    monkeypatch.setattr(kernel.world_model, "update_from_decision", lambda **kw: None)


# ===========================================================
# anyio: asyncio 固定
# ===========================================================

@pytest.fixture
def anyio_backend():
    return "asyncio"


# ===========================================================
# A-1) _score_alternatives — telemetry/degraded 記録
# ===========================================================

class TestScoreAlternativesTelemetry:
    """_score_alternatives の戦略スコアリング成功・失敗時のテレメトリ反映。"""

    def test_strategy_failure_records_degraded_subsystems(self, monkeypatch):
        """strategy_core.score_options が TypeError を投げたとき、
        telemetry["degraded_subsystems"] と metrics に記録される。"""
        mock_sc = MagicMock()
        mock_sc.score_options.side_effect = TypeError("boom")
        monkeypatch.setattr(kernel, "strategy_core", mock_sc)

        telemetry: Dict[str, Any] = {}
        result = kernel._score_alternatives(
            intent="plan",
            q="test",
            alts=[{"id": "a1", "title": "T", "description": "", "score": 1.0}],
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
            ctx={},
            telemetry=telemetry,
        )
        assert result is False
        assert "strategy_scoring" in telemetry.get("degraded_subsystems", [])
        assert telemetry.get("metrics", {}).get("strategy_scoring_degraded") is True

    def test_strategy_failure_with_none_telemetry(self, monkeypatch):
        """telemetry=None のとき例外にならず False を返す。"""
        mock_sc = MagicMock()
        mock_sc.score_options.side_effect = RuntimeError("fail")
        monkeypatch.setattr(kernel, "strategy_core", mock_sc)

        result = kernel._score_alternatives(
            intent="plan",
            q="test",
            alts=[{"id": "a1", "title": "T", "description": "", "score": 1.0}],
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
            ctx={},
            telemetry=None,
        )
        assert result is False

    def test_strategy_success_updates_score_map(self, monkeypatch):
        """strategy_core.score_options が正常に dict リストを返したとき、
        alts の score が更新され True を返す。"""
        mock_sc = MagicMock()
        mock_sc.score_options.return_value = [
            {"id": "a1", "score": 0.99},
            {"id": "a2", "fusion_score": 0.77},
        ]
        monkeypatch.setattr(kernel, "strategy_core", mock_sc)

        alts = [
            {"id": "a1", "title": "T1", "description": "", "score": 0.1},
            {"id": "a2", "title": "T2", "description": "", "score": 0.1},
        ]
        result = kernel._score_alternatives(
            intent="plan",
            q="test",
            alts=alts,
            telos_score=0.5,
            stakes=0.5,
            persona_bias={},
            ctx={},
            telemetry={},
        )
        assert result is True
        assert alts[0]["score"] == round(0.99, 4)
        assert alts[1]["score"] == round(0.77, 4)

    def test_strategy_success_with_dataclass_objects(self, monkeypatch):
        """strategy_core.score_options がオブジェクト（dataclass）を返しても動作する。"""

        class _FakeOptionScore:
            def __init__(self, oid: str, sc: float):
                self.option_id = oid
                self.fusion_score = sc

        mock_sc = MagicMock()
        mock_sc.score_options.return_value = [
            _FakeOptionScore("a1", 0.88),
        ]
        monkeypatch.setattr(kernel, "strategy_core", mock_sc)

        alts = [
            {"id": "a1", "title": "T1", "description": "", "score": 0.1},
        ]
        result = kernel._score_alternatives(
            intent="plan",
            q="test",
            alts=alts,
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
            ctx={},
            telemetry={},
        )
        assert result is True
        assert alts[0]["score"] == round(0.88, 4)

    def test_no_strategy_core_returns_false(self, monkeypatch):
        """strategy_core が None のとき False を返す。"""
        monkeypatch.setattr(kernel, "strategy_core", None)

        result = kernel._score_alternatives(
            intent="plan",
            q="test",
            alts=[{"id": "a1", "title": "T", "description": "", "score": 1.0}],
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
            ctx={},
            telemetry={},
        )
        assert result is False


# ===========================================================
# A-2) decide — reason_core unavailable / 例外
# ===========================================================

class TestDecideReasonCore:
    """decide の reason_core 関連パスを検証。"""

    def test_reason_core_unavailable_records_error(self, monkeypatch):
        """reason_core が None → affect.natural_error に記録される。"""
        _patch_deps(monkeypatch)
        monkeypatch.setattr(kernel, "reason_core", None)

        ctx: Dict[str, Any] = {
            "user_id": "u-r1",
            "fast": True,
            "_episode_saved_by_pipeline": True,
        }
        result = asyncio.run(kernel.decide(ctx, "query", alternatives=None))

        affect = result["extras"].get("affect", {})
        assert "natural_error" in affect
        assert "not available" in affect["natural_error"]

    def test_reason_core_generate_reason_exception(self, monkeypatch):
        """reason_core.generate_reason が例外 → affect.natural_error に repr が入る。"""
        _patch_deps(monkeypatch)

        mock_rc = MagicMock()
        mock_rc.generate_reason.side_effect = RuntimeError("llm down")
        mock_rc.generate_reflection_template = MagicMock(return_value=None)
        monkeypatch.setattr(kernel, "reason_core", mock_rc)

        ctx: Dict[str, Any] = {
            "user_id": "u-r2",
            "fast": True,
            "_episode_saved_by_pipeline": True,
        }
        result = asyncio.run(kernel.decide(ctx, "query", alternatives=None))

        affect = result["extras"].get("affect", {})
        assert "natural_error" in affect
        assert "llm down" in affect["natural_error"]


# ===========================================================
# A-3) decide — reflection template paths
# ===========================================================

class TestDecideReflectionTemplate:
    """decide の reflection_template 生成分岐を検証。"""

    def test_reflection_template_generated_on_high_stakes(self, monkeypatch):
        """stakes >= 0.7 かつ非 fast_mode → reflection_template が extras に入る。"""
        _patch_deps(monkeypatch)

        mock_rc = MagicMock()
        mock_rc.generate_reason.return_value = "reason text"
        mock_rc.generate_reflection_template.return_value = "reflect me"
        monkeypatch.setattr(kernel, "reason_core", mock_rc)

        # debate_core は例外で fallback させる
        monkeypatch.setattr(
            kernel.debate_core, "run_debate",
            MagicMock(side_effect=RuntimeError("skip")),
        )

        ctx: Dict[str, Any] = {
            "user_id": "u-rt1",
            "stakes": 0.8,  # >= 0.7
            "_episode_saved_by_pipeline": True,
        }
        result = asyncio.run(kernel.decide(ctx, "高リスクな判断", alternatives=[
            {"id": "a1", "title": "Option A", "description": "desc", "score": 1.0},
        ]))

        affect = result["extras"].get("affect", {})
        assert affect.get("reflection_template") == "reflect me"

    def test_reflection_template_skipped_in_fast_mode(self, monkeypatch):
        """fast_mode → reflection_template は生成されない。"""
        _patch_deps(monkeypatch)

        mock_rc = MagicMock()
        mock_rc.generate_reason.return_value = "reason text"
        mock_rc.generate_reflection_template.return_value = "should not appear"
        monkeypatch.setattr(kernel, "reason_core", mock_rc)

        ctx: Dict[str, Any] = {
            "user_id": "u-rt2",
            "fast": True,
            "stakes": 0.9,
            "_episode_saved_by_pipeline": True,
        }
        result = asyncio.run(kernel.decide(ctx, "query", alternatives=None))

        affect = result["extras"].get("affect", {})
        assert "reflection_template" not in affect

    def test_reflection_template_skipped_low_risk_low_stakes(self, monkeypatch):
        """stakes < 0.7 かつ risk < 0.5 → reflection_template は生成されない。"""
        _patch_deps(monkeypatch)

        mock_rc = MagicMock()
        mock_rc.generate_reason.return_value = "reason text"
        mock_rc.generate_reflection_template.return_value = "should not appear"
        monkeypatch.setattr(kernel, "reason_core", mock_rc)

        monkeypatch.setattr(
            kernel.debate_core, "run_debate",
            MagicMock(side_effect=RuntimeError("skip")),
        )

        # risk 0.1 (from fuji stub), stakes 0.3 < 0.7
        ctx: Dict[str, Any] = {
            "user_id": "u-rt3",
            "stakes": 0.3,
            "_episode_saved_by_pipeline": True,
        }
        result = asyncio.run(kernel.decide(ctx, "query", alternatives=[
            {"id": "a1", "title": "O", "description": "d", "score": 1.0},
        ]))

        affect = result["extras"].get("affect", {})
        assert "reflection_template" not in affect

    def test_reflection_template_exception_recorded(self, monkeypatch):
        """generate_reflection_template 例外 → reflection_template_error が記録される。"""
        _patch_deps(monkeypatch)

        mock_rc = MagicMock()
        mock_rc.generate_reason.return_value = "ok"
        mock_rc.generate_reflection_template.side_effect = TypeError("boom")
        monkeypatch.setattr(kernel, "reason_core", mock_rc)

        monkeypatch.setattr(
            kernel.debate_core, "run_debate",
            MagicMock(side_effect=RuntimeError("skip")),
        )

        # high risk from fuji
        monkeypatch.setattr(
            kernel.fuji_core, "evaluate",
            lambda *a, **kw: {
                "status": "allow",
                "decision_status": "allow",
                "risk": 0.9,
                "modifications": [],
            },
        )

        ctx: Dict[str, Any] = {
            "user_id": "u-rt4",
            "stakes": 0.8,
            "_episode_saved_by_pipeline": True,
        }
        result = asyncio.run(kernel.decide(ctx, "query", alternatives=[
            {"id": "a1", "title": "O", "description": "d", "score": 1.0},
        ]))

        affect = result["extras"].get("affect", {})
        assert "reflection_template_error" in affect
        assert "boom" in affect["reflection_template_error"]


# ===========================================================
# A-4) decide — legacy_skip_reasons 全フラグ
# ===========================================================

class TestDecideLegacySkipReasons:
    """decide の legacy_flag_map 全4種 + env_tools パイプラインパスを検証。"""

    def test_all_pipeline_flags_mapped(self, monkeypatch):
        """全パイプラインフラグが _skip_reasons に反映される。"""
        _patch_deps(monkeypatch)

        ctx: Dict[str, Any] = {
            "user_id": "u-ls1",
            "fast": True,
            "_world_state_injected": True,
            "_episode_saved_by_pipeline": True,
            "_world_state_updated_by_pipeline": True,
            "_daily_plans_generated_by_pipeline": True,
            "_pipeline_env_tools": {"web_search": "cached"},
        }
        result = asyncio.run(kernel.decide(ctx, "query", alternatives=None))

        skip = result["extras"].get("_skip_reasons", {})
        assert skip.get("world_model_inject") == "already_injected_by_pipeline"
        assert skip.get("episode_save") == "already_saved_by_pipeline"
        assert skip.get("world_state_update") == "already_done_by_pipeline"
        assert skip.get("daily_plans") == "already_generated_by_pipeline"
        assert skip.get("env_tools") == "provided_by_pipeline"

    def test_env_tools_fast_mode_fallback(self, monkeypatch):
        """_pipeline_env_tools が無いとき fast_mode → env_tools = 'fast_mode'。"""
        _patch_deps(monkeypatch)

        ctx: Dict[str, Any] = {
            "user_id": "u-ls2",
            "fast": True,
            "_episode_saved_by_pipeline": True,
        }
        result = asyncio.run(kernel.decide(ctx, "query", alternatives=None))

        skip = result["extras"].get("_skip_reasons", {})
        assert skip.get("env_tools") == "fast_mode"


# ===========================================================
# A-5) decide — degraded_subsystems ソート・重複排除
# ===========================================================

class TestDecideDegradedSubsystems:
    """degraded_subsystems が sorted(set()) でまとめられることを検証。"""

    def test_degraded_subsystems_sorted_deduped(self, monkeypatch):
        """複数回 append された同一サブシステムが dedup＋sort される。"""
        _patch_deps(monkeypatch, stub_scoring=False)

        # strategy_core scoring を失敗させて degraded_subsystems に追加
        mock_sc = MagicMock()
        mock_sc.score_options.side_effect = TypeError("boom")
        monkeypatch.setattr(kernel, "strategy_core", mock_sc)

        ctx: Dict[str, Any] = {
            "user_id": "u-ds1",
            "fast": True,
            "_episode_saved_by_pipeline": True,
        }
        # no alternatives → planner fallback = "planner_fallback" added to degraded
        result = asyncio.run(kernel.decide(ctx, "query", alternatives=[]))

        ds = result["extras"].get("degraded_subsystems", [])
        # planner_fallback and strategy_scoring should both be present
        assert "planner_fallback" in ds
        assert "strategy_scoring" in ds
        # verify sorted
        assert ds == sorted(ds)
        # verify no duplicates
        assert len(ds) == len(set(ds))


# ===========================================================
# A-6) decide — fuji exception → deny fallback
# ===========================================================

class TestDecideFujiExceptionFallback:
    """fuji_core.evaluate 例外 → deny を返しつつ fuji_error を記録。"""

    def test_fuji_exception_produces_deny(self, monkeypatch):
        _patch_deps(monkeypatch)
        monkeypatch.setattr(
            kernel.fuji_core, "evaluate",
            MagicMock(side_effect=RuntimeError("fuji crashed")),
        )

        ctx: Dict[str, Any] = {
            "user_id": "u-fe1",
            "fast": True,
            "_episode_saved_by_pipeline": True,
        }
        result = asyncio.run(kernel.decide(ctx, "query", alternatives=None))

        assert result["decision_status"] == "deny"
        assert result["fuji"]["status"] == "deny"
        assert result["fuji"]["risk"] == 1.0
        assert "fuji_error" in result["extras"]
        assert "fuji crashed" in result["extras"]["fuji_error"]["detail"]
