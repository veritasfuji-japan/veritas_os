# veritas_os/tests/test_kernel_stages_coverage.py
# -*- coding: utf-8 -*-
"""
kernel_stages モジュールの追加カバレッジテスト

既存の test_kernel_stages.py でカバーされていないパスをテストする。
"""
import pytest
import uuid
from unittest.mock import patch, MagicMock, PropertyMock
from typing import Dict, Any


# =============================================================================
# Test: collect_memory_evidence – exception handler (lines 104-117)
# =============================================================================

class TestCollectMemoryEvidenceExceptionPaths:

    def test_memory_summarize_success(self):
        """memory import succeeds and summarize_for_planner returns a summary."""
        from veritas_os.core import kernel_stages

        with patch("veritas_os.core.memory.summarize_for_planner", return_value="summary text"):
            result = kernel_stages.collect_memory_evidence(
                user_id="u1", query="q", context={}, fast_mode=False,
            )

        assert result["source"] == "MemoryOS.summarize_for_planner"

    def test_memory_summarize_exception(self):
        """summarize_for_planner raises → source contains error string."""
        from veritas_os.core import kernel_stages

        with patch("veritas_os.core.memory.summarize_for_planner", side_effect=RuntimeError("db down")):
            result = kernel_stages.collect_memory_evidence(
                user_id="u1", query="q", context={}, fast_mode=False,
            )

        assert "error" in result["source"]
        assert result["memory_summary"] == ""


# =============================================================================
# Test: run_world_simulation – actual world module (lines 159-172)
# =============================================================================

class TestRunWorldSimulationActualModule:

    def test_world_simulate_success(self):
        """world.simulate succeeds → result populated."""
        from veritas_os.core import kernel_stages

        with patch("veritas_os.core.world.simulate", return_value={"outcome": "ok"}):
            result = kernel_stages.run_world_simulation(
                user_id="u1", query="q", context={}, fast_mode=False,
            )

        assert result["simulation"] == {"outcome": "ok"}
        assert result["source"] == "world.simulate()"

    def test_world_simulate_exception(self):
        """world.simulate raises → error source."""
        from veritas_os.core import kernel_stages

        with patch("veritas_os.core.world.simulate", side_effect=ConnectionError("timeout")):
            result = kernel_stages.run_world_simulation(
                user_id="u1", query="q", context={}, fast_mode=False,
            )

        assert "error" in result["source"]
        assert result["simulation"] is None


# =============================================================================
# Test: run_environment_tools – full execution (lines 205-228)
# =============================================================================

class TestRunEnvironmentToolsFull:

    def test_use_env_tools_flag_calls_both(self):
        """use_env_tools=True → web_search and github_search called."""
        from veritas_os.core import kernel_stages

        mock_call_tool = MagicMock(return_value={"ok": True, "results": ["r"]})

        with patch("veritas_os.tools.call_tool", mock_call_tool):
            result = kernel_stages.run_environment_tools(
                query="find repos",
                context={"use_env_tools": True},
                fast_mode=False,
            )

        assert "web_search" in result
        assert "github_search" in result
        assert result["web_search"]["ok"] is True

    def test_github_keyword_triggers_github_search(self):
        """Query containing 'github' triggers github_search only."""
        from veritas_os.core import kernel_stages

        mock_call_tool = MagicMock(return_value={"ok": True, "results": []})

        with patch("veritas_os.tools.call_tool", mock_call_tool):
            result = kernel_stages.run_environment_tools(
                query="search github repos",
                context={},
                fast_mode=False,
            )

        assert "github_search" in result
        assert "web_search" not in result

    def test_agi_keyword_triggers_web_search(self):
        """Query containing 'agi' triggers web_search."""
        from veritas_os.core import kernel_stages

        mock_call_tool = MagicMock(return_value={"ok": True, "results": []})

        with patch("veritas_os.tools.call_tool", mock_call_tool):
            result = kernel_stages.run_environment_tools(
                query="latest agi research",
                context={},
                fast_mode=False,
            )

        assert "web_search" in result

    def test_paper_keyword_triggers_web_search(self):
        """Query containing 'paper' triggers web_search."""
        from veritas_os.core import kernel_stages

        mock_call_tool = MagicMock(return_value={"ok": True, "results": []})

        with patch("veritas_os.tools.call_tool", mock_call_tool):
            result = kernel_stages.run_environment_tools(
                query="new paper on transformers",
                context={},
                fast_mode=False,
            )

        assert "web_search" in result

    def test_no_keyword_match_returns_empty(self):
        """Query with no matching keywords → empty result."""
        from veritas_os.core import kernel_stages

        mock_call_tool = MagicMock(return_value={"ok": True, "results": []})

        with patch("veritas_os.tools.call_tool", mock_call_tool):
            result = kernel_stages.run_environment_tools(
                query="hello world",
                context={},
                fast_mode=False,
            )

        assert "web_search" not in result
        assert "github_search" not in result

    def test_call_tool_import_exception(self):
        """If call_tool import fails → error key in result."""
        from veritas_os.core import kernel_stages

        with patch("veritas_os.tools.call_tool", side_effect=ImportError("no module")):
            result = kernel_stages.run_environment_tools(
                query="github test",
                context={},
                fast_mode=False,
            )

        # _run_tool_safe catches the error per-tool
        assert result["github_search"]["ok"] is False


