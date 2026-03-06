"""Tests for EU AI Act P1-1 through P1-6 improvements.

P1-1: Article 5 multi-layer prohibited-practice detection
P1-3: Human review queue, webhook, SLA, override prevention
P1-4: AI disclosure fields on DecideResponse
P1-6: Fail-close, bench-mode PII guard, audit-readiness guard
"""
from __future__ import annotations

import pytest

from veritas_os.core.eu_ai_act_compliance_module import (
    AI_DISCLOSURE_TEXT,
    AI_REGULATION_NOTICE,
    EUAIActSafetyGateLayer4,
    EUComplianceConfig,
    HumanReviewQueue,
    classify_annex_iii_risk,
    eu_compliance_pipeline,
    validate_audit_readiness_for_high_risk,
    validate_bench_mode_pii_safety,
)


# =====================================================================
# P1-1: Article 5 multi-language and normalised detection
# =====================================================================
class TestArticle5MultiLangDetection:
    """P1-1 — multi-language, normalisation, input inspection."""

    def test_english_base_patterns_detected(self) -> None:
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("This uses subliminal techniques")
        assert result["passed"] is False
        assert "subliminal" in result["violations"]

    def test_japanese_patterns_detected(self) -> None:
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("サブリミナル手法を使用")
        assert result["passed"] is False

    def test_hyphen_evasion_normalised(self) -> None:
        """P1-1: 'mani-pulate' should still be detected after normalisation."""
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("We will mani-pulate the user")
        assert result["passed"] is False

    def test_zero_width_evasion_normalised(self) -> None:
        """Zero-width characters inserted between letters must not bypass."""
        gate = EUAIActSafetyGateLayer4()
        text = "manip\u200bulat\u200be the user"
        result = gate.validate_article_5(text)
        assert result["passed"] is False

    def test_social_scoring_jp_detected(self) -> None:
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("社会的スコアリングを実施")
        assert result["passed"] is False

    def test_new_patterns_biometric_categorisation(self) -> None:
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("using biometric categorisation of people")
        assert result["passed"] is False

    def test_new_patterns_emotion_recognition(self) -> None:
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("apply emotion recognition at the workplace")
        assert result["passed"] is False

    def test_clean_text_passes(self) -> None:
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("This is a normal business decision")
        assert result["passed"] is True
        assert result["violations"] == []

    def test_input_inspection(self) -> None:
        """P1-1: Input prompts must also be inspected."""
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5_input("Please manipulate the audience")
        assert result["passed"] is False
        assert result["scope"] == "input"

    def test_input_inspection_clean(self) -> None:
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5_input("Help me draft a business plan")
        assert result["passed"] is True

    def test_external_classifier_integration(self) -> None:
        """P1-1: External classifier can add violations."""
        def mock_classifier(text: str) -> dict:
            return {"violations": ["custom_prohibited_pattern"], "confidence": 0.95}

        gate = EUAIActSafetyGateLayer4(external_classifier=mock_classifier)
        result = gate.validate_article_5("This is normal text")
        assert result["passed"] is False
        assert "custom_prohibited_pattern" in result["violations"]
        assert result["external_classifier"]["confidence"] == 0.95

    def test_external_classifier_error_handled(self) -> None:
        """External classifier errors must not crash the gate."""
        def failing_classifier(text: str) -> dict:
            raise RuntimeError("classifier unavailable")

        gate = EUAIActSafetyGateLayer4(external_classifier=failing_classifier)
        result = gate.validate_article_5("Normal text")
        assert result["passed"] is True
        assert result.get("external_classifier_error") is True

    def test_external_classifier_unhandled_error_propagates(self) -> None:
        """Truly unexpected errors (e.g. KeyboardInterrupt) should propagate."""
        def bad_classifier(text: str) -> dict:
            raise KeyboardInterrupt

        gate = EUAIActSafetyGateLayer4(external_classifier=bad_classifier)
        import pytest as _pt
        with _pt.raises(KeyboardInterrupt):
            gate.validate_article_5("Normal text")

    def test_pipeline_blocks_prohibited_input(self) -> None:
        """P1-1: Pipeline decorator blocks inputs with prohibited patterns."""

        @eu_compliance_pipeline(config=EUComplianceConfig(
            enabled=True,
            require_audit_for_high_risk=False,
        ))
        def fake_decide(**kwargs: object) -> dict:
            return {"output": "ok", "trust_score": 0.9}

        result = fake_decide(prompt="We need to manipulate users")
        assert result["status"] == "BLOCKED"
        assert result["blocked_by"] == "Art.5_input_inspection"
        assert result["decision_status"] == "rejected"


