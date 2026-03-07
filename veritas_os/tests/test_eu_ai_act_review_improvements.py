"""Tests for EU AI Act compliance improvements from review document.

Art. 9 / GAP-01d  — Spaced-evasion detection in classify_annex_iii_risk()
Art. 13 / Art. 50  — Transparency field injection in eu_compliance_pipeline
Art. 11 / Art. 15  — Change management validation
Art. 10             — Deployment readiness change management integration
"""
from __future__ import annotations

import json
import os
import tempfile

from veritas_os.core.eu_ai_act_compliance_module import (
    AI_DISCLOSURE_TEXT,
    AI_REGULATION_NOTICE,
    EUComplianceConfig,
    HumanReviewQueue,
    SystemHaltController,
    ThirdPartyNotificationService,
    classify_annex_iii_risk,
    eu_compliance_pipeline,
    validate_change_management,
    validate_deployment_readiness,
)


# =====================================================================
# GAP-01d: Art. 9 — Spaced-evasion detection in classify_annex_iii_risk
# =====================================================================
class TestClassifyAnnexIIISpacedEvasion:
    """GAP-01d: Space-separated letters must be collapsed before matching."""

    def test_spaced_hiring_detected(self) -> None:
        """'h i r i n g' should be collapsed to 'hiring' and detected."""
        result = classify_annex_iii_risk("Use AI for h i r i n g decisions")
        assert result["risk_level"] == "HIGH"
        assert "hiring" in result["matched_categories"]

    def test_spaced_medical_detected(self) -> None:
        """'m e d i c a l' should be collapsed and matched."""
        result = classify_annex_iii_risk("Apply m e d i c a l screening")
        assert result["risk_level"] == "HIGH"
        assert "medical" in result["matched_categories"]

    def test_spaced_credit_detected(self) -> None:
        """'c r e d i t' should be collapsed and matched."""
        result = classify_annex_iii_risk("Automate c r e d i t scoring")
        assert result["risk_level"] == "HIGH"
        assert "credit" in result["matched_categories"]

    def test_normal_text_not_affected(self) -> None:
        """Normal text without spaced evasion should not produce false positives."""
        result = classify_annex_iii_risk("What is the weather today?")
        assert result["risk_level"] == "MEDIUM"
        assert result["matched_categories"] == []


# =====================================================================
# Art. 13 / Art. 50 — Transparency field injection in pipeline
# =====================================================================
class TestPipelineTransparencyInjection:
    """Art. 13/50: eu_compliance_pipeline must inject disclosure fields."""

    def setup_method(self) -> None:
        HumanReviewQueue.clear_for_testing()
        SystemHaltController.clear_for_testing()
        ThirdPartyNotificationService.clear_for_testing()

    def test_ai_disclosure_injected(self) -> None:
        """ai_disclosure must appear in every pipeline response."""

        @eu_compliance_pipeline(
            config=EUComplianceConfig(
                enabled=True,
                require_audit_for_high_risk=False,
            )
        )
        def fake_decide(**kwargs: object) -> dict:
            return {"output": "safe output", "trust_score": 0.95}

        result = fake_decide(prompt="What is the weather today?")
        assert result["ai_disclosure"] == AI_DISCLOSURE_TEXT

    def test_regulation_notice_injected(self) -> None:
        """regulation_notice must appear in every pipeline response."""

        @eu_compliance_pipeline(
            config=EUComplianceConfig(
                enabled=True,
                require_audit_for_high_risk=False,
            )
        )
        def fake_decide(**kwargs: object) -> dict:
            return {"output": "safe output", "trust_score": 0.95}

        result = fake_decide(prompt="What is the weather today?")
        assert result["regulation_notice"] == AI_REGULATION_NOTICE

    def test_existing_disclosure_not_overwritten(self) -> None:
        """If the inner function sets ai_disclosure, it should be kept."""

        @eu_compliance_pipeline(
            config=EUComplianceConfig(
                enabled=True,
                require_audit_for_high_risk=False,
            )
        )
        def fake_decide(**kwargs: object) -> dict:
            return {
                "output": "safe output",
                "trust_score": 0.95,
                "ai_disclosure": "Custom disclosure",
            }

        result = fake_decide(prompt="What is the weather today?")
        assert result["ai_disclosure"] == "Custom disclosure"

    def test_affected_parties_notice_for_high_risk(self) -> None:
        """High-risk decisions must auto-generate affected_parties_notice."""

        @eu_compliance_pipeline(
            config=EUComplianceConfig(
                enabled=True,
                require_audit_for_high_risk=False,
            )
        )
        def fake_decide(**kwargs: object) -> dict:
            return {"output": "hiring decision result", "trust_score": 0.95}

        result = fake_decide(prompt="AI hiring screening tool")
        assert result["affected_parties_notice"] is not None
        assert result["affected_parties_notice"]["risk_level"] == "HIGH"
        assert "affected_party_rights" in result["affected_parties_notice"]

    def test_no_affected_parties_notice_for_low_risk(self) -> None:
        """Non-high-risk decisions should not have affected_parties_notice."""

        @eu_compliance_pipeline(
            config=EUComplianceConfig(
                enabled=True,
                require_audit_for_high_risk=False,
            )
        )
        def fake_decide(**kwargs: object) -> dict:
            return {"output": "weather report", "trust_score": 0.95}

        result = fake_decide(prompt="What is the weather today?")
        assert result.get("affected_parties_notice") is None


