"""Tests for GAP-01 / GAP-02 review improvements.

GAP-01: Art. 5  — N-gram semantic similarity detection for prohibited practices
GAP-02: Art. 6  — Legal approval validation and CE marking readiness
"""
from __future__ import annotations

import json
import os
import tempfile

from veritas_os.core.eu_ai_act_compliance_module import (
    EUAIActSafetyGateLayer4,
    _char_ngrams,
    _ngram_similarity,
    _semantic_ngram_check,
    validate_ce_marking_readiness,
    validate_deployment_readiness,
    validate_legal_approval,
)


# =====================================================================
# GAP-01: N-gram semantic similarity detection (Art. 5)
# =====================================================================


class TestCharNgrams:
    """Tests for _char_ngrams helper."""

    def test_basic_ngrams(self) -> None:
        result = _char_ngrams("hello", 3)
        assert "hel" in result
        assert "ell" in result
        assert "llo" in result
        assert len(result) == 3

    def test_short_text_returns_text(self) -> None:
        result = _char_ngrams("ab", 3)
        assert result == {"ab"}

    def test_empty_text(self) -> None:
        result = _char_ngrams("", 3)
        assert result == set()


class TestNgramSimilarity:
    """Tests for _ngram_similarity Jaccard function."""

    def test_identical_strings(self) -> None:
        sim = _ngram_similarity("hello world", "hello world")
        assert sim == 1.0

    def test_completely_different(self) -> None:
        sim = _ngram_similarity("aaa", "zzz")
        assert sim == 0.0

    def test_partial_overlap(self) -> None:
        sim = _ngram_similarity("hello", "help")
        assert 0.0 < sim < 1.0

    def test_empty_string(self) -> None:
        sim = _ngram_similarity("", "hello")
        assert sim == 0.0


class TestSemanticNgramCheck:
    """Tests for _semantic_ngram_check Art. 5 detection."""

    def test_close_paraphrase_detected(self) -> None:
        """A paraphrase of a prohibited description should be caught."""
        text = "use subliminal techniques beyond consciousness to distort behavior of person"
        violations = _semantic_ngram_check(text)
        assert len(violations) > 0
        assert any("semantic:" in v for v in violations)

    def test_benign_text_not_flagged(self) -> None:
        """Ordinary benign text should not trigger semantic detection."""
        text = "please help me write a report about quarterly sales performance"
        violations = _semantic_ngram_check(text)
        assert violations == []

    def test_mass_surveillance_paraphrase(self) -> None:
        """Paraphrased mass surveillance reference should be detected."""
        text = "indiscriminate mass surveillance of the entire population without consent"
        violations = _semantic_ngram_check(text)
        assert len(violations) > 0

    def test_very_short_text_no_crash(self) -> None:
        """Very short text should not crash or raise errors."""
        violations = _semantic_ngram_check("hi")
        assert isinstance(violations, list)


class TestSemanticIntegrationInSafetyGate:
    """Tests that semantic detection is integrated into the safety gate."""

    def test_paraphrased_prohibited_practice_blocked(self) -> None:
        """A paraphrased prohibited practice should be caught by the gate."""
        gate = EUAIActSafetyGateLayer4()
        # This paraphrase avoids all exact keyword matches but is semantically
        # close to a prohibited Art. 5 description.
        text = (
            "techniques beyond consciousness to distort behavior "
            "of persons through hidden cues and signals"
        )
        result = gate.validate_article_5(text)
        assert result["passed"] is False
        assert any("semantic:" in v for v in result["violations"])

    def test_keyword_match_still_works(self) -> None:
        """Keyword-based detection should still work as before."""
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("this uses subliminal manipulation")
        assert result["passed"] is False
        assert any("subliminal" in v for v in result["violations"])

    def test_benign_text_passes(self) -> None:
        """Normal text should pass both keyword and semantic checks."""
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("quarterly earnings report shows growth")
        assert result["passed"] is True
        assert result["violations"] == []

    def test_input_validation_also_uses_semantic(self) -> None:
        """validate_article_5_input should also use the semantic check."""
        gate = EUAIActSafetyGateLayer4()
        text = (
            "exploit cognitive biases to manipulate decisions "
            "and undermine individual autonomy"
        )
        result = gate.validate_article_5_input(text)
        assert result["passed"] is False
        assert result["scope"] == "input"


# =====================================================================
# GAP-02: Legal approval validation (Art. 6)
# =====================================================================