# =====================================================================
# P1-3: Human Review Queue
# =====================================================================
class TestHumanReviewQueue:
    """P1-3 — queue, SLA, review workflow."""

    def setup_method(self) -> None:
        HumanReviewQueue.clear_for_testing()

    def test_enqueue_creates_entry(self) -> None:
        entry = HumanReviewQueue.enqueue(
            decision_payload={"request_id": "r1"},
            reason="low_trust",
        )
        assert entry["status"] == "pending"
        assert entry["entry_id"]
        assert entry["sla_deadline"]
        assert entry["reason"] == "low_trust"

    def test_pending_entries(self) -> None:
        HumanReviewQueue.enqueue(decision_payload={"request_id": "r1"}, reason="a")
        HumanReviewQueue.enqueue(decision_payload={"request_id": "r2"}, reason="b")
        pending = HumanReviewQueue.pending_entries()
        assert len(pending) == 2

    def test_review_approve(self) -> None:
        entry = HumanReviewQueue.enqueue(
            decision_payload={"request_id": "r1"},
            reason="test",
        )
        result = HumanReviewQueue.review(
            entry["entry_id"],
            approved=True,
            reviewer="admin@example.com",
        )
        assert result is not None
        assert result["status"] == "approved"
        assert result["reviewer"] == "admin@example.com"

    def test_review_reject(self) -> None:
        entry = HumanReviewQueue.enqueue(
            decision_payload={"request_id": "r1"},
            reason="test",
        )
        result = HumanReviewQueue.review(
            entry["entry_id"],
            approved=False,
            reviewer="admin@example.com",
            comment="Not appropriate",
        )
        assert result is not None
        assert result["status"] == "rejected"
        assert result["comment"] == "Not appropriate"

    def test_review_nonexistent_returns_none(self) -> None:
        result = HumanReviewQueue.review(
            "nonexistent",
            approved=True,
            reviewer="admin@example.com",
        )
        assert result is None

    def test_get_entry(self) -> None:
        entry = HumanReviewQueue.enqueue(
            decision_payload={"request_id": "r1"},
            reason="test",
        )
        fetched = HumanReviewQueue.get_entry(entry["entry_id"])
        assert fetched is not None
        assert fetched["entry_id"] == entry["entry_id"]

    def test_get_entry_nonexistent(self) -> None:
        assert HumanReviewQueue.get_entry("nonexistent") is None

    def test_double_review_not_allowed(self) -> None:
        entry = HumanReviewQueue.enqueue(
            decision_payload={"request_id": "r1"},
            reason="test",
        )
        HumanReviewQueue.review(
            entry["entry_id"],
            approved=True,
            reviewer="admin@example.com",
        )
        # Second review of same entry should return None (already reviewed)
        result = HumanReviewQueue.review(
            entry["entry_id"],
            approved=False,
            reviewer="other@example.com",
        )
        assert result is None


# =====================================================================
# P1-4: AI Disclosure fields
# =====================================================================
class TestAIDisclosure:
    """P1-4 — Art. 50 mandatory disclosure on DecideResponse."""

    def test_disclosure_constants_defined(self) -> None:
        assert "AI system" in AI_DISCLOSURE_TEXT
        assert "VERITAS OS" in AI_DISCLOSURE_TEXT
        assert "EU AI Act" in AI_REGULATION_NOTICE

    def test_decide_response_has_disclosure_fields(self) -> None:
        from veritas_os.api.schemas import DecideResponse

        resp = DecideResponse()
        assert resp.ai_disclosure == "This response was generated by an AI system (VERITAS OS)."
        assert resp.regulation_notice == "Subject to EU AI Act Regulation (EU) 2024/1689."

    def test_disclosure_included_in_serialization(self) -> None:
        from veritas_os.api.schemas import DecideResponse

        resp = DecideResponse()
        data = resp.model_dump()
        assert "ai_disclosure" in data
        assert "regulation_notice" in data
        assert "AI system" in data["ai_disclosure"]


