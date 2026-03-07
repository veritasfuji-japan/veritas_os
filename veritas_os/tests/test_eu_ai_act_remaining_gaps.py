"""Tests for remaining EU AI Act compliance gaps.

GAP-01: Art. 5  — Expanded prohibited-pattern detection (synonyms, evasion)
Art. 14(4)     — System halt / emergency stop controller
GAP-05: Art. 10 — Data quality validation for dataset writes
P1-5:          — Deployment readiness check
"""
from __future__ import annotations

from veritas_os.core.eu_ai_act_compliance_module import (
    EUAIActSafetyGateLayer4,
    EUComplianceConfig,
    SystemHaltController,
    classify_annex_iii_risk,
    eu_compliance_pipeline,
    validate_data_quality,
    validate_deployment_readiness,
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

    def test_confusable_cyrillic_evasion(self) -> None:
        """GAP-01: Cyrillic homoglyphs must not bypass detection."""
        gate = EUAIActSafetyGateLayer4()
        # "subliminal" with Cyrillic 'а' (U+0430) instead of Latin 'a'
        result = gate.validate_article_5("use sublimin\u0430l techniques")
        assert not result["passed"], "Cyrillic homoglyph evasion should be caught"

    def test_confusable_greek_evasion(self) -> None:
        """GAP-01: Greek homoglyphs must not bypass detection."""
        gate = EUAIActSafetyGateLayer4()
        # "manipulat" with Greek Α (U+0391) → 'a'
        result = gate.validate_article_5("m\u0391nipulat the outcome")
        assert not result["passed"], "Greek homoglyph evasion should be caught"

    def test_spaced_evasion_manipulate(self) -> None:
        """GAP-01: Space-separated chars must not bypass detection."""
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("we will m a n i p u l a t e users")
        assert not result["passed"], "Space-insertion evasion should be caught"

    def test_spaced_evasion_subliminal(self) -> None:
        """GAP-01: Space-separated 'subliminal' is detected."""
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("apply s u b l i m i n a l methods")
        assert not result["passed"], "Space-insertion evasion should be caught"

    def test_fullwidth_evasion(self) -> None:
        """GAP-01: Fullwidth chars (NFKC-normalised to ASCII) must be caught."""
        gate = EUAIActSafetyGateLayer4()
        # Fullwidth "subliminal" → NFKC normalises to ASCII "subliminal"
        result = gate.validate_article_5("\uff53\uff55\uff42\uff4c\uff49\uff4d\uff49\uff4e\uff41\uff4c")
        assert not result["passed"], "Fullwidth evasion should be caught"

    def test_normal_short_words_not_collapsed(self) -> None:
        """Ensure common short words are not false-positively collapsed."""
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("I am a new employee at the company")
        assert result["passed"]


class TestRiskClassificationNormalization:
    """GAP-01: Annex III risk classification with evasion normalization."""

    def test_confusable_hiring_detected(self) -> None:
        """Cyrillic 'і' (U+0456) in 'hiring' must still trigger HIGH risk."""
        result = classify_annex_iii_risk("AI for h\u0456ring decisions")
        assert result["risk_level"] == "HIGH"
        assert "hiring" in result["matched_categories"]

    def test_fullwidth_healthcare_detected(self) -> None:
        """Fullwidth 'healthcare' must still trigger HIGH risk after NFKC."""
        result = classify_annex_iii_risk(
            "\uff48\uff45\uff41\uff4c\uff54\uff48\uff43\uff41\uff52\uff45 system"
        )
        assert result["risk_level"] == "HIGH"
        assert "healthcare" in result["matched_categories"]

    def test_hyphenated_biometric_detected(self) -> None:
        """Hyphen-inserted 'bio-metric' must still trigger HIGH risk."""
        result = classify_annex_iii_risk("AI for bio-metric identification")
        assert result["risk_level"] == "HIGH"
        assert "biometric" in result["matched_categories"]

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
        for kind in ("semantic", "episodic", "procedural", "factual",
                     "training", "validation", "test", "feedback"):
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


# =====================================================================
# P1-5: Deployment readiness check
# =====================================================================
import os
import tempfile


class TestDeploymentReadiness:
    """Tests for validate_deployment_readiness (P1-5 / P1-6)."""

    def test_ready_with_all_artefacts(self, monkeypatch) -> None:
        """When all artefacts exist, are fresh, and env is configured, readiness passes."""
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", "test-dummy-key")
        monkeypatch.setenv("VERITAS_HUMAN_REVIEW_WEBHOOK_URL", "https://hook.example.com")
        result = validate_deployment_readiness()
        assert result["ready"] is True
        assert result["issues"] == []
        assert "model_card" in result["checks"]
        assert "bias_assessment" in result["checks"]
        assert "dpa_checklist" in result["checks"]
        assert "environment" in result

    def test_missing_artefact(self) -> None:
        """When an artefact is missing, readiness fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_deployment_readiness(repo_root=tmpdir)
        assert result["ready"] is False
        # 3 missing artefacts + environment issues (encryption, webhook, possibly retention)
        assert any("model_card" in i for i in result["issues"])

    def test_stale_artefact(self) -> None:
        """When an artefact exists but is stale, readiness fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create the directory structure and files
            docs_dir = os.path.join(tmpdir, "docs", "eu_ai_act")
            os.makedirs(docs_dir)
            for fname in (
                "model_card_gpt41_mini.md",
                "bias_assessment_report.md",
                "third_party_model_dpa_checklist.md",
            ):
                fpath = os.path.join(docs_dir, fname)
                with open(fpath, "w") as f:
                    f.write("# placeholder")
                # Set mtime to 200 days ago
                old_time = os.path.getmtime(fpath) - (200 * 86400)
                os.utime(fpath, (old_time, old_time))

            result = validate_deployment_readiness(repo_root=tmpdir)

        assert result["ready"] is False
        assert any("model_card" in i for i in result["issues"])
        assert any("bias_assessment" in i for i in result["issues"])

    def test_deployment_readiness_includes_article_references(self) -> None:
        result = validate_deployment_readiness()
        assert "Art. 10" in result["eu_ai_act_article"]
        assert "P1-5" in result["eu_ai_act_article"]

    def test_environment_section_present(self) -> None:
        """P1-6: environment section is always included."""
        result = validate_deployment_readiness()
        assert "environment" in result
        env = result["environment"]
        assert "encryption_enabled" in env
        assert "notification_webhook_configured" in env
        assert "log_retention_days" in env
        assert "log_retention_compliant" in env

    def test_missing_encryption_reported(self, monkeypatch) -> None:
        """P1-6: missing encryption key is reported as an issue."""
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
        result = validate_deployment_readiness()
        assert any("encryption" in i for i in result["issues"])

    def test_missing_webhook_reported(self, monkeypatch) -> None:
        """P1-6: missing webhook URL is reported as an issue."""
        monkeypatch.delenv("VERITAS_HUMAN_REVIEW_WEBHOOK_URL", raising=False)
        result = validate_deployment_readiness()
        assert any("notification" in i or "webhook" in i for i in result["issues"])
