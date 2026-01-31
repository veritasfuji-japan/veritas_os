# veritas_os/tests/test_kernel_stages.py
# -*- coding: utf-8 -*-
"""
kernel_stages モジュールのユニットテスト

各ステージ関数の詳細なテスト
"""
import pytest
import uuid
from unittest.mock import patch, MagicMock
from typing import Dict, Any, List


# =============================================================================
# Test: prepare_context
# =============================================================================

class TestPrepareContext:
    """prepare_context 関数のテスト"""

    def test_sets_default_user_id(self):
        """デフォルトの user_id が設定されるか"""
        from veritas_os.core.kernel_stages import prepare_context

        ctx = prepare_context({}, "query")
        assert ctx["user_id"] == "cli"

    def test_preserves_existing_user_id(self):
        """既存の user_id が保持されるか"""
        from veritas_os.core.kernel_stages import prepare_context

        ctx = prepare_context({"user_id": "custom_user"}, "query")
        assert ctx["user_id"] == "custom_user"

    def test_generates_request_id(self):
        """request_id が生成されるか"""
        from veritas_os.core.kernel_stages import prepare_context

        ctx = prepare_context({}, "query")
        assert "request_id" in ctx
        assert len(ctx["request_id"]) > 0

    def test_sets_query(self):
        """query が正しく設定されるか"""
        from veritas_os.core.kernel_stages import prepare_context

        ctx = prepare_context({}, "my query")
        assert ctx["query"] == "my query"

    def test_sets_default_stakes(self):
        """デフォルトの stakes が設定されるか"""
        from veritas_os.core.kernel_stages import prepare_context

        ctx = prepare_context({}, "query")
        assert ctx["stakes"] == 0.5

    def test_computes_telos_score(self):
        """_computed_telos_score が計算されるか"""
        from veritas_os.core.kernel_stages import prepare_context

        ctx = prepare_context({}, "query")
        assert "_computed_telos_score" in ctx
        assert isinstance(ctx["_computed_telos_score"], float)

    def test_computes_telos_score_with_custom_weights(self):
        """カスタム weights で telos_score が計算されるか"""
        from veritas_os.core.kernel_stages import prepare_context

        ctx = prepare_context({
            "telos_weights": {
                "W_Transcendence": 0.8,
                "W_Struggle": 0.2,
            }
        }, "query")

        expected = round(0.5 * 0.8 + 0.5 * 0.2, 3)
        assert ctx["_computed_telos_score"] == expected


# =============================================================================
# Test: collect_memory_evidence
# =============================================================================

class TestCollectMemoryEvidence:
    """collect_memory_evidence 関数のテスト"""

    def test_fast_mode_skips_collection(self):
        """fast_mode で収集がスキップされるか"""
        from veritas_os.core.kernel_stages import collect_memory_evidence

        result = collect_memory_evidence(
            user_id="test",
            query="query",
            context={},
            fast_mode=True,
        )

        assert result["source"] == "skipped_fast_mode"
        assert result["evidence"] == []
        assert result["evidence_count"] == 0

    def test_uses_pipeline_provided_evidence(self):
        """パイプライン提供のエビデンスが使用されるか"""
        from veritas_os.core.kernel_stages import collect_memory_evidence

        provided_evidence = [
            {"source": "test", "text": "evidence 1", "score": 0.9},
            {"source": "test", "text": "evidence 2", "score": 0.8},
        ]

        result = collect_memory_evidence(
            user_id="test",
            query="query",
            context={"_pipeline_evidence": provided_evidence},
            fast_mode=False,
        )

        assert result["source"] == "pipeline_provided"
        assert result["evidence"] == provided_evidence
        assert result["evidence_count"] == 2


# =============================================================================
# Test: run_world_simulation
# =============================================================================

class TestRunWorldSimulation:
    """run_world_simulation 関数のテスト"""

    def test_fast_mode_skips_simulation(self):
        """fast_mode でシミュレーションがスキップされるか"""
        from veritas_os.core.kernel_stages import run_world_simulation

        result = run_world_simulation(
            user_id="test",
            query="query",
            context={},
            fast_mode=True,
        )

        assert result["source"] == "skipped_fast_mode"
        assert result["simulation"] is None

    def test_uses_pipeline_provided_simulation(self):
        """パイプライン提供のシミュレーション結果が使用されるか"""
        from veritas_os.core.kernel_stages import run_world_simulation

        sim_result = {"state": "test_state"}

        result = run_world_simulation(
            user_id="test",
            query="query",
            context={
                "_world_sim_done": True,
                "_world_sim_result": sim_result,
            },
            fast_mode=False,
        )

        assert result["source"] == "pipeline_provided"
        assert result["simulation"] == sim_result