# =============================================================================
# Test: _run_tool_safe (lines 231-245)
# =============================================================================

class TestRunToolSafe:

    def test_success_returns_dict_with_ok(self):
        """Successful call_tool returns dict → ok=True preserved."""
        from veritas_os.core.kernel_stages import _run_tool_safe

        fn = MagicMock(return_value={"data": 42})
        result = _run_tool_safe(fn, "web_search", query="q")

        assert result["ok"] is True
        assert result["data"] == 42
        assert "results" in result

    def test_non_dict_return_wrapped(self):
        """Non-dict return → wrapped in {'raw': ...}."""
        from veritas_os.core.kernel_stages import _run_tool_safe

        fn = MagicMock(return_value="plain string")
        result = _run_tool_safe(fn, "web_search")

        assert result["raw"] == "plain string"
        assert result["ok"] is True

    def test_exception_returns_error(self):
        """Exception in callable → ok=False with error message."""
        from veritas_os.core.kernel_stages import _run_tool_safe

        fn = MagicMock(side_effect=ValueError("bad value"))
        result = _run_tool_safe(fn, "web_search")

        assert result["ok"] is False
        assert "error" in result
        assert "bad value" in result["error"]


# =============================================================================
# Test: score_alternatives – value_core integration (lines 279-360)
# =============================================================================

class TestScoreAlternativesValueCore:

    @patch("veritas_os.core.value_core.compute_value_score", create=True, return_value=1.5)
    @patch("veritas_os.core.value_core.OptionScore", create=True, new_callable=MagicMock)
    def test_value_core_multiplier_applied(self, mock_os_cls, mock_compute):
        """When value_core is available, vscore multiplier is applied."""
        from veritas_os.core import kernel_stages

        alts_with = [{"id": "a", "title": "Test", "description": "d", "score": 1.0}]
        kernel_stages.score_alternatives(
            intent="plan", query="test", alternatives=alts_with,
            telos_score=0.5, stakes=0.5, persona_bias=None,
        )

        # compute_value_score was called
        assert mock_compute.called
        assert "score_raw" in alts_with[0]

    @patch("veritas_os.core.value_core.compute_value_score", create=True, side_effect=RuntimeError("boom"))
    @patch("veritas_os.core.value_core.OptionScore", create=True, new_callable=MagicMock)
    def test_value_core_exception_ignored(self, mock_os_cls, mock_compute):
        """If value_core.compute_value_score raises, score still set."""
        from veritas_os.core import kernel_stages

        alts = [{"id": "a", "title": "Test", "description": "d", "score": 1.0}]
        kernel_stages.score_alternatives(
            intent="plan", query="test", alternatives=alts,
            telos_score=0.5, stakes=0.5, persona_bias=None,
        )

        assert isinstance(alts[0]["score"], float)
        assert "score_raw" in alts[0]

    def test_value_core_import_failure(self):
        """If value_core import fails, scoring still works."""
        from veritas_os.core import kernel_stages

        with patch.dict("sys.modules", {"veritas_os.core.value_core": None}):
            alts = [{"id": "a", "title": "Test", "score": 1.0}]
            kernel_stages.score_alternatives(
                intent="plan", query="test", alternatives=alts,
                telos_score=0.5, stakes=0.5, persona_bias=None,
            )

        assert isinstance(alts[0]["score"], float)

    def test_empty_alternatives_returns_early(self):
        """Empty alternatives list → immediate return."""
        from veritas_os.core.kernel_stages import score_alternatives

        score_alternatives(
            intent="plan",
            query="test",
            alternatives=[],
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
        )
        # No exception, no crash


