# veritas_os/tests/test_integration_pipeline.py
# -*- coding: utf-8 -*-
"""
統合テスト: 決定パイプライン全体のエンドツーエンドテスト

優先度: 高
- kernel.decide() の全ステージが正しく連携するか
- 設定値が正しく適用されるか
- エラー時のフォールバックが機能するか
"""
import pytest
import uuid
from unittest.mock import patch, MagicMock
from typing import Dict, Any, List


# =============================================================================
# Test: Config Module
# =============================================================================

class TestConfigModule:
    """設定モジュールのテスト"""

    def test_scoring_config_defaults(self):
        """ScoringConfig のデフォルト値が正しく設定されているか"""
        from veritas_os.core.config import ScoringConfig

        cfg = ScoringConfig()

        assert cfg.intent_weather_bonus == 0.4
        assert cfg.intent_health_bonus == 0.4
        assert cfg.intent_learn_bonus == 0.35
        assert cfg.intent_plan_bonus == 0.3
        assert cfg.query_match_bonus == 0.2
        assert cfg.high_stakes_threshold == 0.7
        assert cfg.high_stakes_bonus == 0.2
        assert cfg.persona_bias_multiplier == 0.3
        assert cfg.telos_scale_base == 0.9
        assert cfg.telos_scale_factor == 0.2

    def test_fuji_config_defaults(self):
        """FujiConfig のデフォルト値が正しく設定されているか"""
        from veritas_os.core.config import FujiConfig

        cfg = FujiConfig()

        assert cfg.default_min_evidence == 1
        assert cfg.max_uncertainty == 0.60
        assert cfg.low_evidence_risk_penalty == 0.10
        assert cfg.safety_head_error_base_risk == 0.30
        assert cfg.telos_risk_scale_factor == 0.10
        assert cfg.pii_safe_risk_cap == 0.40
        assert cfg.name_like_only_risk_cap == 0.20

    def test_pipeline_config_defaults(self):
        """PipelineConfig のデフォルト値が正しく設定されているか"""
        from veritas_os.core.config import PipelineConfig

        cfg = PipelineConfig()

        assert cfg.memory_search_limit == 8
        assert cfg.evidence_top_k == 5
        assert cfg.max_plan_steps == 10
        assert cfg.debate_timeout_seconds == 30
        assert cfg.persona_update_window == 50
        assert cfg.persona_bias_increment == 0.05

    def test_config_env_override(self):
        """環境変数による設定上書きが機能するか"""
        import os
        from veritas_os.core.config import _parse_float, _parse_int

        # _parse_float
        assert _parse_float("NON_EXISTENT_KEY", 1.5) == 1.5

        # _parse_int
        assert _parse_int("NON_EXISTENT_KEY", 10) == 10


# =============================================================================
# Test: Kernel Stages Module
# =============================================================================

