"""Tests for staged readiness report governance evidence coverage."""

from scripts.generate_staged_readiness_report import (
    CHECK_ENV_OVERRIDES,
    GOVERNANCE_CHECKS,
    build_report,
    run_check,
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


def test_build_report_schema_version_is_2_1() -> None:
    """Staged readiness schema version should remain pinned to 2.1."""
    report = build_report(
        ref="test",
        sha="abc",
        governance_results=[],
        compose_report=None,
        live_report=None,
    )
    assert report["schema_version"] == "2.1"


def test_trustlog_posture_check_forces_enforcement_override() -> None:
    """TrustLog check should always set production posture enforcement."""
    assert CHECK_ENV_OVERRIDES["trustlog-production-posture"] == {
        "VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE": "1",
    }


def test_run_check_passes_env_overrides(monkeypatch) -> None:
    """run_check should pass merged env when overrides are provided."""
    captured: dict[str, object] = {}

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(command, capture_output, text, timeout, env=None):
        captured["command"] = command
        captured["env"] = env
        return Result()

    monkeypatch.setattr(
        "scripts.generate_staged_readiness_report.subprocess.run",
        fake_run,
    )

    passed, output = run_check(
        "trustlog-production-posture",
        ["python", "-m", "scripts.security.check_trustlog_production_posture"],
        env_overrides={"VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE": "1"},
    )

    assert passed is True
    assert output == "ok"
    assert captured["command"] == [
        "python",
        "-m",
        "scripts.security.check_trustlog_production_posture",
    ]
    assert isinstance(captured["env"], dict)
    assert captured["env"]["VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE"] == "1"


def test_run_check_without_env_overrides_uses_default_env(monkeypatch) -> None:
    """run_check should preserve ambient subprocess behavior by default."""
    captured: dict[str, object] = {}

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(command, capture_output, text, timeout, env=None):
        captured["command"] = command
        captured["env"] = env
        return Result()

    monkeypatch.setattr(
        "scripts.generate_staged_readiness_report.subprocess.run",
        fake_run,
    )

    passed, output = run_check("dummy", ["python", "--version"])

    assert passed is True
    assert output == "ok"
    assert captured["command"] == ["python", "--version"]
    assert captured["env"] is None
