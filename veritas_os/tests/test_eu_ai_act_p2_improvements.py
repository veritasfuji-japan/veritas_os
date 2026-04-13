"""Tests for EU AI Act P2-1 through P2-4 improvements.

P2-1: Annex IV technical documentation templates (doc existence)
P2-2: Accuracy benchmark monitoring in doctor.py
P2-3: bench_mode synthetic-data-only validation
P2-4: End-user guide (doc existence)
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from veritas_os.core.eu_ai_act_compliance_module import (
    EUComplianceConfig,
    eu_compliance_pipeline,
    validate_bench_mode_synthetic_data,
)


# =====================================================================
# P2-1: Annex IV technical documentation templates
# =====================================================================
class TestAnnexIVDocumentation:
    """P2-1 — Annex IV compliant documentation templates exist."""

    REPO_ROOT = Path(__file__).resolve().parents[2]
    EU_AI_ACT_DIR = REPO_ROOT / "docs" / "eu_ai_act"

    def test_technical_documentation_exists(self) -> None:
        path = self.EU_AI_ACT_DIR / "technical_documentation.md"
        assert path.exists(), f"Missing: {path}"

    def test_intended_purpose_exists(self) -> None:
        path = self.EU_AI_ACT_DIR / "intended_purpose.md"
        assert path.exists(), f"Missing: {path}"

    def test_risk_assessment_exists(self) -> None:
        path = self.EU_AI_ACT_DIR / "risk_assessment.md"
        assert path.exists(), f"Missing: {path}"

    def test_performance_metrics_exists(self) -> None:
        path = self.EU_AI_ACT_DIR / "performance_metrics.md"
        assert path.exists(), f"Missing: {path}"

    def test_technical_documentation_contains_annex_iv(self) -> None:
        path = self.EU_AI_ACT_DIR / "technical_documentation.md"
        content = path.read_text(encoding="utf-8")
        assert "附属書IV" in content or "Annex IV" in content

    def test_risk_assessment_contains_residual_risk(self) -> None:
        """Art. 9(2)(c): residual risk documentation is required."""
        path = self.EU_AI_ACT_DIR / "risk_assessment.md"
        content = path.read_text(encoding="utf-8")
        assert "残留リスク" in content or "residual risk" in content.lower()


# =====================================================================
# P2-2: Accuracy benchmark monitoring in doctor.py
# =====================================================================
class TestAccuracyBenchmarkMonitoring:
    """P2-2 — doctor.py accuracy monitoring dashboard."""

    def test_analyze_accuracy_benchmarks_no_dir(self) -> None:
        from veritas_os.scripts import doctor

        original = doctor.BENCH_DIR
        try:
            doctor.BENCH_DIR = Path("/nonexistent/dir/for/testing")
            result = doctor.analyze_accuracy_benchmarks()
            assert result["status"] == "no_benchmark_dir"
            assert result["total_runs"] == 0
        finally:
            doctor.BENCH_DIR = original

    def test_analyze_accuracy_benchmarks_empty_dir(self) -> None:
        from veritas_os.scripts import doctor

        original = doctor.BENCH_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                doctor.BENCH_DIR = Path(tmpdir)
                result = doctor.analyze_accuracy_benchmarks()
                assert result["status"] == "no_results"
                assert result["total_runs"] == 0
            finally:
                doctor.BENCH_DIR = original

    def test_analyze_accuracy_benchmarks_with_results(self) -> None:
        from veritas_os.scripts import doctor

        original = doctor.BENCH_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                doctor.BENCH_DIR = Path(tmpdir)
                # Write a benchmark result file
                result_file = Path(tmpdir) / "bench_001.json"
                result_file.write_text(
                    json.dumps({
                        "benchmark": "test_bench",
                        "model": "gpt-4.1-mini",
                        "accuracy": 0.85,
                        "timestamp": "2026-03-06T12:00:00Z",
                    }),
                    encoding="utf-8",
                )
                result = doctor.analyze_accuracy_benchmarks()
                assert result["status"] == "ok"
                assert result["total_runs"] == 1
                assert result["accuracy_avg"] == 0.85
                assert result["drift_detected"] is False
            finally:
                doctor.BENCH_DIR = original

    def test_drift_detection(self) -> None:
        from veritas_os.scripts import doctor

        original = doctor.BENCH_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                doctor.BENCH_DIR = Path(tmpdir)
                # Write multiple runs: first ones high, recent ones dropping
                runs = (
                    [{"accuracy": 0.90}] * 10
                    + [{"accuracy": 0.70}] * 5
                )
                result_file = Path(tmpdir) / "bench_drift.json"
                result_file.write_text(json.dumps(runs), encoding="utf-8")
                result = doctor.analyze_accuracy_benchmarks()
                assert result["drift_detected"] is True
                assert result["drift_details"] is not None
            finally:
                doctor.BENCH_DIR = original

    def test_no_drift_when_stable(self) -> None:
        from veritas_os.scripts import doctor

        original = doctor.BENCH_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                doctor.BENCH_DIR = Path(tmpdir)
                runs = [{"accuracy": 0.85}] * 10
                result_file = Path(tmpdir) / "bench_stable.json"
                result_file.write_text(json.dumps(runs), encoding="utf-8")
                result = doctor.analyze_accuracy_benchmarks()
                assert result["drift_detected"] is False
            finally:
                doctor.BENCH_DIR = original


# =====================================================================
# P2-3: bench_mode synthetic-data-only validation
# =====================================================================
class TestBenchModeSyntheticDataValidation:
    """P2-3 — bench_mode rejects data containing real PII markers."""

    def test_normal_mode_always_passes(self) -> None:
        result = validate_bench_mode_synthetic_data(
            mode="normal",
            data_text="user@gmail.com is a real email",
        )
        assert result["passed"] is True
        assert result["reason"] == "not_bench_mode"

    def test_bench_mode_blocks_email_markers(self) -> None:
        result = validate_bench_mode_synthetic_data(
            mode="bench",
            data_text="Contact john@gmail.com for more info",
        )
        assert result["passed"] is False
        assert "@gmail." in result["detected_markers"]

    def test_bench_mode_blocks_ssn_keyword(self) -> None:
        result = validate_bench_mode_synthetic_data(
            mode="bench",
            data_text="My social security number is important",
        )
        assert result["passed"] is False
        assert "social security" in result["detected_markers"]

    def test_bench_mode_blocks_numeric_pattern(self) -> None:
        result = validate_bench_mode_synthetic_data(
            mode="bench",
            data_text="Card 4111-1111-1111-1111 is a test card",
        )
        assert result["passed"] is False
        assert "pii_numeric_pattern" in result["detected_markers"]

    def test_bench_mode_blocks_japanese_pii(self) -> None:
        result = validate_bench_mode_synthetic_data(
            mode="bench",
            data_text="マイナンバーは重要な個人情報です",
        )
        assert result["passed"] is False
        assert "マイナンバー" in result["detected_markers"]

    def test_bench_mode_passes_synthetic_data(self) -> None:
        result = validate_bench_mode_synthetic_data(
            mode="bench",
            data_text="Evaluate the business strategy for Q4 planning",
        )
        assert result["passed"] is True
        assert result["reason"] == "synthetic_data_check_passed"

    def test_bench_mode_with_override_allows_all(self) -> None:
        result = validate_bench_mode_synthetic_data(
            mode="bench",
            data_text="Contact john@gmail.com for details",
            config=EUComplianceConfig(bench_mode_pii_override=True),
        )
        assert result["passed"] is True
        assert result["reason"] == "bench_mode_pii_override_enabled"

    def test_internal_eval_mode_also_checked(self) -> None:
        result = validate_bench_mode_synthetic_data(
            mode="internal_eval",
            data_text="Passport number 123456789",
        )
        assert result["passed"] is False
        assert "passport number" in result["detected_markers"]


class TestPipelineBenchModeSyntheticData:
    """P2-3 — pipeline decorator blocks bench_mode with real PII data."""

    def test_pipeline_blocks_bench_with_real_pii(self) -> None:
        @eu_compliance_pipeline(config=EUComplianceConfig(enabled=True))
        def fake_decide(**kwargs: object) -> dict:
            return {"output": "ok", "trust_score": 0.9}

        result = fake_decide(
            prompt="Contact john@gmail.com for hiring details",
            mode="bench",
        )
        assert result["status"] == "BLOCKED"
        assert result["blocked_by"] == "P2-3_synthetic_data_only"

    def test_pipeline_allows_bench_with_synthetic_data(self) -> None:
        @eu_compliance_pipeline(config=EUComplianceConfig(
            enabled=True,
            require_audit_for_high_risk=False,
        ))
        def fake_decide(**kwargs: object) -> dict:
            return {"output": "safe response", "trust_score": 0.9}

        result = fake_decide(
            prompt="Evaluate the best team building activity",
            mode="bench",
        )
        # Should not be blocked by P2-3 (no PII markers)
        # May still be blocked by P1-6 bench_mode PII safety
        assert result.get("blocked_by") != "P2-3_synthetic_data_only"


# =====================================================================
# P2-4: End-user guide
# =====================================================================
class TestUserGuide:
    """P2-4 — EU AI Act end-user guide exists with required sections."""

    REPO_ROOT = Path(__file__).resolve().parents[2]

    def test_user_guide_exists(self) -> None:
        path = self.REPO_ROOT / "docs" / "ja" / "governance" / "user-guide-eu-ai-act.md"
        assert path.exists(), f"Missing: {path}"

    def test_user_guide_contains_intended_use(self) -> None:
        path = self.REPO_ROOT / "docs" / "ja" / "governance" / "user-guide-eu-ai-act.md"
        content = path.read_text(encoding="utf-8")
        assert "意図された用途" in content or "intended" in content.lower()

    def test_user_guide_contains_human_oversight(self) -> None:
        path = self.REPO_ROOT / "docs" / "ja" / "governance" / "user-guide-eu-ai-act.md"
        content = path.read_text(encoding="utf-8")
        assert "人間" in content or "human" in content.lower()

    def test_user_guide_contains_contestation(self) -> None:
        """Art. 13 requires info on how to contest AI decisions."""
        path = self.REPO_ROOT / "docs" / "ja" / "governance" / "user-guide-eu-ai-act.md"
        content = path.read_text(encoding="utf-8")
        assert "異議" in content or "contest" in content.lower()