# =============================================================================
# Test: run_environment_tools
# =============================================================================

class TestRunEnvironmentTools:
    """run_environment_tools 関数のテスト"""

    def test_fast_mode_skips_tools(self):
        """fast_mode でツールがスキップされるか"""
        from veritas_os.core.kernel_stages import run_environment_tools

        result = run_environment_tools(
            query="query",
            context={},
            fast_mode=True,
        )

        assert "skipped" in result
        assert result["skipped"]["reason"] == "fast_mode"

    def test_uses_pipeline_provided_tools(self):
        """パイプライン提供のツール結果が使用されるか"""
        from veritas_os.core.kernel_stages import run_environment_tools

        provided_tools = {"web_search": {"results": []}}

        result = run_environment_tools(
            query="query",
            context={"_pipeline_env_tools": provided_tools},
            fast_mode=False,
        )

        assert result == provided_tools


# =============================================================================
# Test: score_alternatives (詳細)
# =============================================================================

class TestScoreAlternativesDetailed:
    """score_alternatives 関数の詳細テスト"""

    def test_weather_intent_bonus(self):
        """weather intent のボーナスが適用されるか"""
        from veritas_os.core.kernel_stages import score_alternatives
        from veritas_os.core.config import scoring_cfg

        alts = [
            {"id": "1", "title": "天気予報を確認", "score": 1.0},
            {"id": "2", "title": "別のオプション", "score": 1.0},
        ]

        score_alternatives(
            intent="weather",
            query="天気",
            alternatives=alts,
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
        )

        weather_score = next(a["score"] for a in alts if a["id"] == "1")
        other_score = next(a["score"] for a in alts if a["id"] == "2")

        # weather オプションがより高いスコアを持つ
        assert weather_score > other_score

    def test_health_intent_bonus(self):
        """health intent のボーナスが適用されるか"""
        from veritas_os.core.kernel_stages import score_alternatives

        alts = [
            {"id": "1", "title": "休息を取る", "score": 1.0},
            {"id": "2", "title": "作業を続ける", "score": 1.0},
        ]

        score_alternatives(
            intent="health",
            query="疲れた",
            alternatives=alts,
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
        )

        rest_score = next(a["score"] for a in alts if a["id"] == "1")
        work_score = next(a["score"] for a in alts if a["id"] == "2")

        assert rest_score > work_score

    def test_learn_intent_bonus(self):
        """learn intent のボーナスが適用されるか"""
        from veritas_os.core.kernel_stages import score_alternatives

        alts = [
            {"id": "1", "title": "一次情報を確認", "score": 1.0},
            {"id": "2", "title": "推測する", "score": 1.0},
        ]

        score_alternatives(
            intent="learn",
            query="学習",
            alternatives=alts,
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
        )

        primary_score = next(a["score"] for a in alts if a["id"] == "1")
        guess_score = next(a["score"] for a in alts if a["id"] == "2")

        assert primary_score > guess_score

    def test_plan_intent_bonus(self):
        """plan intent のボーナスが適用されるか"""
        from veritas_os.core.kernel_stages import score_alternatives

        alts = [
            {"id": "1", "title": "最小限の変更でテスト", "score": 1.0},
            {"id": "2", "title": "完全に新規実装", "score": 1.0},
        ]

        score_alternatives(
            intent="plan",
            query="計画",
            alternatives=alts,
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
        )

        minimal_score = next(a["score"] for a in alts if a["id"] == "1")
        large_score = next(a["score"] for a in alts if a["id"] == "2")

        # plan intent では「最小」「テスト」などのキーワードにボーナス
        assert minimal_score > large_score

    def test_query_match_umbrella_bonus(self):
        """雨/傘のクエリマッチボーナスが適用されるか"""
        from veritas_os.core.kernel_stages import score_alternatives

        alts = [
            {"id": "1", "title": "傘を持っていく", "score": 1.0},
            {"id": "2", "title": "そのまま出かける", "score": 1.0},
        ]

        score_alternatives(
            intent="weather",
            query="今日は雨が降りそう",
            alternatives=alts,
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
        )

        umbrella_score = next(a["score"] for a in alts if a["id"] == "1")
        no_umbrella_score = next(a["score"] for a in alts if a["id"] == "2")

        assert umbrella_score > no_umbrella_score

    def test_high_stakes_rest_bonus(self):
        """高 stakes 時の休息ボーナスが適用されるか"""
        from veritas_os.core.kernel_stages import score_alternatives
        from veritas_os.core.config import scoring_cfg

        alts = [
            {"id": "1", "title": "休息を取る", "score": 1.0},
            {"id": "2", "title": "急いで進める", "score": 1.0},
        ]

        # High stakes (>= 0.7)
        score_alternatives(
            intent="plan",
            query="重要な判断",
            alternatives=alts,
            telos_score=0.5,
            stakes=0.8,
            persona_bias=None,
        )

        rest_score = next(a["score"] for a in alts if a["id"] == "1")
        rush_score = next(a["score"] for a in alts if a["id"] == "2")

        assert rest_score > rush_score

    def test_persona_bias_boost(self):
        """persona bias がスコアに反映されるか（@id: 形式を使用）"""
        from veritas_os.core.kernel_stages import score_alternatives

        # @id: 形式を使用してfuzzy matchingを避ける
        alts = [
            {"id": "preferred_123", "title": "First Choice", "score": 1.0},
            {"id": "other_456", "title": "Second Choice", "score": 1.0},
        ]

        score_alternatives(
            intent="plan",
            query="test",
            alternatives=alts,
            telos_score=0.5,
            stakes=0.5,
            # @id: 形式でIDに直接マッチさせる
            persona_bias={"@id:preferred_123": 5.0},
        )

        preferred_score = next(a["score"] for a in alts if a["id"] == "preferred_123")
        other_score = next(a["score"] for a in alts if a["id"] == "other_456")

        # persona_bias_multiplier (0.3) * 5.0 = 1.5 の乗数ブースト
        assert preferred_score > other_score

    def test_telos_scale_applied(self):
        """Telos スコアによるスケーリングが適用されるか"""
        from veritas_os.core.kernel_stages import score_alternatives

        alts_low = [{"id": "1", "title": "test", "score": 1.0}]
        alts_high = [{"id": "1", "title": "test", "score": 1.0}]

        score_alternatives(
            intent="plan",
            query="test",
            alternatives=alts_low,
            telos_score=0.0,  # low
            stakes=0.5,
            persona_bias=None,
        )

        score_alternatives(
            intent="plan",
            query="test",
            alternatives=alts_high,
            telos_score=1.0,  # high
            stakes=0.5,
            persona_bias=None,
        )

        # 高い telos_score はより高いスコアをもたらす
        assert alts_high[0]["score"] > alts_low[0]["score"]

    def test_score_raw_preserved(self):
        """元のスコアが score_raw に保存されるか"""
        from veritas_os.core.kernel_stages import score_alternatives

        alts = [{"id": "1", "title": "test", "score": 0.75}]

        score_alternatives(
            intent="plan",
            query="test",
            alternatives=alts,
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
        )

        assert "score_raw" in alts[0]
        assert alts[0]["score_raw"] == 0.75