# =====================================================================
# Art. 11 / Art. 15 — Change management validation
# =====================================================================
class TestValidateChangeManagement:
    """Art. 11/15: Change management records must be well-formed."""

    def test_valid_change_log(self) -> None:
        """A well-formed change log should pass validation."""
        log = [
            {
                "date": "2026-03-07",
                "author": "dev-team",
                "description": "Updated safety gate patterns",
                "component": "core/eu_ai_act_compliance_module",
            },
        ]
        result = validate_change_management(change_log=log)
        assert result["valid"] is True
        assert result["entries_count"] == 1
        assert result["issues"] == []

    def test_empty_change_log(self) -> None:
        """An empty change log should report an issue."""
        result = validate_change_management(change_log=[])
        assert result["valid"] is False
        assert any("empty" in issue for issue in result["issues"])

    def test_missing_required_fields(self) -> None:
        """Entries missing required fields should be flagged."""
        log = [
            {"date": "2026-03-07", "author": "dev-team"},  # missing description, component
        ]
        result = validate_change_management(change_log=log)
        assert result["valid"] is False
        assert any("description" in issue for issue in result["issues"])
        assert any("component" in issue for issue in result["issues"])

    def test_file_based_loading(self) -> None:
        """When no explicit log is provided, loads from change_log.json."""
        with tempfile.TemporaryDirectory() as tmp:
            eu_dir = os.path.join(tmp, "docs", "eu_ai_act")
            os.makedirs(eu_dir)
            log = [
                {
                    "date": "2026-03-07",
                    "author": "team",
                    "description": "test",
                    "component": "test",
                },
            ]
            with open(os.path.join(eu_dir, "change_log.json"), "w") as f:
                json.dump(log, f)

            result = validate_change_management(repo_root=tmp)
            assert result["valid"] is True
            assert result["entries_count"] == 1

    def test_missing_file(self) -> None:
        """Missing change_log.json should report issue."""
        with tempfile.TemporaryDirectory() as tmp:
            result = validate_change_management(repo_root=tmp)
            assert result["valid"] is False
            assert any("not found" in issue for issue in result["issues"])

    def test_malformed_json(self) -> None:
        """Malformed JSON should report a read error."""
        with tempfile.TemporaryDirectory() as tmp:
            eu_dir = os.path.join(tmp, "docs", "eu_ai_act")
            os.makedirs(eu_dir)
            with open(os.path.join(eu_dir, "change_log.json"), "w") as f:
                f.write("not valid json {{{")

            result = validate_change_management(repo_root=tmp)
            assert result["valid"] is False
            assert any("read_error" in issue for issue in result["issues"])

    def test_non_list_json(self) -> None:
        """JSON that is not an array should report format error."""
        with tempfile.TemporaryDirectory() as tmp:
            eu_dir = os.path.join(tmp, "docs", "eu_ai_act")
            os.makedirs(eu_dir)
            with open(os.path.join(eu_dir, "change_log.json"), "w") as f:
                json.dump({"key": "value"}, f)

            result = validate_change_management(repo_root=tmp)
            assert result["valid"] is False
            assert any("format" in issue for issue in result["issues"])

    def test_article_reference(self) -> None:
        """Result should reference Art. 11 / Art. 15."""
        result = validate_change_management(change_log=[])
        assert "Art. 11" in result["eu_ai_act_article"]
        assert "Art. 15" in result["eu_ai_act_article"]


# =====================================================================
# Art. 10 / Art. 11 — Deployment readiness with change management
# =====================================================================
class TestDeploymentReadinessChangeManagement:
    """validate_deployment_readiness() should include change management check."""

    def test_includes_change_management_section(self) -> None:
        """Result should contain change_management key."""
        result = validate_deployment_readiness(repo_root="/nonexistent")
        assert "change_management" in result

    def test_change_management_valid_with_file(self) -> None:
        """With a valid change log, change_management.valid should be True."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create required dirs and change log
            eu_dir = os.path.join(tmp, "docs", "eu_ai_act")
            os.makedirs(eu_dir)
            log = [
                {
                    "date": "2026-03-07",
                    "author": "team",
                    "description": "test",
                    "component": "test",
                },
            ]
            with open(os.path.join(eu_dir, "change_log.json"), "w") as f:
                json.dump(log, f)

            result = validate_deployment_readiness(repo_root=tmp)
            assert result["change_management"]["valid"] is True

    def test_change_management_invalid_without_file(self) -> None:
        """Without change_log.json, change_management.valid should be False."""
        with tempfile.TemporaryDirectory() as tmp:
            result = validate_deployment_readiness(repo_root=tmp)
            assert result["change_management"]["valid"] is False
            assert any("change_management" in issue for issue in result["issues"])