# =============================================================================
# Test: run_debate_stage – non-fast-mode (lines 370-459)
# =============================================================================

class TestRunDebateStageNonFast:

    def test_debate_success_path(self):
        """debate.run_debate succeeds → chosen from debate result."""
        from veritas_os.core import kernel_stages

        mock_return = {
            "chosen": {"id": "d1", "title": "Debated"},
            "options": [{"id": "d1", "title": "Debated", "score": 2.0}],
            "source": "openai_llm",
        }

        with patch("veritas_os.core.debate.run_debate", return_value=mock_return):
            alts = [{"id": "1", "title": "A", "score": 1.0}]
            result = kernel_stages.run_debate_stage(
                query="test", alternatives=alts, context={"user_id": "u1"}, fast_mode=False,
            )

        assert result["chosen"]["id"] == "d1"
        assert result["source"] == "openai_llm"
        assert len(result["debate_logs"]) == 1

    def test_debate_exception_fallback_with_alts(self):
        """debate.run_debate raises → fallback picks max score."""
        from veritas_os.core import kernel_stages

        with patch("veritas_os.core.debate.run_debate", side_effect=RuntimeError("LLM unavailable")):
            alts = [
                {"id": "1", "title": "Low", "score": 0.3},
                {"id": "2", "title": "High", "score": 0.9},
            ]
            result = kernel_stages.run_debate_stage(
                query="test", alternatives=alts, context={}, fast_mode=False,
            )

        assert result["chosen"]["id"] == "2"
        assert result["source"] == "fallback"

    def test_debate_exception_fallback_empty_alts(self):
        """debate.run_debate raises with empty alts → fallback option created."""
        from veritas_os.core import kernel_stages

        with patch("veritas_os.core.debate.run_debate", side_effect=RuntimeError("fail")):
            result = kernel_stages.run_debate_stage(
                query="test", alternatives=[], context={}, fast_mode=False,
            )

        assert result["chosen"] is not None
        assert result["chosen"]["title"] == "フォールバック選択"
        assert result["source"] == "fallback"


# =============================================================================
# Test: run_fuji_gate – full execution (lines 466-520)
# =============================================================================

class TestRunFujiGateFullExecution:

    @patch("veritas_os.core.fuji.evaluate")
    def test_fuji_evaluate_success(self, mock_evaluate):
        """fuji.evaluate succeeds → result returned directly."""
        from veritas_os.core import kernel_stages

        mock_evaluate.return_value = {
            "status": "allow",
            "decision_status": "allow",
            "risk": 0.02,
            "violations": [],
            "reasons": [],
        }

        result = kernel_stages.run_fuji_gate(
            query="safe query",
            context={"user_id": "u1", "stakes": 0.3, "mode": "normal",
                     "_computed_telos_score": 0.5},
            evidence=[{"text": "ev1"}],
            alternatives=[{"id": "a1"}],
        )

        assert result["status"] == "allow"
        assert result["risk"] == 0.02
        mock_evaluate.assert_called_once()

    @patch("veritas_os.core.fuji.evaluate")
    def test_fuji_evaluate_exception_returns_allow(self, mock_evaluate):
        """fuji.evaluate raises → fallback allow result."""
        from veritas_os.core import kernel_stages

        mock_evaluate.side_effect = Exception("fuji crash")

        result = kernel_stages.run_fuji_gate(
            query="test",
            context={"user_id": "u1"},
            evidence=[],
            alternatives=[],
        )

        assert result["status"] == "allow"
        assert result["risk"] == 0.05
        assert any("fuji_error" in r for r in result["reasons"])


# =============================================================================
# Test: update_persona_and_goals – full execution (lines 527-600)
# =============================================================================

