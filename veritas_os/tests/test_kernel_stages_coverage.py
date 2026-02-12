# veritas_os/tests/test_kernel_stages_coverage.py
# -*- coding: utf-8 -*-
"""
kernel_stages モジュールのカバレッジテスト

例外パスとモジュール統合のテストケース
"""
import pytest
from unittest.mock import patch, MagicMock


# =============================================================================
# Test: collect_memory_evidence - Exception Paths
# =============================================================================

class TestCollectMemoryEvidenceExceptionPaths:
    """collect_memory_evidence の例外パスをテスト"""

    def test_memory_summarize_success(self):
        """メモリ要約が成功するケース"""
        from veritas_os.core.kernel_stages import collect_memory_evidence

        # Patch the memory module where it's imported in kernel_stages
        with patch("veritas_os.core.memory.summarize_for_planner") as mock_summarize:
            mock_summarize.return_value = "summary text"
            
            result = collect_memory_evidence(
                user_id="test_user",
                query="test query",
                context={},
                fast_mode=False,
            )

            # Expected: result["memory_summary"] == "summary text"
            assert result["memory_summary"] == "summary text"
            assert result["source"] == "MemoryOS.summarize_for_planner"

    def test_memory_summarize_exception(self):
        """メモリ要約が例外を発生させるケース"""
        from veritas_os.core.kernel_stages import collect_memory_evidence

        # Patch the memory module where it's imported in kernel_stages
        with patch("veritas_os.core.memory.summarize_for_planner") as mock_summarize:
            mock_summarize.side_effect = Exception("Memory error")
            
            result = collect_memory_evidence(
                user_id="test_user",
                query="test query",
                context={},
                fast_mode=False,
            )

            # Expected: "error" in result["source"]
            assert "error" in result["source"]


# =============================================================================
# Test: run_world_simulation - Actual Module Integration
# =============================================================================

class TestRunWorldSimulationActualModule:
    """run_world_simulation の実モジュール統合テスト"""

    def test_world_simulate_success(self):
        """World シミュレーションが成功するケース"""
        from veritas_os.core.kernel_stages import run_world_simulation

        # Patch the world module where it's imported in kernel_stages
        with patch("veritas_os.core.world.simulate") as mock_simulate:
            mock_simulate.return_value = {"outcome": "ok"}
            
            result = run_world_simulation(
                user_id="test_user",
                query="test query",
                context={},
                fast_mode=False,
            )

            # Expected: result["simulation"] == {"outcome": "ok"}
            assert result["simulation"] == {"outcome": "ok"}
            assert result["source"] == "world.simulate()"

    def test_world_simulate_exception(self):
        """World シミュレーションが例外を発生させるケース"""
        from veritas_os.core.kernel_stages import run_world_simulation

        # Patch the world module where it's imported in kernel_stages
        with patch("veritas_os.core.world.simulate") as mock_simulate:
            mock_simulate.side_effect = Exception("World error")
            
            result = run_world_simulation(
                user_id="test_user",
                query="test query",
                context={},
                fast_mode=False,
            )

            # Expected: "error" in result["source"]
            assert "error" in result["source"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
