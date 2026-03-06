from __future__ import annotations

from veritas_os.core.eu_ai_act_compliance_module import (
    EUComplianceConfig,
    build_tamper_evident_trustlog_package,
    classify_annex_iii_risk,
    eu_compliance_pipeline,
)


def test_classify_annex_iii_risk_high() -> None:
    result = classify_annex_iii_risk("Use AI for hiring and credit screening")
    assert result["risk_level"] == "HIGH"
    assert "hiring" in result["matched_categories"]


def test_trustlog_package_contains_hash_chain() -> None:
    package = build_tamper_evident_trustlog_package(
        system_state={"model": "v1", "stage": "decide"},
        uncertainty_score=0.31,
        evidence_sources=["doc://policy", "doc://audit"],
        safety_gate_log={"passed": True},
        previous_hash="abc123",
    )
    assert package["sha256_prev"] == "abc123"
    assert isinstance(package["sha256"], str)
    assert len(package["sha256"]) == 64


def test_decorator_applies_human_review_and_role_injection() -> None:
    debate_roles = []

    @eu_compliance_pipeline(config=EUComplianceConfig(enabled=True, trust_score_threshold=0.8, require_audit_for_high_risk=False))
    def fake_decide(**kwargs: object) -> dict:
        assert kwargs.get("eu_risk_assessment") is not None
        return {"output": "normal output", "trust_score": 0.4}

    result = fake_decide(
        prompt="AI medical triage support",
        debate_roles=debate_roles,
    )

    assert any(role.get("role") == "fundamental_rights_officer" for role in debate_roles)
    assert result["status"] == "PENDING_HUMAN_REVIEW"
    assert result["eu_safety_gate"]["passed"] is True