class TestUpdatePersonaAndGoalsFull:

    @patch("veritas_os.core.agi_goals.auto_adjust_goals")
    @patch("veritas_os.core.adapt.save_persona")
    @patch("veritas_os.core.adapt.clean_bias_weights", side_effect=lambda b: b)
    @patch("veritas_os.core.adapt.update_persona_bias_from_history")
    def test_full_update_success(self, mock_update, mock_clean, mock_save, mock_adjust):
        """adapt + agi_goals + world all available → updated=True."""
        from veritas_os.core import kernel_stages

        mock_update.return_value = {
            "bias_weights": {"rest": 0.5, "work": 0.5},
        }
        mock_adjust.return_value = {"rest": 0.6, "work": 0.4}

        result = kernel_stages.update_persona_and_goals(
            chosen={"id": "1", "title": "休息"},
            context={"_world_sim_result": {"state": "ok"}},
            fuji_result={"risk": 0.1},
            telos_score=0.6,
            fast_mode=False,
        )

        assert result["updated"] is True
        assert result["error"] is None
        assert result["last_auto_adjust"]["value_ema"] == 0.6
        assert result["last_auto_adjust"]["fuji_risk"] == 0.1
        mock_save.assert_called_once()

    @patch("veritas_os.core.adapt.update_persona_bias_from_history")
    def test_update_exception_returns_error(self, mock_update):
        """If adapt raises → error captured, updated=False."""
        from veritas_os.core import kernel_stages

        mock_update.side_effect = RuntimeError("db fail")

        result = kernel_stages.update_persona_and_goals(
            chosen={"id": "1", "title": "test"},
            context={},
            fuji_result={"risk": 0.1},
            telos_score=0.5,
            fast_mode=False,
        )

        assert result["updated"] is False
        assert result["error"] is not None
        assert "db fail" in result["error"]

    @patch("veritas_os.core.agi_goals.auto_adjust_goals", return_value={})
    @patch("veritas_os.core.adapt.save_persona")
    @patch("veritas_os.core.adapt.clean_bias_weights", side_effect=lambda b: b)
    @patch("veritas_os.core.adapt.update_persona_bias_from_history")
    def test_update_with_no_world_sim_result(self, mock_update, mock_clean, mock_save, mock_adjust):
        """No _world_sim_result in context → world_snap is empty dict."""
        from veritas_os.core import kernel_stages

        mock_update.return_value = {
            "bias_weights": {},
        }

        result = kernel_stages.update_persona_and_goals(
            chosen={"id": "1", "title": "test"},
            context={},
            fuji_result={"risk": 0.05},
            telos_score=0.5,
            fast_mode=False,
        )

        assert result["updated"] is True


# =============================================================================
# Test: save_episode_to_memory – full execution (lines 603-666)
# =============================================================================

class TestSaveEpisodeToMemoryFull:

    @patch("veritas_os.core.memory.MEM")
    def test_mem_put_success(self, mock_mem_store):
        """MEM.put(episodic, ...) succeeds → True."""
        from veritas_os.core import kernel_stages

        mock_mem_store.put = MagicMock()

        result = kernel_stages.save_episode_to_memory(
            query="test query",
            chosen={"id": "1", "title": "chosen"},
            context={"user_id": "u1", "request_id": "r1"},
            intent="plan",
            mode="normal",
            telos_score=0.5,
        )

        assert result is True
        mock_mem_store.put.assert_called_once()
        args = mock_mem_store.put.call_args
        assert args[0][0] == "episodic"

    @patch("veritas_os.core.memory.MEM")
    def test_mem_put_typeerror_fallback(self, mock_mem_store):
        """MEM.put(episodic, ...) raises TypeError → fallback 3-arg call."""
        from veritas_os.core import kernel_stages

        call_count = 0

        def put_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TypeError("put() takes 3 positional arguments")
            return None

        mock_mem_store.put = MagicMock(side_effect=put_side_effect)

        result = kernel_stages.save_episode_to_memory(
            query="test",
            chosen={"id": "1", "title": "t"},
            context={"user_id": "u1", "request_id": "r1"},
            intent="test",
            mode="fast",
            telos_score=0.5,
        )

        assert result is True
        assert mock_mem_store.put.call_count == 2

    @patch("veritas_os.core.memory.MEM")
    def test_mem_put_general_exception_returns_false(self, mock_mem_store):
        """If MEM.put raises a non-TypeError exception → returns False."""
        from veritas_os.core import kernel_stages

        mock_mem_store.put = MagicMock(side_effect=ConnectionError("lost"))

        result = kernel_stages.save_episode_to_memory(
            query="test",
            chosen={"id": "1", "title": "t"},
            context={"user_id": "u1"},
            intent="test",
            mode="fast",
            telos_score=0.5,
        )

        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