class TestKernelStages:
    """kernel_stages モジュールのテスト"""

    def test_prepare_context_defaults(self):
        """prepare_context がデフォルト値を正しく設定するか"""
        from veritas_os.core.kernel_stages import prepare_context

        ctx = prepare_context({}, "test query")

        assert ctx["user_id"] == "cli"
        assert "request_id" in ctx
        assert ctx["query"] == "test query"
        assert ctx["stakes"] == 0.5
        assert ctx["mode"] == ""
        assert "_computed_telos_score" in ctx

    def test_prepare_context_preserves_values(self):
        """prepare_context が既存の値を保持するか"""
        from veritas_os.core.kernel_stages import prepare_context

        ctx = prepare_context(
            {"user_id": "test_user", "stakes": 0.8},
            "test query"
        )

        assert ctx["user_id"] == "test_user"
        assert ctx["stakes"] == 0.8

    def test_score_alternatives_intent_weather(self):
        """weather intent のスコアリングが正しく動作するか"""
        from veritas_os.core.kernel_stages import score_alternatives
        from veritas_os.core.config import scoring_cfg

        alternatives = [
            {"id": "1", "title": "天気予報を確認", "score": 1.0},
            {"id": "2", "title": "その他のオプション", "score": 1.0},
        ]

        score_alternatives(
            intent="weather",
            query="今日の天気は？",
            alternatives=alternatives,
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
        )

        # 天気関連のオプションがより高いスコアを持つはず
        weather_opt = next(a for a in alternatives if a["id"] == "1")
        other_opt = next(a for a in alternatives if a["id"] == "2")

        assert weather_opt["score"] > other_opt["score"]

    def test_score_alternatives_high_stakes(self):
        """高 stakes 時のスコアリングが正しく動作するか"""
        from veritas_os.core.kernel_stages import score_alternatives
        from veritas_os.core.config import scoring_cfg

        alternatives = [
            {"id": "1", "title": "休息を取る", "score": 1.0},
            {"id": "2", "title": "継続する", "score": 1.0},
        ]

        score_alternatives(
            intent="plan",
            query="疲れている",
            alternatives=alternatives,
            telos_score=0.5,
            stakes=0.8,  # high stakes
            persona_bias=None,
        )

        # 休息オプションがボーナスを得るはず
        rest_opt = next(a for a in alternatives if a["id"] == "1")
        continue_opt = next(a for a in alternatives if a["id"] == "2")

        assert rest_opt["score"] > continue_opt["score"]

    def test_score_alternatives_persona_bias(self):
        """persona bias が正しく適用されるか（@id: 形式を使用）"""
        from veritas_os.core.kernel_stages import score_alternatives

        # @id: 形式を使用してfuzzy matchingを避ける
        alternatives = [
            {"id": "preferred_abc", "title": "First Choice", "score": 1.0},
            {"id": "other_xyz", "title": "Second Choice", "score": 1.0},
        ]

        # 大きなバイアス値を使用して差が出るようにする
        score_alternatives(
            intent="plan",
            query="test",
            alternatives=alternatives,
            telos_score=0.5,
            stakes=0.5,
            # @id: 形式でIDに直接マッチさせる
            persona_bias={"@id:preferred_abc": 5.0},
        )

        preferred = next(a for a in alternatives if a["id"] == "preferred_abc")
        other = next(a for a in alternatives if a["id"] == "other_xyz")

        assert preferred["score"] > other["score"]

    def test_collect_memory_evidence_fast_mode(self):
        """fast_mode で memory 収集がスキップされるか"""
        from veritas_os.core.kernel_stages import collect_memory_evidence

        result = collect_memory_evidence(
            user_id="test",
            query="test query",
            context={},
            fast_mode=True,
        )

        assert result["source"] == "skipped_fast_mode"
        assert result["evidence"] == []

    def test_run_world_simulation_fast_mode(self):
        """fast_mode で world simulation がスキップされるか"""
        from veritas_os.core.kernel_stages import run_world_simulation

        result = run_world_simulation(
            user_id="test",
            query="test query",
            context={},
            fast_mode=True,
        )

        assert result["source"] == "skipped_fast_mode"
        assert result["simulation"] is None

    def test_run_debate_stage_fast_mode(self):
        """fast_mode で debate がスキップされ、最高スコアが選択されるか"""
        from veritas_os.core.kernel_stages import run_debate_stage

        alternatives = [
            {"id": "1", "title": "Low score", "score": 0.5},
            {"id": "2", "title": "High score", "score": 0.9},
        ]

        result = run_debate_stage(
            query="test",
            alternatives=alternatives,
            context={},
            fast_mode=True,
        )

        assert result["source"] == "fast_mode"
        assert result["chosen"]["id"] == "2"  # highest score

    def test_run_fuji_gate_returns_valid_structure(self):
        """run_fuji_gate が有効な構造を返すか"""
        from veritas_os.core.kernel_stages import run_fuji_gate

        result = run_fuji_gate(
            query="safe query",
            context={"user_id": "test", "stakes": 0.5},
            evidence=[],
            alternatives=[],
        )

        assert "status" in result
        assert "risk" in result
        assert isinstance(result["risk"], (int, float))


