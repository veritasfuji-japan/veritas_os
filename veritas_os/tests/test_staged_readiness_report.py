"""Tests for staged readiness report governance evidence coverage."""

from scripts.generate_staged_readiness_report import (
    CHECK_ENV_OVERRIDES,
    GOVERNANCE_CHECKS,
    build_report,
    load_json_report,
    run_check,
    render_text_report,
)


def _sample_governance_results() -> list[dict]:
    """Return representative blocking/advisory governance check outcomes."""
    return [
        {
            "label": "runtime-pickle-ban",
            "tier": "Tier 1",
            "blocking": True,
            "passed": True,
            "output": "",
        },
        {
            "label": "trustlog-production-posture",
            "tier": "Tier 2",
            "blocking": False,
            "passed": False,
            "output": "TrustLog production posture check failed.",
        },
    ]




def _passing_blocking_governance_results() -> list[dict]:
    """Return minimal passing blocking governance checks for semantics tests."""
    return [
        {
            "label": "runtime-pickle-ban",
            "tier": "Tier 1",
            "blocking": True,
            "passed": True,
            "output": "",
        }
    ]

def _sample_report() -> dict:
    """Return a representative staged readiness report payload."""
    return build_report(
        ref="v-test",
        sha="abc123",
        governance_results=_sample_governance_results(),
        compose_report=None,
        live_report=None,
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


def test_build_report_surfaces_advisory_issues_in_overall_readiness() -> None:
    """Advisory failures should be summarized in overall readiness metadata."""
    report = build_report(
        ref="test",
        sha="abc",
        governance_results=[
            {
                "label": "trustlog-production-posture",
                "tier": "Tier 2",
                "blocking": False,
                "passed": False,
                "output": "TrustLog production posture check failed.",
            }
        ],
        compose_report=None,
        live_report=None,
    )
    assert report["overall_readiness"]["deployment_ready"] is True
    assert report["overall_readiness"]["advisory_issues"] is True
    assert report["overall_readiness"]["advisory_issue_count"] == 1
    assert report["governance"]["advisory_failures"] == 1
    assert report["governance"]["advisory_failure_labels"] == [
        "trustlog-production-posture"
    ]


def test_build_report_marks_no_advisory_issues_when_none() -> None:
    """Advisory issue summary should be empty when no advisory checks fail."""
    report = build_report(
        ref="test",
        sha="abc",
        governance_results=[],
        compose_report=None,
        live_report=None,
    )
    assert report["overall_readiness"]["advisory_issues"] is False
    assert report["overall_readiness"]["advisory_issue_count"] == 0


def test_render_text_report_surfaces_advisory_issue_summary() -> None:
    """Text report should surface advisory summary and non-blocking note."""
    report = build_report(
        ref="test",
        sha="abc",
        governance_results=[
            {
                "label": "trustlog-production-posture",
                "tier": "Tier 2",
                "blocking": False,
                "passed": False,
                "output": "TrustLog production posture check failed.",
            }
        ],
        compose_report=None,
        live_report=None,
    )
    text = render_text_report(report)
    assert "Advisory Issues" in text
    assert "warning" in text
    assert "trustlog-production-posture" in text
    assert "advisory failures are non-blocking" in text.lower()


def test_blocking_failure_still_blocks_deployment_ready() -> None:
    """Blocking failures must still determine deployment readiness outcome."""
    report = build_report(
        ref="test",
        sha="abc",
        governance_results=[
            {
                "label": "runtime-pickle-ban",
                "tier": "Tier 1",
                "blocking": True,
                "passed": False,
                "output": "failed",
            }
        ],
        compose_report=None,
        live_report=None,
    )
    assert report["overall_readiness"]["deployment_ready"] is False
    assert report["overall_readiness"]["governance_ready"] is False


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


def test_staged_readiness_report_top_level_schema_contract() -> None:
    """Top-level report keys and identity metadata should remain stable."""
    report = _sample_report()
    expected_keys = {
        "schema_version",
        "report_type",
        "generated_at",
        "release_ref",
        "release_sha",
        "overall_readiness",
        "governance",
        "compose_validation",
        "live_provider_validation",
        "coverage_matrix",
    }

    assert set(report.keys()) == expected_keys
    assert report["schema_version"] == "2.1"
    assert report["report_type"] == "staged_operational_readiness"
    assert report["release_ref"] == "v-test"
    assert report["release_sha"] == "abc123"


def test_staged_readiness_overall_readiness_schema_contract() -> None:
    """overall_readiness keys and value types should stay machine-readable."""
    overall = _sample_report()["overall_readiness"]
    expected_keys = {
        "governance_ready",
        "compose_validated",
        "live_provider_ok",
        "deployment_ready",
        "advisory_issues",
        "advisory_issue_count",
    }

    assert set(overall.keys()) == expected_keys
    assert isinstance(overall["governance_ready"], bool)
    assert isinstance(overall["compose_validated"], bool)
    assert isinstance(overall["live_provider_ok"], bool)
    assert isinstance(overall["deployment_ready"], bool)
    assert isinstance(overall["advisory_issues"], bool)
    assert isinstance(overall["advisory_issue_count"], int)


def test_staged_readiness_governance_schema_contract() -> None:
    """governance aggregate keys and value types should remain stable."""
    governance = _sample_report()["governance"]
    expected_keys = {
        "total_checks",
        "passed",
        "blocking_failures",
        "advisory_failures",
        "checks",
        "blocking_failure_labels",
        "advisory_failure_labels",
    }

    assert set(governance.keys()) == expected_keys
    assert isinstance(governance["total_checks"], int)
    assert isinstance(governance["passed"], int)
    assert isinstance(governance["blocking_failures"], int)
    assert isinstance(governance["advisory_failures"], int)
    assert isinstance(governance["checks"], list)
    assert isinstance(governance["blocking_failure_labels"], list)
    assert isinstance(governance["advisory_failure_labels"], list)


def test_staged_readiness_governance_check_item_schema_contract() -> None:
    """Each governance check item should expose the pinned check shape."""
    checks = _sample_report()["governance"]["checks"]
    expected_keys = {"label", "tier", "blocking", "passed", "output"}

    for item in checks:
        assert set(item.keys()) == expected_keys
        assert isinstance(item["label"], str)
        assert isinstance(item["tier"], str)
        assert isinstance(item["blocking"], bool)
        assert isinstance(item["passed"], bool)
        assert isinstance(item["output"], str)


def test_staged_readiness_coverage_matrix_schema_contract() -> None:
    """coverage_matrix keys and list[str] values should remain unchanged."""
    coverage = _sample_report()["coverage_matrix"]
    expected_keys = {
        "proven_in_ci",
        "proven_in_compose",
        "proven_with_secrets",
        "requires_environment",
    }

    assert set(coverage.keys()) == expected_keys
    for value in coverage.values():
        assert isinstance(value, list)
        assert all(isinstance(item, str) for item in value)
    assert any(
        "TrustLog production posture" in item
        for item in coverage["proven_in_ci"]
    )


def test_staged_readiness_preserves_compose_and_live_reports() -> None:
    """Compose/live reports should passthrough while preserving current semantics."""
    compose_report = {
        "summary": {"overall": "PASS"},
        "checks": [{"name": "compose", "result": "PASS", "detail": "ok"}],
    }
    live_report = {
        "summary": {"overall": "WARN"},
        "checks": [{"name": "live", "result": "WARN", "detail": "skipped"}],
    }

    report = build_report(
        ref="v-test",
        sha="abc123",
        governance_results=_sample_governance_results(),
        compose_report=compose_report,
        live_report=live_report,
    )

    assert report["compose_validation"] == compose_report
    assert report["live_provider_validation"] == live_report
    assert report["overall_readiness"]["compose_validated"] is True
    assert report["overall_readiness"]["live_provider_ok"] is True


def test_staged_readiness_compose_fail_blocks_deployment_ready() -> None:
    """Compose FAIL should set compose_validated false and block deployment."""
    report = build_report(
        ref="v-test",
        sha="abc123",
        governance_results=[
            {
                "label": "runtime-pickle-ban",
                "tier": "Tier 1",
                "blocking": True,
                "passed": True,
                "output": "",
            }
        ],
        compose_report={"summary": {"overall": "FAIL"}},
        live_report=None,
    )

    assert report["overall_readiness"]["compose_validated"] is False
    assert report["overall_readiness"]["deployment_ready"] is False


def test_staged_readiness_live_fail_does_not_flip_deployment_ready() -> None:
    """Live FAIL is informational and should not change deployment readiness."""
    report = build_report(
        ref="v-test",
        sha="abc123",
        governance_results=[
            {
                "label": "runtime-pickle-ban",
                "tier": "Tier 1",
                "blocking": True,
                "passed": True,
                "output": "",
            }
        ],
        compose_report=None,
        live_report={"summary": {"overall": "FAIL"}},
    )

    assert report["overall_readiness"]["live_provider_ok"] is False
    assert report["overall_readiness"]["deployment_ready"] is True


def test_staged_readiness_text_report_contract_contains_schema_and_advisory_summary() -> None:
    """Text report should include schema/advisory contract wording."""
    text = render_text_report(_sample_report())

    assert "Schema:     v2.1" in text
    assert "Advisory Issues:" in text
    assert "warning" in text
    assert "Note: advisory failures are non-blocking but require operator review." in text


def test_load_json_report_returns_parsed_report(tmp_path) -> None:
    """load_json_report should return parsed JSON when the report is valid."""
    path = tmp_path / "compose-report.json"
    path.write_text('{"summary": {"overall": "PASS"}}', encoding="utf-8")

    assert load_json_report(str(path)) == {"summary": {"overall": "PASS"}}


def test_load_json_report_none_path_returns_none() -> None:
    """load_json_report should return None when the report path is omitted."""
    assert load_json_report(None) is None


def test_load_json_report_missing_file_warns_and_returns_none(
    tmp_path,
    caplog,
) -> None:
    """Missing report artifacts should warn and return None."""
    with caplog.at_level("WARNING"):
        result = load_json_report(str(tmp_path / "missing.json"))

    assert result is None
    assert "Report file not found" in caplog.text


def test_load_json_report_invalid_json_warns_and_returns_none(
    tmp_path,
    caplog,
) -> None:
    """Invalid JSON reports should warn and return None."""
    path = tmp_path / "compose-report.json"
    path.write_text("{not-json", encoding="utf-8")

    with caplog.at_level("WARNING"):
        result = load_json_report(str(path))

    assert result is None
    assert "Failed to parse JSON" in caplog.text


def test_load_json_report_read_error_warns_and_returns_none(
    tmp_path,
    caplog,
    monkeypatch,
) -> None:
    """Read errors should warn and return None for report loading."""
    path = tmp_path / "compose-report.json"
    path.write_text("{}", encoding="utf-8")

    def raise_oserror(self, encoding=None):
        raise OSError("boom")

    monkeypatch.setattr(
        "scripts.generate_staged_readiness_report.Path.read_text",
        raise_oserror,
    )

    with caplog.at_level("WARNING"):
        result = load_json_report(str(path))

    assert result is None
    assert "Failed to read report file" in caplog.text


def test_absent_compose_report_is_not_failed_but_not_evidence_of_validation() -> None:
    """Absent compose reports are treated as not failed, not as proof of validation."""
    report = build_report(
        ref="test",
        sha="abc",
        governance_results=_passing_blocking_governance_results(),
        compose_report=None,
        live_report=None,
    )

    assert report["compose_validation"] is None
    assert report["overall_readiness"]["compose_validated"] is True
    assert report["overall_readiness"]["deployment_ready"] is True


def test_absent_live_report_is_not_failed_but_not_evidence_of_validation() -> None:
    """Absent live reports are treated as not failed, not as proof of provider health."""
    report = build_report(
        ref="test",
        sha="abc",
        governance_results=_passing_blocking_governance_results(),
        compose_report=None,
        live_report=None,
    )

    assert report["live_provider_validation"] is None
    assert report["overall_readiness"]["live_provider_ok"] is True
    assert report["overall_readiness"]["deployment_ready"] is True


def test_missing_compose_artifact_results_in_absent_compose_validation_semantics(
    tmp_path,
) -> None:
    """Missing compose artifacts should map to absent compose validation semantics."""
    compose_report = load_json_report(str(tmp_path / "missing-compose.json"))
    report = build_report(
        ref="test",
        sha="abc",
        governance_results=_passing_blocking_governance_results(),
        compose_report=compose_report,
        live_report=None,
    )

    assert compose_report is None
    assert report["compose_validation"] is None
    assert report["overall_readiness"]["compose_validated"] is True
    assert report["overall_readiness"]["deployment_ready"] is True


def test_invalid_live_artifact_results_in_absent_live_validation_semantics(
    tmp_path,
) -> None:
    """Invalid live artifacts should map to absent live validation semantics."""
    path = tmp_path / "live-report.json"
    path.write_text("{not-json", encoding="utf-8")

    live_report = load_json_report(str(path))
    report = build_report(
        ref="test",
        sha="abc",
        governance_results=_passing_blocking_governance_results(),
        compose_report=None,
        live_report=live_report,
    )

    assert live_report is None
    assert report["live_provider_validation"] is None
    assert report["overall_readiness"]["live_provider_ok"] is True
    assert report["overall_readiness"]["deployment_ready"] is True


def test_text_report_marks_absent_compose_and_live_reports_as_not_included() -> None:
    """Text report should mark absent compose/live reports as not included."""
    report = build_report(
        ref="test",
        sha="abc",
        governance_results=_passing_blocking_governance_results(),
        compose_report=None,
        live_report=None,
    )

    text = render_text_report(report)

    assert "Compose Validation" in text
    assert "Not included (run with --compose-report)" in text
    assert "Live Provider Validation" in text
    assert "Not included (run with --live-report)" in text