# =====================================================================
# P1-6: Security remediation
# =====================================================================
class TestFailClose:
    """P1-6 — fail-close on human_review."""

    def setup_method(self) -> None:
        HumanReviewQueue.clear_for_testing()

    def test_fail_close_blocks_decision(self) -> None:
        from veritas_os.core.eu_ai_act_compliance_module import apply_human_oversight_hook

        payload: dict = {"request_id": "test"}
        result = apply_human_oversight_hook(
            trust_score=0.3,
            risk_level="HIGH",
            response_payload=payload,
            config=EUComplianceConfig(fail_close=True),
        )
        assert result["status"] == "PENDING_HUMAN_REVIEW"
        assert result["decision_blocked"] is True
        assert result["fail_close"] is True
        assert result["decision_status"] == "hold"
        assert "human_review_entry_id" in result

    def test_fail_close_disabled(self) -> None:
        from veritas_os.core.eu_ai_act_compliance_module import apply_human_oversight_hook

        payload: dict = {"request_id": "test"}
        result = apply_human_oversight_hook(
            trust_score=0.3,
            risk_level="HIGH",
            response_payload=payload,
            config=EUComplianceConfig(fail_close=False),
        )
        assert result["status"] == "PENDING_HUMAN_REVIEW"
        assert result.get("decision_blocked") is None


class TestBenchModePIISafeguard:
    """P1-6 — bench_mode must not disable PII checks."""

    def test_bench_mode_blocked_by_default(self) -> None:
        result = validate_bench_mode_pii_safety(mode="bench")
        assert result["allowed"] is False

    def test_bench_mode_allowed_with_override(self) -> None:
        result = validate_bench_mode_pii_safety(
            mode="bench",
            config=EUComplianceConfig(bench_mode_pii_override=True),
        )
        assert result["allowed"] is True

    def test_normal_mode_unaffected(self) -> None:
        result = validate_bench_mode_pii_safety(mode="normal")
        assert result["allowed"] is True


class TestAuditReadinessGuard:
    """P1-6 — high-risk usage requires audit readiness."""

    def test_high_risk_rejected_low_retention(self) -> None:
        result = validate_audit_readiness_for_high_risk(
            risk_level="HIGH",
            log_retention_days=90,
        )
        assert result["allowed"] is False
        assert "log_retention_days" in result["reason"]

    def test_high_risk_rejected_no_notification(self) -> None:
        result = validate_audit_readiness_for_high_risk(
            risk_level="HIGH",
            log_retention_days=365,
            notification_flow_ready=False,
        )
        assert result["allowed"] is False
        assert "notification flow" in result["reason"]

    def test_high_risk_allowed_when_ready(self) -> None:
        result = validate_audit_readiness_for_high_risk(
            risk_level="HIGH",
            log_retention_days=365,
            notification_flow_ready=True,
        )
        assert result["allowed"] is True

    def test_non_high_risk_always_allowed(self) -> None:
        result = validate_audit_readiness_for_high_risk(
            risk_level="MEDIUM",
            log_retention_days=30,
        )
        assert result["allowed"] is True

    def test_guard_disabled(self) -> None:
        result = validate_audit_readiness_for_high_risk(
            risk_level="HIGH",
            log_retention_days=30,
            config=EUComplianceConfig(require_audit_for_high_risk=False),
        )
        assert result["allowed"] is True


class TestDefaultRiskScore:
    """P1-6 — GAP-06: default score raised from 0.2 to 0.4."""

    def test_unmatched_prompt_returns_medium(self) -> None:
        result = classify_annex_iii_risk("General business planning query")
        assert result["risk_level"] == "MEDIUM"
        assert result["risk_score"] == 0.4

    def test_matched_prompt_still_returns_high(self) -> None:
        result = classify_annex_iii_risk("Use AI for hiring decisions")
        assert result["risk_level"] == "HIGH"
        assert result["risk_score"] >= 0.85


class TestPipelineAuditGuard:
    """P1-6 — pipeline decorator blocks high-risk if audit not ready."""

    def test_pipeline_blocks_high_risk_without_audit(self) -> None:
        @eu_compliance_pipeline(config=EUComplianceConfig(
            enabled=True,
            require_audit_for_high_risk=True,
        ))
        def fake_decide(**kwargs: object) -> dict:
            return {"output": "ok", "trust_score": 0.9}

        result = fake_decide(prompt="AI healthcare decision support")
        assert result["status"] == "BLOCKED"
        assert result["blocked_by"] == "Art.9_audit_readiness"

    def test_pipeline_allows_non_high_risk(self) -> None:
        @eu_compliance_pipeline(config=EUComplianceConfig(
            enabled=True,
            require_audit_for_high_risk=True,
        ))
        def fake_decide(**kwargs: object) -> dict:
            return {"output": "ok", "trust_score": 0.9}

        result = fake_decide(prompt="Help me plan a team meeting")
        assert result.get("status") != "BLOCKED"