# =============================================================================
# Test: End-to-End Pipeline Integration
# =============================================================================

class TestEndToEndPipeline:
    """エンドツーエンドのパイプライン統合テスト"""

    @pytest.mark.asyncio
    async def test_kernel_decide_basic_flow(self):
        """kernel.decide() の基本フローが動作するか"""
        from veritas_os.core import kernel

        # LLM呼び出しをモック（正しいパスでパッチ）
        with patch("veritas_os.core.llm_client.chat") as mock_chat:
            mock_chat.return_value = {
                "text": "テスト応答",
                "content": "テスト応答",
            }

            # kernel.decide() は async 関数で alternatives 引数が必要
            result = await kernel.decide(
                context={
                    "user_id": "test_user",
                    "mode": "fast",
                },
                query="今日の天気は？",
                alternatives=[
                    {"id": "1", "title": "天気予報を確認", "score": 1.0},
                ],
            )

            assert result is not None
            assert "chosen" in result
            assert "fuji" in result

    @pytest.mark.asyncio
    async def test_kernel_decide_fast_mode(self):
        """fast mode で kernel.decide() が高速に完了するか"""
        from veritas_os.core import kernel

        with patch("veritas_os.core.llm_client.chat") as mock_chat:
            mock_chat.return_value = {"text": "response"}

            result = await kernel.decide(
                context={
                    "user_id": "test",
                    "mode": "fast",
                },
                query="simple question",
                alternatives=[
                    {"id": "1", "title": "Answer", "score": 1.0},
                ],
            )

            assert result is not None
            # fast mode ではメモリ/debate がスキップされる

    @pytest.mark.asyncio
    async def test_kernel_decide_with_evidence(self):
        """evidence 付きで kernel.decide() が動作するか"""
        from veritas_os.core import kernel

        with patch("veritas_os.core.llm_client.chat") as mock_chat:
            mock_chat.return_value = {"text": "response"}

            result = await kernel.decide(
                context={
                    "user_id": "test",
                    "_pipeline_evidence": [
                        {"source": "test", "text": "evidence text", "score": 0.8}
                    ],
                },
                query="research question",
                alternatives=[
                    {"id": "1", "title": "Research Result", "score": 1.0},
                ],
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_kernel_decide_handles_errors(self):
        """kernel.decide() がエラーを適切にハンドリングするか"""
        from veritas_os.core import kernel

        # LLM呼び出しがエラーになるケース
        with patch("veritas_os.core.llm_client.chat") as mock_chat:
            mock_chat.side_effect = Exception("LLM error")

            # エラーでもクラッシュせずに結果を返す（fast modeでLLM不要）
            result = await kernel.decide(
                context={"user_id": "test", "mode": "fast"},
                query="test query",
                alternatives=[
                    {"id": "1", "title": "Default", "score": 1.0},
                ],
            )

            assert result is not None


# =============================================================================
# Test: FUJI Gate Integration
# =============================================================================

class TestFujiGateIntegration:
    """FUJI Gate の統合テスト"""

    def test_fuji_evaluate_safe_query(self):
        """安全なクエリが allow されるか"""
        from veritas_os.core import fuji

        result = fuji.evaluate(
            "今日の天気を教えてください",
            context={"user_id": "test", "stakes": 0.5},
            evidence=[{"source": "test", "text": "天気情報", "score": 0.8}],
            alternatives=[],
        )

        assert result["status"] in ("allow", "allow_with_warning")
        assert result["risk"] < 0.5

    def test_fuji_evaluate_low_evidence_warning(self):
        """evidence 不足時に警告が出るか"""
        from veritas_os.core import fuji

        result = fuji.evaluate(
            "重要な決定をしてください",
            context={"user_id": "test", "stakes": 0.8},
            evidence=[],  # no evidence
            alternatives=[],
        )

        # low_evidence の場合、guidance に警告が含まれるはず
        guidance = result.get("guidance", "")
        # または reasons に low_evidence が含まれるはず
        reasons = result.get("reasons", [])

        has_low_evidence_warning = (
            "エビデンス" in guidance or
            any("low_evidence" in str(r) for r in reasons)
        )
        assert has_low_evidence_warning or result["risk"] > 0.0

    def test_fuji_config_values_applied(self):
        """FUJI Gate が設定値を正しく使用しているか"""
        from veritas_os.core import fuji
        from veritas_os.core.config import fuji_cfg

        # DEFAULT_MIN_EVIDENCE が config から取得されていることを確認
        assert fuji.DEFAULT_MIN_EVIDENCE == fuji_cfg.default_min_evidence
        assert fuji.MAX_UNCERTAINTY == fuji_cfg.max_uncertainty


# =============================================================================
# Test: Memory Integration
# =============================================================================

class TestMemoryIntegration:
    """Memory システムの統合テスト"""

    def test_memory_search_returns_valid_structure(self):
        """memory.search() が有効な構造を返すか"""
        from veritas_os.core import memory

        results = memory.search(
            query="test query",
            k=5,
        )

        assert isinstance(results, list)
        for item in results:
            assert isinstance(item, dict)

    def test_memory_summarize_for_planner(self):
        """memory.summarize_for_planner() が動作するか"""
        from veritas_os.core import memory

        summary = memory.summarize_for_planner(
            user_id="test_user",
            query="test query",
            limit=5,
        )

        assert isinstance(summary, str)


# =============================================================================
# Test: Configuration Isolation
# =============================================================================

class TestConfigurationIsolation:
    """設定が各モジュール間で正しく共有されているか"""

    def test_scoring_config_shared(self):
        """scoring_cfg が正しくインポートされるか"""
        from veritas_os.core.config import scoring_cfg
        from veritas_os.core.kernel_stages import score_alternatives

        # score_alternatives が scoring_cfg を使用していることを確認
        # (内部で使用されているため、直接テストは困難だが、エラーなく動作することを確認)
        alternatives = [{"id": "1", "title": "test", "score": 1.0}]
        score_alternatives(
            intent="test",
            query="test",
            alternatives=alternatives,
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
        )
        assert True  # エラーなく完了

    def test_fuji_config_shared(self):
        """fuji_cfg が fuji.py で正しく使用されているか"""
        from veritas_os.core.config import fuji_cfg
        from veritas_os.core import fuji

        # fuji.py の定数が config から取得されていることを確認
        assert fuji.DEFAULT_MIN_EVIDENCE == fuji_cfg.default_min_evidence


# =============================================================================
# Test: Error Resilience
# =============================================================================

class TestErrorResilience:
    """エラー耐性のテスト"""

    def test_kernel_stages_handle_missing_modules(self):
        """モジュールが欠けていてもクラッシュしないか"""
        from veritas_os.core.kernel_stages import (
            collect_memory_evidence,
            run_world_simulation,
        )

        # fast_mode でモジュール呼び出しをスキップ
        mem_result = collect_memory_evidence("test", "query", {}, fast_mode=True)
        assert mem_result["source"] == "skipped_fast_mode"

        world_result = run_world_simulation("test", "query", {}, fast_mode=True)
        assert world_result["source"] == "skipped_fast_mode"

    def test_score_alternatives_handles_empty_list(self):
        """空のリストでもクラッシュしないか"""
        from veritas_os.core.kernel_stages import score_alternatives

        # 空のリストを渡してもエラーにならない
        score_alternatives(
            intent="test",
            query="test",
            alternatives=[],
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
        )
        assert True  # エラーなく完了

    def test_score_alternatives_handles_malformed_data(self):
        """不正なデータでもクラッシュしないか"""
        from veritas_os.core.kernel_stages import score_alternatives

        # 不完全なデータ
        alternatives = [
            {"id": "1"},  # title, score なし
            {"title": "test"},  # id, score なし
            {},  # 空
        ]

        score_alternatives(
            intent="test",
            query="test",
            alternatives=alternatives,
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
        )
        assert True  # エラーなく完了


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
