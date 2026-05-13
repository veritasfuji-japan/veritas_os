"""Tests for staged readiness report governance evidence coverage."""

from scripts.generate_staged_readiness_report import (
    GOVERNANCE_CHECKS,
    build_report,
    render_text_report,
)


def test_governance_checks_include_trustlog_production_posture() -> None:
    """GOVERNANCE_CHECKS should register the TrustLog posture evidence check."""
    labels = [item[0] for item in GOVERNANCE_CHECKS]
    assert "trustlog-production-posture" in labels


def test_trustlog_production_posture_check_metadata() -> None:
    """TrustLog posture check should be Tier 2 advisory with stable command."""
    check = next(
        item for item in GOVERNANCE_CHECKS
        if item[0] == "trustlog-production-posture"
    )
    assert check[1] == "Tier 2"
    assert check[2] == [
        "python",
        "-m",
        "scripts.security.check_trustlog_production_posture",
    ]
    assert check[3] is False


def test_build_report_coverage_mentions_trustlog_posture() -> None:
    """Coverage matrix should include TrustLog posture evidence wording."""
    report = build_report(
        ref="test",
        sha="abc",
        governance_results=[
            {
                "label": "trustlog-production-posture",
                "tier": "Tier 2",
                "blocking": False,
                "passed": True,
                "output": "",
            }
        ],
        compose_report=None,
        live_report=None,
    )
    assert any(
        "TrustLog production posture" in item
        for item in report["coverage_matrix"]["proven_in_ci"]
    )


def test_render_text_report_includes_trustlog_posture_label() -> None:
    """Text report should surface TrustLog posture check label."""
    report = build_report(
        ref="test",
        sha="abc",
        governance_results=[
            {
                "label": "trustlog-production-posture",
                "tier": "Tier 2",
                "blocking": False,
                "passed": True,
                "output": "",
            }
        ],
        compose_report=None,
        live_report=None,
    )

    text = render_text_report(report)
    assert "trustlog-production-posture" in text