# =============================================================================
# Test: run_debate_stage
# =============================================================================

class TestRunDebateStage:
    """run_debate_stage 関数のテスト"""

    def test_fast_mode_selects_highest_score(self):
        """fast_mode で最高スコアが選択されるか"""
        from veritas_os.core.kernel_stages import run_debate_stage

        alts = [
            {"id": "1", "title": "Low", "score": 0.3},
            {"id": "2", "title": "High", "score": 0.9},
            {"id": "3", "title": "Medium", "score": 0.6},
        ]

        result = run_debate_stage(
            query="test",
            alternatives=alts,
            context={},
            fast_mode=True,
        )

        assert result["chosen"]["id"] == "2"
        assert result["source"] == "fast_mode"

    def test_fast_mode_creates_default_for_empty_alts(self):
        """fast_mode で空のリストにデフォルトが生成されるか"""
        from veritas_os.core.kernel_stages import run_debate_stage

        result = run_debate_stage(
            query="test",
            alternatives=[],
            context={},
            fast_mode=True,
        )

        assert result["chosen"] is not None
        assert "title" in result["chosen"]

    def test_debate_logs_generated(self):
        """debate_logs が生成されるか"""
        from veritas_os.core.kernel_stages import run_debate_stage

        alts = [{"id": "1", "title": "Test", "score": 1.0}]

        result = run_debate_stage(
            query="test",
            alternatives=alts,
            context={},
            fast_mode=True,
        )

        assert len(result["debate_logs"]) > 0
        assert "summary" in result["debate_logs"][0]