class TestLegalApproval:
    """Tests for validate_legal_approval (GAP-02 / Art. 6)."""

    def test_missing_file(self) -> None:
        """When legal_approval.json is missing, validation fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_legal_approval(repo_root=tmpdir)
        assert result["valid"] is False
        assert any("legal_approval_missing" in i for i in result["issues"])
        assert "Art. 6" in result["eu_ai_act_article"]

    def test_valid_approval(self) -> None:
        """A complete and approved record passes validation."""
        record = {
            "approved_by": "Legal Team Lead",
            "approval_date": "2026-03-07",
            "risk_classification": "high-risk",
            "scope": "VERITAS OS v2.0",
            "status": "approved",
        }
        result = validate_legal_approval(approval_record=record)
        assert result["valid"] is True
        assert result["issues"] == []

    def test_pending_status_fails(self) -> None:
        """A record with pending status is not valid."""
        record = {
            "approved_by": "Legal Team",
            "approval_date": "2026-03-07",
            "risk_classification": "high-risk",
            "scope": "VERITAS OS v2.0",
            "status": "pending",
        }
        result = validate_legal_approval(approval_record=record)
        assert result["valid"] is False
        assert any("status" in i for i in result["issues"])

    def test_missing_fields(self) -> None:
        """Missing required fields are reported."""
        record = {"status": "approved"}
        result = validate_legal_approval(approval_record=record)
        assert result["valid"] is False
        assert any("approved_by" in i for i in result["issues"])
        assert any("approval_date" in i for i in result["issues"])

    def test_reads_from_file(self) -> None:
        """Can read approval record from JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = os.path.join(tmpdir, "docs", "eu_ai_act")
            os.makedirs(docs_dir)
            record = {
                "approved_by": "Legal Team",
                "approval_date": "2026-03-07",
                "risk_classification": "high-risk",
                "scope": "VERITAS OS",
                "status": "approved",
            }
            with open(os.path.join(docs_dir, "legal_approval.json"), "w") as f:
                json.dump(record, f)
            result = validate_legal_approval(repo_root=tmpdir)
        assert result["valid"] is True

    def test_invalid_json_format(self) -> None:
        """Non-dict JSON is rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = os.path.join(tmpdir, "docs", "eu_ai_act")
            os.makedirs(docs_dir)
            with open(os.path.join(docs_dir, "legal_approval.json"), "w") as f:
                json.dump(["not", "a", "dict"], f)
            result = validate_legal_approval(repo_root=tmpdir)
        assert result["valid"] is False
        assert any("legal_approval_format" in i for i in result["issues"])


# =====================================================================
# GAP-02: CE marking readiness (Art. 6 / Art. 43)
# =====================================================================


class TestCEMarkingReadiness:
    """Tests for validate_ce_marking_readiness (GAP-02)."""

    def test_all_complete(self) -> None:
        """All prerequisites met returns ready."""
        checklist = {
            "risk_classification_approved": True,
            "technical_documentation_complete": True,
            "conformity_assessment_done": True,
            "quality_management_system": True,
            "post_market_monitoring_plan": True,
        }
        result = validate_ce_marking_readiness(checklist=checklist)
        assert result["ready"] is True
        assert result["missing"] == []
        assert len(result["completed"]) == 5

    def test_none_complete(self) -> None:
        """Empty checklist returns all missing."""
        result = validate_ce_marking_readiness(checklist={})
        assert result["ready"] is False
        assert len(result["missing"]) == 5

    def test_partial_complete(self) -> None:
        """Partial completion lists both completed and missing."""
        checklist = {
            "risk_classification_approved": True,
            "technical_documentation_complete": True,
        }
        result = validate_ce_marking_readiness(checklist=checklist)
        assert result["ready"] is False
        assert "risk_classification_approved" in result["completed"]
        assert "conformity_assessment_done" in result["missing"]
        assert "Art. 6" in result["eu_ai_act_article"]

    def test_reads_from_legal_approval_file(self) -> None:
        """CE marking data can be loaded from legal_approval.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = os.path.join(tmpdir, "docs", "eu_ai_act")
            os.makedirs(docs_dir)
            data = {
                "status": "approved",
                "ce_marking": {
                    "risk_classification_approved": True,
                    "technical_documentation_complete": True,
                    "conformity_assessment_done": True,
                    "quality_management_system": True,
                    "post_market_monitoring_plan": True,
                },
            }
            with open(os.path.join(docs_dir, "legal_approval.json"), "w") as f:
                json.dump(data, f)
            result = validate_ce_marking_readiness(repo_root=tmpdir)
        assert result["ready"] is True


# =====================================================================
# GAP-02: Deployment readiness integration
# =====================================================================


class TestDeploymentReadinessGAP02Integration:
    """Tests that GAP-02 checks are integrated into deployment readiness."""

    def test_legal_approval_section_present(self) -> None:
        """Deployment readiness includes legal_approval section."""
        result = validate_deployment_readiness()
        assert "legal_approval" in result
        assert "valid" in result["legal_approval"]

    def test_ce_marking_section_present(self) -> None:
        """Deployment readiness includes ce_marking section."""
        result = validate_deployment_readiness()
        assert "ce_marking" in result
        assert "ready" in result["ce_marking"]
        assert "missing" in result["ce_marking"]

    def test_unapproved_legal_blocks_readiness(self) -> None:
        """Unapproved legal status blocks deployment readiness."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = os.path.join(tmpdir, "docs", "eu_ai_act")
            os.makedirs(docs_dir)
            # Create valid artefacts
            for fname in (
                "model_card_gpt41_mini.md",
                "bias_assessment_report.md",
                "third_party_model_dpa_checklist.md",
            ):
                with open(os.path.join(docs_dir, fname), "w") as f:
                    f.write("# placeholder")
            # Create pending legal approval
            with open(os.path.join(docs_dir, "legal_approval.json"), "w") as f:
                json.dump({"status": "pending"}, f)
            result = validate_deployment_readiness(repo_root=tmpdir)
        assert result["ready"] is False
        assert any("legal_approval" in i for i in result["issues"])
