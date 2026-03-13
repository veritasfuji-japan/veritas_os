"""Tests for EU AI Act P3-1 through P3-4 improvements.

P3-1: Log retention period adjustment (GAP-13, Art. 12)
P3-2: At-rest encryption standardisation (GAP-12, Art. 12)
P3-3: Continuous risk monitoring process (GAP-15, Art. 9)
P3-4: Third-party notification mechanism (GAP-17, Art. 13)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from veritas_os.core.eu_ai_act_compliance_module import (
    DEFAULT_RETENTION_DAYS,
    HIGH_RISK_RETENTION_DAYS,
    MIN_STANDARD_RETENTION_DAYS,
    RISK_MONITORING_SCHEDULE,
    ThirdPartyNotificationService,
    assess_continuous_risk_monitoring,
    get_retention_config,
)
from veritas_os.logging.encryption import (
    decrypt,
    encrypt,
    generate_key,
    get_encryption_status,
    is_encryption_enabled,
)


# =====================================================================
# P3-1: Log retention period (GAP-13, Art. 12)
# =====================================================================
class TestLogRetention:
    """P3-1 — log retention meets EU AI Act Art. 12 requirements."""

    def test_default_retention_at_least_180_days(self) -> None:
        assert DEFAULT_RETENTION_DAYS >= 180

    def test_high_risk_retention_at_least_365_days(self) -> None:
        assert HIGH_RISK_RETENTION_DAYS >= 365

    def test_get_retention_config_low_risk(self) -> None:
        result = get_retention_config(risk_level="LOW")
        assert result["retention_days"] == DEFAULT_RETENTION_DAYS
        assert result["compliant"] is True
        assert result["risk_level"] == "LOW"

    def test_get_retention_config_high_risk(self) -> None:
        result = get_retention_config(risk_level="HIGH")
        assert result["retention_days"] == HIGH_RISK_RETENTION_DAYS
        assert result["minimum_required_days"] == 180
        assert result["compliant"] is True
        assert result["risk_level"] == "HIGH"

    def test_get_retention_config_medium_risk(self) -> None:
        result = get_retention_config(risk_level="MEDIUM")
        assert result["retention_days"] == DEFAULT_RETENTION_DAYS
        assert result["compliant"] is True

    def test_get_retention_config_empty_defaults_to_low(self) -> None:
        result = get_retention_config(risk_level="")
        assert result["retention_days"] == DEFAULT_RETENTION_DAYS
        assert result["compliant"] is True

    def test_governance_json_retention_days(self) -> None:
        """Verify governance.json reflects updated retention."""
        governance_path = (
            Path(__file__).resolve().parents[1] / "api" / "governance.json"
        )
        data = json.loads(governance_path.read_text(encoding="utf-8"))
        assert data["log_retention"]["retention_days"] >= 180
        assert data["log_retention"]["retention_days_high_risk"] >= 365


# =====================================================================
# P3-2: At-rest encryption (GAP-12, Art. 12)
# =====================================================================
class TestEncryption:
    """P3-2 — at-rest encryption utilities."""

    def test_generate_key_is_valid_base64(self) -> None:
        import base64

        key = generate_key()
        decoded = base64.urlsafe_b64decode(key)
        assert len(decoded) == 32

    def test_encryption_disabled_by_default(self) -> None:
        # Ensure env is not set
        old = os.environ.pop("VERITAS_ENCRYPTION_KEY", None)
        try:
            assert is_encryption_enabled() is False
        finally:
            if old is not None:
                os.environ["VERITAS_ENCRYPTION_KEY"] = old

    def test_encrypt_raises_without_key(self) -> None:
        """secure-by-default: encrypt raises EncryptionKeyMissing without key."""
        from veritas_os.logging.encryption import EncryptionKeyMissing

        old = os.environ.pop("VERITAS_ENCRYPTION_KEY", None)
        try:
            plaintext = '{"request_id": "test", "sha256": "abc123"}'
            with pytest.raises(EncryptionKeyMissing):
                encrypt(plaintext)
        finally:
            if old is not None:
                os.environ["VERITAS_ENCRYPTION_KEY"] = old

    def test_encrypt_produces_enc_prefix_with_key(self) -> None:
        key = generate_key()
        old = os.environ.get("VERITAS_ENCRYPTION_KEY")
        os.environ["VERITAS_ENCRYPTION_KEY"] = key
        try:
            plaintext = '{"test": "data"}'
            result = encrypt(plaintext)
            assert result.startswith("ENC:")
            assert result != plaintext
        finally:
            if old is not None:
                os.environ["VERITAS_ENCRYPTION_KEY"] = old
            else:
                os.environ.pop("VERITAS_ENCRYPTION_KEY", None)

    def test_encryption_status_disabled(self) -> None:
        old = os.environ.pop("VERITAS_ENCRYPTION_KEY", None)
        try:
            status = get_encryption_status()
            assert status["encryption_enabled"] is False
            assert status["algorithm"] == "none"
        finally:
            if old is not None:
                os.environ["VERITAS_ENCRYPTION_KEY"] = old

    def test_encryption_status_enabled(self) -> None:
        key = generate_key()
        old = os.environ.get("VERITAS_ENCRYPTION_KEY")
        os.environ["VERITAS_ENCRYPTION_KEY"] = key
        try:
            status = get_encryption_status()
            assert status["encryption_enabled"] is True
            assert status["algorithm"] in ("AES-256-GCM", "HMAC-SHA256 CTR-mode")
        finally:
            if old is not None:
                os.environ["VERITAS_ENCRYPTION_KEY"] = old
            else:
                os.environ.pop("VERITAS_ENCRYPTION_KEY", None)

    def test_invalid_base64_key_is_rejected(self) -> None:
        """Invalid Base64 should disable encryption and raise EncryptionKeyMissing."""
        from veritas_os.logging.encryption import EncryptionKeyMissing

        old = os.environ.get("VERITAS_ENCRYPTION_KEY")
        os.environ["VERITAS_ENCRYPTION_KEY"] = "%%%not-base64%%%"
        try:
            assert is_encryption_enabled() is False
            plaintext = '{"security": "check"}'
            with pytest.raises(EncryptionKeyMissing):
                encrypt(plaintext)
        finally:
            if old is not None:
                os.environ["VERITAS_ENCRYPTION_KEY"] = old
            else:
                os.environ.pop("VERITAS_ENCRYPTION_KEY", None)

    def test_encrypt_raises_for_non_string_payload(self) -> None:
        """Unexpected payload type should fail closed with TypeError."""
        key = generate_key()
        old = os.environ.get("VERITAS_ENCRYPTION_KEY")
        os.environ["VERITAS_ENCRYPTION_KEY"] = key
        try:
            with pytest.raises(TypeError, match="requires a str"):
                encrypt(12345)
        finally:
            if old is not None:
                os.environ["VERITAS_ENCRYPTION_KEY"] = old
            else:
                os.environ.pop("VERITAS_ENCRYPTION_KEY", None)

    def test_decrypt_returns_input_for_invalid_base64_ciphertext(self) -> None:
        """Malformed ciphertext should safely return the original input."""
        key = generate_key()
        old = os.environ.get("VERITAS_ENCRYPTION_KEY")
        os.environ["VERITAS_ENCRYPTION_KEY"] = key
        try:
            malformed = "ENC:###"
            assert decrypt(malformed) == malformed
        finally:
            if old is not None:
                os.environ["VERITAS_ENCRYPTION_KEY"] = old
            else:
                os.environ.pop("VERITAS_ENCRYPTION_KEY", None)


# =====================================================================
# P3-3: Continuous risk monitoring (GAP-15, Art. 9)
# =====================================================================
class TestContinuousRiskMonitoring:
    """P3-3 — continuous risk monitoring schedule and assessment."""

    def test_schedule_has_all_frequencies(self) -> None:
        expected = {"daily", "weekly", "monthly", "quarterly", "annually"}
        assert set(RISK_MONITORING_SCHEDULE.keys()) == expected

    def test_each_frequency_has_activities(self) -> None:
        for freq, activities in RISK_MONITORING_SCHEDULE.items():
            assert len(activities) > 0, f"{freq} has no activities"

    def test_assess_no_activities_returns_zero_score(self) -> None:
        result = assess_continuous_risk_monitoring()
        assert result["overall_score"] == 0.0
        assert result["compliant"] is False
        assert result["completed_activities"] == 0

    def test_assess_full_completion(self) -> None:
        completed = {
            freq: list(acts)
            for freq, acts in RISK_MONITORING_SCHEDULE.items()
        }
        result = assess_continuous_risk_monitoring(completed_activities=completed)
        assert result["overall_score"] == 1.0
        assert result["compliant"] is True
        assert result["completed_activities"] == result["total_activities"]

    def test_assess_partial_completion(self) -> None:
        completed = {
            "daily": ["trust_log_integrity_check", "anomaly_detection_review"],
            "weekly": ["accuracy_drift_analysis"],
        }
        result = assess_continuous_risk_monitoring(completed_activities=completed)
        assert 0.0 < result["overall_score"] < 1.0
        assert result["completed_activities"] == 3
        assert result["eu_ai_act_article"] == "Art. 9"

    def test_assess_compliance_threshold(self) -> None:
        """70% completion is the compliance threshold."""
        import math

        total = sum(len(v) for v in RISK_MONITORING_SCHEDULE.values())
        threshold_count = math.ceil(total * 0.7)
        # Build enough activities to cross threshold
        completed: dict[str, list[str]] = {}
        count = 0
        for freq, acts in RISK_MONITORING_SCHEDULE.items():
            freq_done = []
            for act in acts:
                if count >= threshold_count:
                    break
                freq_done.append(act)
                count += 1
            if freq_done:
                completed[freq] = freq_done
            if count >= threshold_count:
                break
        result = assess_continuous_risk_monitoring(completed_activities=completed)
        assert result["compliant"] is True

    def test_monitoring_doc_exists(self) -> None:
        doc_path = (
            Path(__file__).resolve().parents[2]
            / "docs"
            / "eu_ai_act"
            / "continuous_risk_monitoring.md"
        )
        assert doc_path.exists(), f"Missing: {doc_path}"

    def test_monitoring_doc_contains_schedule(self) -> None:
        doc_path = (
            Path(__file__).resolve().parents[2]
            / "docs"
            / "eu_ai_act"
            / "continuous_risk_monitoring.md"
        )
        content = doc_path.read_text(encoding="utf-8")
        assert "日次" in content or "daily" in content.lower()
        assert "週次" in content or "weekly" in content.lower()
        assert "月次" in content or "monthly" in content.lower()
        assert "四半期" in content or "quarterly" in content.lower()
        assert "年次" in content or "annual" in content.lower()

    def test_monitoring_doc_references_key_activities(self) -> None:
        doc_path = (
            Path(__file__).resolve().parents[2]
            / "docs"
            / "eu_ai_act"
            / "continuous_risk_monitoring.md"
        )
        content = doc_path.read_text(encoding="utf-8")
        # Verify key activities from RISK_MONITORING_SCHEDULE are documented
        assert "TrustLog" in content
        assert "doctor.py" in content or "精度" in content
        assert "バイアス" in content or "bias" in content.lower()
        assert "Art. 9" in content or "第9条" in content


# =====================================================================
# P3-4: Third-party notification (GAP-17, Art. 13)
# =====================================================================
class TestThirdPartyNotification:
    """P3-4 — third-party notification for high-risk decisions."""

    def setup_method(self) -> None:
        ThirdPartyNotificationService.clear_for_testing()

    def test_build_notification_high_risk(self) -> None:
        result = ThirdPartyNotificationService.build_notification(
            decision_id="test-001",
            risk_level="HIGH",
            matched_categories=["hiring", "employment"],
            decision_summary="Candidate screening decision",
        )
        assert result["decision_id"] == "test-001"
        assert result["risk_level"] == "HIGH"
        assert result["status"] == "pending_delivery"
        assert result["affected_party_rights"]["right_to_explanation"] is True
        assert result["affected_party_rights"]["right_to_contest"] is True
        assert result["affected_party_rights"]["right_to_human_review"] is True
        assert result["ai_disclosure"] != ""

    def test_build_notification_non_high_risk_returns_empty(self) -> None:
        result = ThirdPartyNotificationService.build_notification(
            decision_id="test-002",
            risk_level="LOW",
            matched_categories=[],
        )
        assert result == {}

    def test_build_notification_medium_risk_returns_empty(self) -> None:
        result = ThirdPartyNotificationService.build_notification(
            decision_id="test-003",
            risk_level="MEDIUM",
            matched_categories=["education"],
        )
        assert result == {}

    def test_get_notifications_filters_by_decision_id(self) -> None:
        ThirdPartyNotificationService.build_notification(
            decision_id="d-001",
            risk_level="HIGH",
            matched_categories=["hiring"],
        )
        ThirdPartyNotificationService.build_notification(
            decision_id="d-002",
            risk_level="HIGH",
            matched_categories=["healthcare"],
        )
        results = ThirdPartyNotificationService.get_notifications(decision_id="d-001")
        assert len(results) == 1
        assert results[0]["decision_id"] == "d-001"

    def test_get_all_notifications(self) -> None:
        ThirdPartyNotificationService.build_notification(
            decision_id="d-010",
            risk_level="HIGH",
            matched_categories=["credit"],
        )
        ThirdPartyNotificationService.build_notification(
            decision_id="d-011",
            risk_level="HIGH",
            matched_categories=["insurance"],
        )
        results = ThirdPartyNotificationService.get_notifications()
        assert len(results) == 2

    def test_notification_includes_regulation_notice(self) -> None:
        result = ThirdPartyNotificationService.build_notification(
            decision_id="test-reg",
            risk_level="HIGH",
            matched_categories=["law enforcement"],
        )
        assert "EU AI Act" in result["regulation_notice"]

    def test_clear_for_testing(self) -> None:
        ThirdPartyNotificationService.build_notification(
            decision_id="x",
            risk_level="HIGH",
            matched_categories=["hiring"],
        )
        assert len(ThirdPartyNotificationService.get_notifications()) == 1
        ThirdPartyNotificationService.clear_for_testing()
        assert len(ThirdPartyNotificationService.get_notifications()) == 0


class TestDecideResponseAffectedPartiesNotice:
    """P3-4 — DecideResponse includes affected_parties_notice field."""

    def test_affected_parties_notice_default_none(self) -> None:
        from veritas_os.api.schemas import DecideResponse

        resp = DecideResponse()
        assert resp.affected_parties_notice is None

    def test_affected_parties_notice_accepts_dict(self) -> None:
        from veritas_os.api.schemas import DecideResponse

        notice = {
            "notification_id": "n-001",
            "decision_id": "d-001",
            "risk_level": "HIGH",
            "affected_party_rights": {
                "right_to_explanation": True,
                "right_to_contest": True,
            },
        }
        resp = DecideResponse(affected_parties_notice=notice)
        assert resp.affected_parties_notice is not None
        assert resp.affected_parties_notice["risk_level"] == "HIGH"