# =============================================================================
# Test: run_fuji_gate
# =============================================================================

class TestRunFujiGate:
    """run_fuji_gate 関数のテスト"""

    def test_returns_valid_structure(self):
        """有効な構造が返されるか"""
        from veritas_os.core.kernel_stages import run_fuji_gate

        result = run_fuji_gate(
            query="safe query",
            context={"user_id": "test", "stakes": 0.5},
            evidence=[],
            alternatives=[],
        )

        assert "status" in result
        assert "risk" in result
        assert "violations" in result

    def test_handles_fuji_error(self):
        """FUJI エラー時にフォールバックが動作するか"""
        from veritas_os.core.kernel_stages import run_fuji_gate

        # fuji モジュールを直接パッチ
        with patch("veritas_os.core.fuji.evaluate") as mock_evaluate:
            mock_evaluate.side_effect = Exception("FUJI error")

            # エラーでもクラッシュせずに結果を返す
            result = run_fuji_gate(
                query="test",
                context={"user_id": "test"},
                evidence=[],
                alternatives=[],
            )

            # エラー時は allow で低リスクを返す
            assert result["status"] == "allow"
            assert result["risk"] == 0.05


# =============================================================================
# Test: update_persona_and_goals
# =============================================================================

class TestUpdatePersonaAndGoals:
    """update_persona_and_goals 関数のテスト"""

    def test_fast_mode_skips_update(self):
        """fast_mode で更新がスキップされるか"""
        from veritas_os.core.kernel_stages import update_persona_and_goals

        result = update_persona_and_goals(
            chosen={"id": "1", "title": "test"},
            context={},
            fuji_result={"risk": 0.1},
            telos_score=0.5,
            fast_mode=True,
        )

        assert result.get("skipped") is True

    def test_pipeline_provided_skips_update(self):
        """パイプラインで既に処理済みの場合スキップされるか"""
        from veritas_os.core.kernel_stages import update_persona_and_goals

        result = update_persona_and_goals(
            chosen={"id": "1", "title": "test"},
            context={"_agi_goals_adjusted_by_pipeline": True},
            fuji_result={"risk": 0.1},
            telos_score=0.5,
            fast_mode=False,
        )

        assert result.get("skipped") is True


# =============================================================================
# Test: save_episode_to_memory
# =============================================================================

class TestSaveEpisodeToMemory:
    """save_episode_to_memory 関数のテスト"""

    def test_pipeline_provided_returns_true(self):
        """パイプラインで既に保存済みの場合 True を返すか"""
        from veritas_os.core.kernel_stages import save_episode_to_memory

        result = save_episode_to_memory(
            query="test",
            chosen={"id": "1", "title": "test"},
            context={"_episode_saved_by_pipeline": True},
            intent="test",
            mode="fast",
            telos_score=0.5,
        )

        assert result is True


# =============================================================================
# Test: Utility functions
# =============================================================================

class TestUtilityFunctions:
    """ユーティリティ関数のテスト"""

    def test_mk_option_generates_valid_structure(self):
        """_mk_option が有効な構造を生成するか"""
        from veritas_os.core.kernel_stages import _mk_option

        opt = _mk_option("Test Title", "Test Description")

        assert "id" in opt
        assert opt["title"] == "Test Title"
        assert opt["description"] == "Test Description"
        assert opt["score"] == 1.0

    def test_mk_option_with_custom_id(self):
        """_mk_option でカスタム ID が使用できるか"""
        from veritas_os.core.kernel_stages import _mk_option

        opt = _mk_option("Test", _id="custom_id")

        assert opt["id"] == "custom_id"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
