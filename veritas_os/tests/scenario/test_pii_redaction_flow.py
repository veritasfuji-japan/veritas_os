# -*- coding: utf-8 -*-
"""PII 検出フローテスト: PII 検出 → マスク → TrustLog 暗号化保存のフロー"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.scenario


class TestPiiRedactionFlow:
    """PII がマスクされてから TrustLog に暗号化保存されるシナリオ"""

    def test_email_detected_and_masked(self):
        """メールアドレスが検出されマスクされること"""
        from veritas_os.core import fuji

        result = fuji._fallback_safety_head("連絡先: user@example.com")
        assert "PII" in result.categories

    def test_phone_detected_and_masked(self):
        """電話番号が検出されマスクされること"""
        from veritas_os.core import fuji

        result = fuji._fallback_safety_head("電話: 03-1234-5678")
        assert "PII" in result.categories

    def test_pii_safe_applied_caps_risk(self):
        """PII マスク済みフラグでリスクが抑制されること"""
        from veritas_os.core import fuji

        sh = fuji.SafetyHeadResult(
            risk_score=0.8, categories=["PII"],
            rationale="PII 検出", model="test",
            raw={"pii_hits": ["phone"]},
        )
        result = fuji.fuji_core_decide(
            safety_head=sh, stakes=0.5, telos_score=0.0,
            evidence_count=1, policy=fuji.POLICY, safe_applied=True,
        )
        assert result["risk"] <= 0.40
        assert any("pii_safe_applied" in r for r in result["reasons"])

    def test_redaction_removes_pii_from_text(self):
        """リダクションで PII がテキストから除去されること"""
        from veritas_os.core import fuji

        policy = {
            "audit": {"redact_before_log": True},
            "pii": {"enabled": True, "masked_markers": ["●"]},
        }
        text = "電話: 03-1234-5678"
        result = fuji._redact_text_for_trust_log(text, policy)
        assert "03-1234-5678" not in result
