"""Tests for remaining EU AI Act compliance gaps.

GAP-01: Art. 5  — Expanded prohibited-pattern detection (synonyms, evasion)
Art. 14(4)     — System halt / emergency stop controller
GAP-05: Art. 10 — Data quality validation for dataset writes
"""
from __future__ import annotations

from veritas_os.core.eu_ai_act_compliance_module import (
    EUAIActSafetyGateLayer4,
    EUComplianceConfig,
    SystemHaltController,
    eu_compliance_pipeline,
    validate_data_quality,
)


# =====================================================================
# GAP-01: Art. 5 — Expanded prohibited-pattern detection
# =====================================================================
class TestExpandedArticle5Patterns:
    """GAP-01 — synonym / euphemism / multi-language detection."""

    def test_social_credit_synonym(self) -> None:
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("implement a social credit system for citizens")
        assert not result["passed"]
        assert any("social credit" in v for v in result["violations"])

    def test_citizen_score_synonym(self) -> None:
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("assign each citizen score based on behavior")
        assert not result["passed"]

    def test_facial_recognition_synonym(self) -> None:
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("deploy facial recognition in public spaces")
        assert not result["passed"]

    def test_mass_surveillance_synonym(self) -> None:
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("enable mass surveillance of the population")
        assert not result["passed"]

    def test_psychological_manipulation_synonym(self) -> None:
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("use psychological manipulation techniques")
        assert not result["passed"]

    def test_japanese_mass_surveillance(self) -> None:
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("大量監視システムを導入する")
        assert not result["passed"]

    def test_french_facial_recognition(self) -> None:
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("déployer la reconnaissance faciale")
        assert not result["passed"]

    def test_input_detects_new_synonyms(self) -> None:
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5_input("build a behavioural scoring engine")
        assert not result["passed"]

    def test_evasion_with_hyphens(self) -> None:
        gate = EUAIActSafetyGateLayer4()
        # "mani-pulat" -> after stripping hyphens -> "manipulat" matches pattern
        result = gate.validate_article_5("use mani-pulative techniques on users")
        assert not result["passed"], "Hyphenated evasion should be caught"

    def test_safe_text_passes(self) -> None:
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("Analyze quarterly revenue data for the board")
        assert result["passed"]


# =====================================================================
# Art. 14(4): System halt / emergency stop controller
# =====================================================================
class TestSystemHaltController:
    """Art. 14(4) — Human operator halt/resume mechanism."""

    def setup_method(self) -> None:
        SystemHaltController.clear_for_testing()

    def test_initial_state_not_halted(self) -> None:
        assert SystemHaltController.is_halted() is False
        status = SystemHaltController.status()
        assert status["halted"] is False
        assert status["halted_by"] is None

    def test_halt_sets_state(self) -> None:
        result = SystemHaltController.halt(
            reason="Safety concern detected",
            operator="reviewer@example.com",
        )
        assert result["halted"] is True
        assert result["halted_by"] == "reviewer@example.com"
        assert result["reason"] == "Safety concern detected"
        assert SystemHaltController.is_halted() is True

    def test_resume_clears_state(self) -> None:
        SystemHaltController.halt(reason="test", operator="admin")
        result = SystemHaltController.resume(operator="admin", comment="issue resolved")
        assert result["resumed"] is True
        assert result["was_halted"] is True
        assert SystemHaltController.is_halted() is False

    def test_resume_when_not_halted(self) -> None:
        result = SystemHaltController.resume(operator="admin")
        assert result["resumed"] is True
        assert result["was_halted"] is False

    def test_status_reflects_halt(self) -> None:
        SystemHaltController.halt(reason="emergency", operator="ops")
        status = SystemHaltController.status()
        assert status["halted"] is True
        assert status["reason"] == "emergency"
        assert status["halted_by"] == "ops"
        assert status["halted_at"] is not None

    def test_pipeline_blocks_when_halted(self) -> None:
        """When the system is halted, the compliance pipeline should refuse all requests."""
        SystemHaltController.halt(reason="audit required", operator="auditor")

        @eu_compliance_pipeline(config=EUComplianceConfig())
        def dummy_decide(**kwargs):
            return {"output": "should not reach here", "trust_score": 0.95}

        result = dummy_decide(prompt="simple question")
        assert result["status"] == "HALTED"
        assert result["decision_status"] == "rejected"
        assert "Art.14(4)" in result["blocked_by"]
        assert "audit required" in result["rejection_reason"]

    def test_pipeline_works_after_resume(self) -> None:
        """After resume, the pipeline should process normally."""
        SystemHaltController.halt(reason="test halt", operator="admin")
        SystemHaltController.resume(operator="admin")

        @eu_compliance_pipeline(config=EUComplianceConfig())
        def dummy_decide(**kwargs):
            return {"output": "hello", "trust_score": 0.95}

        result = dummy_decide(prompt="simple question")
        assert result.get("status") != "HALTED"


# =====================================================================
# GAP-05: Art. 10 — Data quality validation
# =====================================================================
class TestDataQualityValidation:
    """GAP-05 — data quality checks for dataset writes."""

    def test_valid_data_passes(self) -> None:
        result = validate_data_quality(
            text="This is a meaningful piece of training data for the model.",
            kind="training",
        )
        assert result["passed"] is True
        assert result["issues"] == []
        assert result["quality_score"] == 1.0

    def test_empty_text_fails(self) -> None:
        result = validate_data_quality(text="", kind="training")
        assert result["passed"] is False
        assert any("empty_content" in i for i in result["issues"])

    def test_whitespace_only_fails(self) -> None:
        result = validate_data_quality(text="   \n\t  ", kind="semantic")
        assert result["passed"] is False
        assert any("empty_content" in i for i in result["issues"])

    def test_too_short_text_fails(self) -> None:
        result = validate_data_quality(text="hi", kind="training")
        assert result["passed"] is False
        assert any("too_short" in i for i in result["issues"])

    def test_low_diversity_fails(self) -> None:
        # Highly repetitive text
        result = validate_data_quality(
            text="word " * 50,
            kind="training",
        )
        assert result["passed"] is False
        assert any("low_diversity" in i for i in result["issues"])

    def test_unknown_kind_flagged(self) -> None:
        result = validate_data_quality(
            text="Valid text content here for testing quality.",
            kind="unknown_category",
        )
        assert result["passed"] is False
        assert any("unknown_kind" in i for i in result["issues"])

    def test_valid_kind_accepted(self) -> None:
        for kind in ("semantic", "episodic", "training", "validation", "test"):
            result = validate_data_quality(
                text="Sufficient text content for validation check.",
                kind=kind,
            )
            assert result["passed"] is True, f"kind={kind} should be accepted"

    def test_null_bytes_rejected(self) -> None:
        result = validate_data_quality(
            text="some text with\x00null bytes",
            kind="training",
        )
        assert result["passed"] is False
        assert any("null_bytes" in i for i in result["issues"])

    def test_quality_score_decreases_with_issues(self) -> None:
        result = validate_data_quality(text="", kind="invalid_kind")
        assert result["quality_score"] < 1.0
        # Multiple issues should reduce the score further
        assert len(result["issues"]) >= 2

    def test_empty_kind_is_accepted(self) -> None:
        """When no kind is provided, the kind check is skipped."""
        result = validate_data_quality(
            text="Valid text content that is long enough for the check.",
        )
        assert result["passed"] is True

    def test_art10_reference(self) -> None:
        result = validate_data_quality(text="some valid text content here")
        assert result["eu_ai_act_article"] == "Art. 10"
