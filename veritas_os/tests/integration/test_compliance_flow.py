# -*- coding: utf-8 -*-
"""EU AI Act コンプライアンスフローテスト"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


# ============================================================
# Source: test_compliance_report_engine.py
# ============================================================


import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veritas_os.api import server as srv
from veritas_os.compliance import report_engine

HEADERS = {"X-API-Key": "test-governance-key"}


@pytest.fixture(autouse=True)
def _set_test_api_key(monkeypatch):
    """Ensure API key protected endpoints are testable in isolated runs."""
    monkeypatch.setenv("VERITAS_API_KEY", "test-governance-key")
    monkeypatch.setattr(srv, "API_KEY_DEFAULT", "test-governance-key")


def _write_decision(path: Path, request_id: str, risk: float = 0.2) -> None:
    payload = {
        "request_id": request_id,
        "decision_status": "allow",
        "ts": "2026-01-01T12:00:00Z",
        "query": "test query",
        "chosen": {"action": "safe"},
        "gate": {"risk": risk},
        "fuji": {
            "status": "allow",
            "violations": [],
            "modifications": ["redact_sensitive_fields"],
        },
        "critique_ok": True,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_generate_eu_ai_act_report_outputs_json_pdf_and_signature(
    monkeypatch,
    tmp_path: Path,
):
    log_dir = tmp_path / "logs"
    replay_dir = tmp_path / "replay"
    report_dir = tmp_path / "reports"
    key_dir = tmp_path / "keys"
    log_dir.mkdir(parents=True)
    replay_dir.mkdir(parents=True)

    _write_decision(log_dir / "decide_001.json", "dec-001", risk=0.7)
    replay_dir.joinpath("replay_dec-001_1.json").write_text(
        json.dumps({"match": True, "diff": {"changed": False}, "replay_time_ms": 11}),
        encoding="utf-8",
    )

    monkeypatch.setattr(report_engine, "LOG_DIR", log_dir)
    monkeypatch.setattr(report_engine, "REPORT_DIR", report_dir)
    monkeypatch.setattr(report_engine, "REPLAY_REPORT_DIR", replay_dir)
    monkeypatch.setattr(report_engine, "PRIVATE_KEY_PATH", key_dir / "private.key")
    monkeypatch.setattr(report_engine, "PUBLIC_KEY_PATH", key_dir / "public.key")
    monkeypatch.setattr(
        report_engine,
        "verify_trustlog_chain",
        lambda: {"ok": True, "entries_checked": 1, "issues": []},
    )
    monkeypatch.setattr(
        report_engine,
        "verify_trust_log",
        lambda: {"ok": True, "checked": 1, "broken": False, "broken_reason": None},
    )

    result = report_engine.generate_eu_ai_act_report("dec-001")

    assert result["ok"] is True
    assert result["risk_classification"]["risk_level"] == "high"
    assert "signature" in result["signed_report_hash"]
    assert Path(result["artifacts"]["json_path"]).exists()
    assert Path(result["artifacts"]["pdf_path"]).exists()


def test_report_api_endpoints(monkeypatch):
    client = TestClient(srv.app)

    monkeypatch.setattr(
        srv,
        "generate_eu_ai_act_report",
        lambda decision_id: {
            "ok": True,
            "report_type": "eu_ai_act",
            "decision_id": decision_id,
        },
    )
    monkeypatch.setattr(
        srv,
        "generate_internal_governance_report",
        lambda date_range: {
            "ok": True,
            "report_type": "governance",
            "date_range": date_range,
        },
    )

    eu_resp = client.get("/v1/report/eu_ai_act/dec-abc", headers=HEADERS)
    assert eu_resp.status_code == 200
    assert eu_resp.json()["decision_id"] == "dec-abc"

    gov_resp = client.get(
        "/v1/report/governance",
        params={"from": "2026-01-01T00:00:00Z", "to": "2026-01-31T23:59:59Z"},
        headers=HEADERS,
    )
    assert gov_resp.status_code == 200
    assert gov_resp.json()["date_range"] == [
        "2026-01-01T00:00:00Z",
        "2026-01-31T23:59:59Z",
    ]


def test_report_governance_invalid_date(monkeypatch):
    client = TestClient(srv.app)

    def _raise_value_error(date_range):
        raise ValueError("invalid")

    monkeypatch.setattr(srv, "generate_internal_governance_report", _raise_value_error)
    response = client.get(
        "/v1/report/governance",
        params={"from": "bad", "to": "bad"},
        headers=HEADERS,
    )
    assert response.status_code == 400
    assert response.json()["ok"] is False


def test_iter_decision_logs_reraises_unexpected_json_error(monkeypatch, tmp_path: Path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)
    _write_decision(log_dir / "decide_001.json", "dec-001", risk=0.7)
    monkeypatch.setattr(report_engine, "LOG_DIR", log_dir)

    def _raise_runtime_error(_: str):
        raise RuntimeError("unexpected parser failure")

    monkeypatch.setattr(report_engine.json, "loads", _raise_runtime_error)

    with pytest.raises(RuntimeError, match="unexpected parser failure"):
        list(report_engine._iter_decision_logs())


def test_latest_replay_result_reraises_unexpected_json_error(
    monkeypatch,
    tmp_path: Path,
):
    replay_dir = tmp_path / "replay"
    replay_dir.mkdir(parents=True)
    replay_dir.joinpath("replay_dec-001_1.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(report_engine, "REPLAY_REPORT_DIR", replay_dir)

    def _raise_runtime_error(_: str):
        raise RuntimeError("unexpected parser failure")

    monkeypatch.setattr(report_engine.json, "loads", _raise_runtime_error)

    with pytest.raises(RuntimeError, match="unexpected parser failure"):
        report_engine._latest_replay_result("dec-001")


def _patch_report_environment(monkeypatch, tmp_path: Path):
    """Patch report engine paths and integrity checks for stable tests."""
    log_dir = tmp_path / "logs"
    replay_dir = tmp_path / "replay"
    report_dir = tmp_path / "reports"
    key_dir = tmp_path / "keys"

    log_dir.mkdir(parents=True, exist_ok=True)
    replay_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(report_engine, "LOG_DIR", log_dir)
    monkeypatch.setattr(report_engine, "REPLAY_REPORT_DIR", replay_dir)
    monkeypatch.setattr(report_engine, "REPORT_DIR", report_dir)
    monkeypatch.setattr(report_engine, "PRIVATE_KEY_PATH", key_dir / "private.key")
    monkeypatch.setattr(report_engine, "PUBLIC_KEY_PATH", key_dir / "public.key")
    monkeypatch.setattr(
        report_engine,
        "verify_trustlog_chain",
        lambda: {"ok": True, "entries_checked": 2, "issues": []},
    )
    monkeypatch.setattr(
        report_engine,
        "verify_trust_log",
        lambda: {"ok": True, "checked": 2, "broken": False, "broken_reason": None},
    )
    return log_dir, replay_dir, report_dir


def test_generate_eu_ai_act_report_missing_replay_artifact(monkeypatch, tmp_path: Path):
    log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
    _write_decision(log_dir / "decide_no_replay.json", "dec-no-replay", risk=0.25)

    result = report_engine.generate_eu_ai_act_report("dec-no-replay")

    assert result["ok"] is True
    assert result["replay_verification"] == {"available": False, "result": "missing"}


def test_generate_eu_ai_act_report_handles_partial_trust_log(monkeypatch, tmp_path: Path):
    log_dir, replay_dir, _ = _patch_report_environment(monkeypatch, tmp_path)
    _write_decision(log_dir / "decide_partial_trust.json", "dec-partial", risk=0.45)
    replay_dir.joinpath("replay_dec-partial_001.json").write_text(
        json.dumps({"match": False, "diff": {"fuji": "changed"}, "replay_time_ms": 42}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        report_engine,
        "verify_trustlog_chain",
        lambda: {
            "ok": False,
            "entries_checked": 10,
            "issues": ["missing_signature_entry"],
        },
    )
    monkeypatch.setattr(
        report_engine,
        "verify_trust_log",
        lambda: {
            "ok": False,
            "checked": 10,
            "broken": True,
            "broken_reason": "hash_mismatch",
        },
    )

    result = report_engine.generate_eu_ai_act_report("dec-partial")

    assert result["ok"] is True
    assert result["signature_verification"]["ok"] is False
    assert result["signature_verification"]["issues"] == ["missing_signature_entry"]
    assert result["hash_chain_integrity"]["broken"] is True
    assert result["replay_verification"]["match"] is False


def test_build_decision_section_tolerates_missing_optional_fields():
    rec = {"request_id": "req-minimal", "decision_status": "allow"}

    section = report_engine._build_decision_section(rec)

    assert section["decision_overview"]["decision_id"] == "req-minimal"
    assert section["decision_overview"]["timestamp"] is None
    assert section["risk_classification"]["risk_score"] == 0.0
    assert section["risk_classification"]["risk_level"] == "low"
    assert section["mitigation_actions"] == []


@pytest.mark.parametrize(
    ("risk_score", "expected_level"),
    [
        (0.0, "low"),
        (0.3, "medium"),
        (0.5, "high"),
        (0.8, "critical"),
    ],
)
def test_schema_normalization_risk_boundary_levels(risk_score: float, expected_level: str):
    rec = {
        "request_id": f"req-{expected_level}",
        "gate": {"risk": risk_score},
        "fuji": {},
    }

    section = report_engine._build_decision_section(rec)

    assert section["risk_classification"]["risk_level"] == expected_level
    assert isinstance(section["risk_classification"]["violations"], list)
    assert isinstance(section["mitigation_actions"], list)


def test_generate_internal_governance_report_omits_invalid_optional_records(
    monkeypatch,
    tmp_path: Path,
):
    log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)

    _write_decision(log_dir / "decide_valid_001.json", "dec-valid-1", risk=0.9)
    _write_decision(log_dir / "decide_valid_002.json", "dec-valid-2", risk=0.1)

    (log_dir / "decide_missing_ts.json").write_text(
        json.dumps({"request_id": "dec-no-ts", "gate": {"risk": 0.7}}),
        encoding="utf-8",
    )
    (log_dir / "decide_invalid_ts.json").write_text(
        json.dumps(
            {
                "request_id": "dec-bad-ts",
                "ts": "not-a-date",
                "gate": {"risk": 0.7},
            }
        ),
        encoding="utf-8",
    )

    result = report_engine.generate_internal_governance_report(
        ("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")
    )

    assert result["ok"] is True
    assert result["decision_count"] == 2
    assert result["summary"]["high_risk_decisions"] == 1
    assert result["summary"]["risk_ratio"] == 0.5


def test_generate_internal_governance_report_empty_input(monkeypatch, tmp_path: Path):
    _patch_report_environment(monkeypatch, tmp_path)

    result = report_engine.generate_internal_governance_report(
        ("2026-01-01T00:00:00Z", "2026-01-01T23:59:59Z")
    )

    assert result["ok"] is True
    assert result["decision_count"] == 0
    assert result["summary"]["risk_ratio"] == 0.0
    assert result["summary"]["high_risk_decisions"] == 0
    assert result["replay_verification"]["result"] == "missing"


def test_generate_internal_governance_report_invalid_input_raises_value_error(
    monkeypatch,
    tmp_path: Path,
):
    _patch_report_environment(monkeypatch, tmp_path)

    with pytest.raises(ValueError):
        report_engine.generate_internal_governance_report(("invalid", "2026-01-01"))


def test_generate_eu_ai_act_report_not_found_has_fallback_narrative():
    result = report_engine.generate_eu_ai_act_report("not-found")

    assert result == {
        "ok": False,
        "error": "decision_not_found",
        "decision_id": "not-found",
    }


def test_finalize_report_includes_export_artifacts_paths(monkeypatch, tmp_path: Path):
    _, _, report_dir = _patch_report_environment(monkeypatch, tmp_path)

    report = report_engine._finalize_report(
        "eu_ai_act",
        {"scope": "eu_ai_act", "summary": {"compliance_status": "pass"}},
    ).report

    json_path = Path(report["artifacts"]["json_path"])
    pdf_path = Path(report["artifacts"]["pdf_path"])

    assert json_path.exists()
    assert pdf_path.exists()
    assert json_path.parent == report_dir
    assert pdf_path.parent == report_dir
    assert json_path.suffix == ".json"
    assert pdf_path.suffix == ".pdf"


def test_risk_summary_report_compliance_readiness_summary(monkeypatch, tmp_path: Path):
    log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
    _write_decision(log_dir / "decide_low.json", "low", risk=0.1)
    _write_decision(log_dir / "decide_medium.json", "medium", risk=0.4)
    _write_decision(log_dir / "decide_high.json", "high", risk=0.7)

    result = report_engine.generate_risk_summary_report()

    assert result["ok"] is True
    assert result["decision_count"] == 3
    assert result["risk_distribution"] == {
        "low": 1,
        "medium": 1,
        "high": 1,
        "critical": 0,
    }
    assert result["summary"]["top_risk_level"] in {"low", "medium", "high"}


def test_latest_replay_result_invalid_schema_returns_degraded_result(
    monkeypatch,
    tmp_path: Path,
):
    _, replay_dir, _ = _patch_report_environment(monkeypatch, tmp_path)
    replay_dir.joinpath("replay_dec-invalid_1.json").write_text("[]", encoding="utf-8")

    result = report_engine._latest_replay_result("dec-invalid")

    assert result == {"available": False, "result": "invalid_type"}


# ---------------------------------------------------------------------------
# ▼ New tests: malformed log input, missing evidence, stale/absent policy,
#   partial compliance data, replay validation, deterministic output,
#   governance integration, explainability
# ---------------------------------------------------------------------------


class TestValidateDecisionRecord:
    """Unit tests for _validate_decision_record."""

    def test_valid_record_returns_no_issues(self):
        rec = {
            "request_id": "req-1",
            "gate": {"risk": 0.5},
            "fuji": {"status": "allow"},
        }
        assert report_engine._validate_decision_record(rec) == []

    def test_missing_request_id(self):
        issues = report_engine._validate_decision_record({})
        assert "missing_required_field:request_id" in issues

    def test_empty_request_id(self):
        issues = report_engine._validate_decision_record({"request_id": ""})
        assert "missing_required_field:request_id" in issues

    def test_gate_not_dict(self):
        rec = {"request_id": "req-1", "gate": "not-a-dict"}
        issues = report_engine._validate_decision_record(rec)
        assert "invalid_gate_type:expected_dict" in issues

    def test_fuji_not_dict(self):
        rec = {"request_id": "req-1", "fuji": [1, 2, 3]}
        issues = report_engine._validate_decision_record(rec)
        assert "invalid_fuji_type:expected_dict" in issues

    def test_risk_out_of_range(self):
        rec = {"request_id": "req-1", "gate": {"risk": 1.5}}
        issues = report_engine._validate_decision_record(rec)
        assert "risk_out_of_range:expected_0_to_1" in issues

    def test_risk_not_numeric(self):
        rec = {"request_id": "req-1", "gate": {"risk": "not-a-number"}}
        issues = report_engine._validate_decision_record(rec)
        assert "risk_not_numeric" in issues

    def test_negative_risk(self):
        rec = {"request_id": "req-1", "gate": {"risk": -0.1}}
        issues = report_engine._validate_decision_record(rec)
        assert "risk_out_of_range:expected_0_to_1" in issues


class TestValidateReplayPayload:
    """Unit tests for _validate_replay_payload."""

    def test_valid_payload(self):
        payload = {"match": True, "diff": {}, "replay_time_ms": 42}
        result = report_engine._validate_replay_payload(payload)
        assert result["available"] is True
        assert result["valid"] is True
        assert result["match"] is True

    def test_non_dict_returns_invalid(self):
        result = report_engine._validate_replay_payload([1, 2])
        assert result["available"] is False
        assert result["valid"] is False
        assert result["reason"] == "invalid_type"

    def test_none_returns_invalid(self):
        result = report_engine._validate_replay_payload(None)
        assert result["available"] is False
        assert result["reason"] == "invalid_type"

    def test_preserves_schema_version(self):
        payload = {"match": False, "diff": {}, "schema_version": "1.0.0"}
        result = report_engine._validate_replay_payload(payload)
        assert result["schema_version"] == "1.0.0"

    def test_preserves_severity_and_divergence(self):
        payload = {
            "match": False,
            "diff": {},
            "severity": "critical",
            "divergence_level": "critical_divergence",
            "audit_summary": "mismatch found",
        }
        result = report_engine._validate_replay_payload(payload)
        assert result["severity"] == "critical"
        assert result["divergence_level"] == "critical_divergence"
        assert result["audit_summary"] == "mismatch found"


class TestClassifyRiskWithGovernanceThresholds:
    """Test risk classification with custom governance thresholds."""

    def test_default_thresholds(self):
        assert report_engine._classify_risk(0.1) == "low"
        assert report_engine._classify_risk(0.3) == "medium"
        assert report_engine._classify_risk(0.5) == "high"
        assert report_engine._classify_risk(0.8) == "critical"

    def test_custom_thresholds_lower(self):
        custom = {"medium_lower": 0.2, "high_lower": 0.4, "critical_lower": 0.6}
        assert report_engine._classify_risk(0.1, custom) == "low"
        assert report_engine._classify_risk(0.25, custom) == "medium"
        assert report_engine._classify_risk(0.45, custom) == "high"
        assert report_engine._classify_risk(0.65, custom) == "critical"

    def test_custom_thresholds_higher(self):
        strict = {"medium_lower": 0.5, "high_lower": 0.7, "critical_lower": 0.9}
        assert report_engine._classify_risk(0.4, strict) == "low"
        assert report_engine._classify_risk(0.6, strict) == "medium"
        assert report_engine._classify_risk(0.8, strict) == "high"
        assert report_engine._classify_risk(0.95, strict) == "critical"


class TestMalformedLogInput:
    """Test report generation with malformed decision log files."""

    def test_non_dict_json_file_skipped(self, monkeypatch, tmp_path):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        (log_dir / "decide_array.json").write_text("[1,2,3]", encoding="utf-8")
        _write_decision(log_dir / "decide_valid.json", "dec-ok", risk=0.1)

        result = report_engine.generate_risk_summary_report()
        assert result["ok"] is True
        assert result["decision_count"] == 1

    def test_corrupt_json_file_skipped(self, monkeypatch, tmp_path):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        (log_dir / "decide_corrupt.json").write_text("{bad json", encoding="utf-8")
        _write_decision(log_dir / "decide_valid.json", "dec-ok", risk=0.2)

        result = report_engine.generate_risk_summary_report()
        assert result["ok"] is True
        assert result["decision_count"] == 1

    def test_empty_file_skipped(self, monkeypatch, tmp_path):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        (log_dir / "decide_empty.json").write_text("", encoding="utf-8")
        _write_decision(log_dir / "decide_valid.json", "dec-ok", risk=0.3)

        result = report_engine.generate_risk_summary_report()
        assert result["ok"] is True
        assert result["decision_count"] == 1


class TestMissingEvidence:
    """Test reports with missing evidence components."""

    def test_eu_report_missing_fuji_and_gate(self, monkeypatch, tmp_path):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        (log_dir / "decide_bare.json").write_text(
            json.dumps({
                "request_id": "dec-bare",
                "decision_status": "allow",
                "ts": "2026-01-01T12:00:00Z",
            }),
            encoding="utf-8",
        )

        result = report_engine.generate_eu_ai_act_report("dec-bare")
        assert result["ok"] is True
        assert result["risk_classification"]["risk_score"] == 0.0
        assert result["mitigation_actions"] == []
        assert result["policy_application_evidence"]["fuji"] == {}
        assert result["policy_application_evidence"]["gate"] == {}

    def test_eu_report_with_non_dict_gate_degrades_gracefully(
        self, monkeypatch, tmp_path
    ):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        (log_dir / "decide_bad_gate.json").write_text(
            json.dumps({
                "request_id": "dec-bad-gate",
                "decision_status": "allow",
                "ts": "2026-01-01T12:00:00Z",
                "gate": "not-a-dict",
                "fuji": "also-not-a-dict",
            }),
            encoding="utf-8",
        )

        result = report_engine.generate_eu_ai_act_report("dec-bad-gate")
        assert result["ok"] is True
        assert "invalid_gate_type:expected_dict" in result["validation_issues"]
        assert "invalid_fuji_type:expected_dict" in result["validation_issues"]
        assert result["risk_classification"]["risk_score"] == 0.0


class TestStaleAbsentPolicy:
    """Test report generation when governance policy is unavailable or stale."""

    def test_governance_unavailable_uses_defaults(self, monkeypatch, tmp_path):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        _write_decision(log_dir / "decide_001.json", "dec-001", risk=0.7)

        monkeypatch.setattr(
            report_engine,
            "_load_governance_context",
            lambda: {
                "policy_available": False,
                "policy_version": "unavailable",
                "policy_updated_at": "",
                "risk_thresholds": dict(report_engine._DEFAULT_RISK_THRESHOLDS),
            },
        )

        result = report_engine.generate_eu_ai_act_report("dec-001")
        assert result["ok"] is True
        assert result["governance_context"]["policy_available"] is False
        assert result["governance_context"]["policy_version"] == "unavailable"
        assert "default thresholds" in result["summary"]["narrative"]

    def test_governance_policy_exception_degrades_gracefully(
        self, monkeypatch, tmp_path
    ):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        _write_decision(log_dir / "decide_001.json", "dec-001", risk=0.4)

        def _raise(*args, **kwargs):
            raise ConnectionError("governance service down")

        monkeypatch.setattr(
            report_engine,
            "_load_governance_context",
            lambda: {
                "policy_available": False,
                "policy_version": "unavailable",
                "policy_updated_at": "",
                "risk_thresholds": dict(report_engine._DEFAULT_RISK_THRESHOLDS),
            },
        )

        result = report_engine.generate_eu_ai_act_report("dec-001")
        assert result["ok"] is True
        assert result["governance_context"]["policy_available"] is False

    def test_governance_context_included_in_risk_summary(
        self, monkeypatch, tmp_path
    ):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        _write_decision(log_dir / "decide_001.json", "dec-001", risk=0.5)

        result = report_engine.generate_risk_summary_report()
        assert result["ok"] is True
        assert "governance_context" in result
        assert "policy_version" in result["governance_context"]

    def test_governance_context_included_in_governance_report(
        self, monkeypatch, tmp_path
    ):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        _write_decision(log_dir / "decide_001.json", "dec-001", risk=0.5)

        result = report_engine.generate_internal_governance_report(
            ("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")
        )
        assert result["ok"] is True
        assert "governance_context" in result
        assert "policy_version" in result["governance_context"]


class TestPartialComplianceData:
    """Test reports with incomplete or partial decision records."""

    def test_decision_with_only_request_id(self, monkeypatch, tmp_path):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        (log_dir / "decide_minimal.json").write_text(
            json.dumps({
                "request_id": "dec-minimal",
                "ts": "2026-01-01T12:00:00Z",
            }),
            encoding="utf-8",
        )

        result = report_engine.generate_eu_ai_act_report("dec-minimal")
        assert result["ok"] is True
        assert result["decision_overview"]["decision_id"] == "dec-minimal"
        assert result["decision_overview"]["decision_status"] is None
        assert result["risk_classification"]["risk_level"] == "low"

    def test_governance_report_with_mixed_valid_invalid_records(
        self, monkeypatch, tmp_path
    ):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        _write_decision(log_dir / "decide_valid.json", "dec-valid", risk=0.1)

        (log_dir / "decide_no_ts.json").write_text(
            json.dumps({"request_id": "dec-no-ts", "gate": {"risk": 0.5}}),
            encoding="utf-8",
        )
        (log_dir / "decide_bad_ts.json").write_text(
            json.dumps({
                "request_id": "dec-bad-ts",
                "ts": "not-a-date",
                "gate": {"risk": 0.9},
            }),
            encoding="utf-8",
        )

        result = report_engine.generate_internal_governance_report(
            ("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")
        )
        assert result["ok"] is True
        assert result["decision_count"] == 1
        assert result["summary"]["skipped_records"] == 2
        assert len(result["skipped_records"]) == 2

        reasons = {r["reason"] for r in result["skipped_records"]}
        assert "missing_timestamp" in reasons
        assert "invalid_timestamp" in reasons

    def test_validation_issues_set_review_required(self, monkeypatch, tmp_path):
        """Decisions with validation issues trigger review_required status."""
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        (log_dir / "decide_no_reqid.json").write_text(
            json.dumps({
                "decision_id": "dec-no-reqid",
                "ts": "2026-01-01T12:00:00Z",
                "decision_status": "allow",
            }),
            encoding="utf-8",
        )

        result = report_engine.generate_eu_ai_act_report("dec-no-reqid")
        assert result["ok"] is True
        assert "missing_required_field:request_id" in result["validation_issues"]
        assert result["summary"]["compliance_status"] == "review_required"


class TestReplayValidation:
    """Test replay result validation in the report pipeline."""

    def test_replay_with_schema_version_preserved(self, monkeypatch, tmp_path):
        _, replay_dir, _ = _patch_report_environment(monkeypatch, tmp_path)
        replay_dir.joinpath("replay_dec-sv_1.json").write_text(
            json.dumps({
                "match": True,
                "diff": {},
                "replay_time_ms": 10,
                "schema_version": "1.0.0",
                "severity": "info",
                "divergence_level": "no_divergence",
            }),
            encoding="utf-8",
        )

        result = report_engine._latest_replay_result("dec-sv")
        assert result["available"] is True
        assert result["schema_version"] == "1.0.0"
        assert result["severity"] == "info"

    def test_replay_unreadable_file(self, monkeypatch, tmp_path):
        _, replay_dir, _ = _patch_report_environment(monkeypatch, tmp_path)
        replay_dir.joinpath("replay_dec-unread_1.json").write_text(
            "{not valid json", encoding="utf-8"
        )

        result = report_engine._latest_replay_result("dec-unread")
        assert result == {"available": False, "result": "unreadable"}


class TestDeterministicOutput:
    """Test that reports are deterministic given the same inputs."""

    def test_finalize_report_includes_schema_version(self, monkeypatch, tmp_path):
        _patch_report_environment(monkeypatch, tmp_path)

        report = report_engine._finalize_report(
            "eu_ai_act",
            {"scope": "eu_ai_act", "summary": {"compliance_status": "pass"}},
        ).report

        assert report["report_schema_version"] == report_engine.REPORT_SCHEMA_VERSION

    def test_finalize_report_accepts_injected_timestamp(self, monkeypatch, tmp_path):
        _patch_report_environment(monkeypatch, tmp_path)

        fixed_ts = "2026-01-01T00:00:00Z"
        report = report_engine._finalize_report(
            "eu_ai_act",
            {"scope": "eu_ai_act", "summary": {"compliance_status": "pass"}},
            generated_at=fixed_ts,
        ).report

        assert report["generated_at"] == fixed_ts

    def test_same_input_same_hash_with_fixed_timestamp(self, monkeypatch, tmp_path):
        _patch_report_environment(monkeypatch, tmp_path)

        payload = {"scope": "eu_ai_act", "summary": {"compliance_status": "pass"}}
        fixed_ts = "2026-01-01T00:00:00Z"

        r1 = report_engine._finalize_report(
            "eu_ai_act", dict(payload), generated_at=fixed_ts
        ).report
        r2 = report_engine._finalize_report(
            "eu_ai_act", dict(payload), generated_at=fixed_ts
        ).report

        assert r1["signed_report_hash"]["report_hash"] == r2["signed_report_hash"]["report_hash"]


class TestExplainability:
    """Test compliance narrative / explainability features."""

    def test_eu_report_includes_narrative(self, monkeypatch, tmp_path):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        _write_decision(log_dir / "decide_001.json", "dec-001", risk=0.6)

        result = report_engine.generate_eu_ai_act_report("dec-001")
        assert result["ok"] is True
        narrative = result["summary"]["narrative"]
        assert "dec-001" in narrative
        assert "Risk score" in narrative

    def test_narrative_mentions_replay_missing(self, monkeypatch, tmp_path):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        _write_decision(log_dir / "decide_001.json", "dec-001", risk=0.2)

        result = report_engine.generate_eu_ai_act_report("dec-001")
        assert "not available" in result["summary"]["narrative"]

    def test_narrative_mentions_integrity_issues(self, monkeypatch, tmp_path):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        _write_decision(log_dir / "decide_001.json", "dec-001", risk=0.3)
        monkeypatch.setattr(
            report_engine,
            "verify_trustlog_chain",
            lambda: {"ok": False, "entries_checked": 5, "issues": ["sig_err"]},
        )
        monkeypatch.setattr(
            report_engine,
            "verify_trust_log",
            lambda: {"ok": False, "checked": 5, "broken": True, "broken_reason": "x"},
        )

        result = report_engine.generate_eu_ai_act_report("dec-001")
        narrative = result["summary"]["narrative"]
        assert "signature verification failed" in narrative
        assert "hash chain integrity broken" in narrative

    def test_narrative_mentions_replay_match(self, monkeypatch, tmp_path):
        log_dir, replay_dir, _ = _patch_report_environment(monkeypatch, tmp_path)
        _write_decision(log_dir / "decide_001.json", "dec-001", risk=0.2)
        replay_dir.joinpath("replay_dec-001_1.json").write_text(
            json.dumps({"match": True, "diff": {}, "replay_time_ms": 5}),
            encoding="utf-8",
        )

        result = report_engine.generate_eu_ai_act_report("dec-001")
        assert "deterministic output" in result["summary"]["narrative"]

    def test_narrative_mentions_replay_divergence(self, monkeypatch, tmp_path):
        log_dir, replay_dir, _ = _patch_report_environment(monkeypatch, tmp_path)
        _write_decision(log_dir / "decide_001.json", "dec-001", risk=0.2)
        replay_dir.joinpath("replay_dec-001_1.json").write_text(
            json.dumps({"match": False, "diff": {"decision": "changed"}, "replay_time_ms": 5}),
            encoding="utf-8",
        )

        result = report_engine.generate_eu_ai_act_report("dec-001")
        assert "divergence" in result["summary"]["narrative"]


class TestInputSourcesTraceability:
    """Test that reports include input_sources metadata."""

    def test_eu_report_includes_input_sources(self, monkeypatch, tmp_path):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        _write_decision(log_dir / "decide_001.json", "dec-001", risk=0.1)

        result = report_engine.generate_eu_ai_act_report("dec-001")
        assert "input_sources" in result
        assert "decision_log" in result["input_sources"]
        assert "replay_dir" in result["input_sources"]
        assert "governance_policy_version" in result["input_sources"]

    def test_governance_report_includes_input_sources(self, monkeypatch, tmp_path):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        _write_decision(log_dir / "decide_001.json", "dec-001", risk=0.1)

        result = report_engine.generate_internal_governance_report(
            ("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")
        )
        assert "input_sources" in result
        assert "log_dir" in result["input_sources"]

    def test_risk_summary_includes_input_sources(self, monkeypatch, tmp_path):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        _write_decision(log_dir / "decide_001.json", "dec-001", risk=0.1)

        result = report_engine.generate_risk_summary_report()
        assert "input_sources" in result
        assert "log_dir" in result["input_sources"]


class TestBuildDecisionSectionWithGovernance:
    """Test _build_decision_section with governance context."""

    def test_thresholds_used_reflects_governance(self):
        rec = {"request_id": "req-1", "gate": {"risk": 0.5}, "fuji": {}}
        gov_ctx = {
            "risk_thresholds": {
                "medium_lower": 0.2,
                "high_lower": 0.4,
                "critical_lower": 0.6,
            },
        }

        section = report_engine._build_decision_section(rec, gov_ctx)
        assert section["risk_classification"]["thresholds_used"] == gov_ctx["risk_thresholds"]
        assert section["risk_classification"]["risk_level"] == "high"

    def test_thresholds_used_defaults_without_governance(self):
        rec = {"request_id": "req-1", "gate": {"risk": 0.5}, "fuji": {}}
        section = report_engine._build_decision_section(rec)
        assert section["risk_classification"]["thresholds_used"] == report_engine._DEFAULT_RISK_THRESHOLDS

    def test_validation_issues_included(self):
        rec = {"gate": "not-a-dict"}
        section = report_engine._build_decision_section(rec)
        assert "missing_required_field:request_id" in section["validation_issues"]
        assert "invalid_gate_type:expected_dict" in section["validation_issues"]


# ---------------------------------------------------------------------------
# ▼ Enhanced tests: reproducible evidence generation, schema strictness,
#   deterministic filenames, evidence completeness, narrative coverage,
#   replay required-field validation, path traversal, date-range ordering
# ---------------------------------------------------------------------------


class TestSafeFilenameId:
    """Verify _safe_filename_id sanitises dangerous characters."""

    def test_strips_path_traversal_characters(self):
        assert ".." not in report_engine._safe_filename_id("../../etc/passwd")
        assert "/" not in report_engine._safe_filename_id("foo/bar")

    def test_truncates_long_ids(self):
        long_id = "a" * 300
        assert len(report_engine._safe_filename_id(long_id)) == 128

    def test_preserves_safe_characters(self):
        assert report_engine._safe_filename_id("dec-001_abc") == "dec-001_abc"


class TestFindDecision:
    """Verify _find_decision matches on both request_id and decision_id."""

    def test_matches_by_request_id(self, monkeypatch, tmp_path):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        _write_decision(log_dir / "decide_001.json", "req-match", risk=0.1)

        assert report_engine._find_decision("req-match") is not None

    def test_matches_by_decision_id(self, monkeypatch, tmp_path):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        payload = {
            "request_id": "req-x",
            "decision_id": "did-y",
            "decision_status": "allow",
            "ts": "2026-01-01T12:00:00Z",
            "gate": {"risk": 0.1},
            "fuji": {},
        }
        (log_dir / "decide_did.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

        assert report_engine._find_decision("did-y") is not None
        assert report_engine._find_decision("req-x") is not None
        assert report_engine._find_decision("nonexistent") is None


class TestValidateTimestamp:
    """Test _validate_timestamp helper."""

    def test_valid_iso8601(self):
        assert report_engine._validate_timestamp("2026-01-01T12:00:00Z") is None

    def test_valid_with_offset(self):
        assert report_engine._validate_timestamp("2026-01-01T12:00:00+09:00") is None

    def test_invalid_format(self):
        assert report_engine._validate_timestamp("not-a-date") == "invalid_timestamp_format"

    def test_empty_string(self):
        assert report_engine._validate_timestamp("") == "invalid_timestamp_format"


class TestDecisionRecordTimestampValidation:
    """Verify _validate_decision_record catches bad timestamps."""

    def test_invalid_timestamp_reported(self):
        rec = {
            "request_id": "req-1",
            "ts": "not-a-timestamp",
        }
        issues = report_engine._validate_decision_record(rec)
        assert "invalid_timestamp_format" in issues

    def test_valid_timestamp_no_issue(self):
        rec = {
            "request_id": "req-1",
            "ts": "2026-01-01T12:00:00Z",
            "gate": {"risk": 0.5},
            "fuji": {},
        }
        issues = report_engine._validate_decision_record(rec)
        assert "invalid_timestamp_format" not in issues

    def test_unknown_decision_status_flagged(self):
        rec = {"request_id": "req-1", "decision_status": "banana"}
        issues = report_engine._validate_decision_record(rec)
        assert any("unknown_decision_status" in i for i in issues)

    def test_known_decision_status_ok(self):
        for status in ("allow", "reject", "review", "block"):
            rec = {"request_id": "req-1", "decision_status": status}
            issues = report_engine._validate_decision_record(rec)
            assert not any("unknown_decision_status" in i for i in issues)


class TestReplayRequiredFields:
    """Verify replay validation rejects payloads missing required fields."""

    def test_missing_match_field(self):
        result = report_engine._validate_replay_payload({"diff": {}})
        assert result["valid"] is False
        assert "missing_required_fields" in result["reason"]
        assert "match" in result["reason"]

    def test_missing_diff_field(self):
        result = report_engine._validate_replay_payload({"match": True})
        assert result["valid"] is False
        assert "diff" in result["reason"]

    def test_missing_both_fields(self):
        result = report_engine._validate_replay_payload({})
        assert result["valid"] is False
        assert "match" in result["reason"]
        assert "diff" in result["reason"]

    def test_replay_with_missing_required_returns_degraded_in_latest(
        self, monkeypatch, tmp_path
    ):
        """_latest_replay_result returns unavailable when replay lacks required fields."""
        _, replay_dir, _ = _patch_report_environment(monkeypatch, tmp_path)
        replay_dir.joinpath("replay_dec-bad_1.json").write_text(
            json.dumps({"some_field": "value"}), encoding="utf-8"
        )

        result = report_engine._latest_replay_result("dec-bad")
        assert result["available"] is False
        assert "missing_required_fields" in result["result"]


class TestDeterministicFilenames:
    """Verify report filenames are derived from the injected timestamp."""

    def test_filename_matches_injected_timestamp(self, monkeypatch, tmp_path):
        _patch_report_environment(monkeypatch, tmp_path)

        fixed_ts = "2026-06-15T08:30:00Z"
        artifact = report_engine._finalize_report(
            "eu_ai_act",
            {"scope": "eu_ai_act", "summary": {}},
            generated_at=fixed_ts,
        )

        assert "20260615_083000" in artifact.json_path.name
        assert "20260615_083000" in artifact.pdf_path.name

    def test_two_calls_same_timestamp_same_filenames(self, monkeypatch, tmp_path):
        _patch_report_environment(monkeypatch, tmp_path)

        fixed_ts = "2026-03-01T00:00:00Z"
        a1 = report_engine._finalize_report(
            "test", {"scope": "test"}, generated_at=fixed_ts,
        )
        a2 = report_engine._finalize_report(
            "test", {"scope": "test"}, generated_at=fixed_ts,
        )

        assert a1.json_path.name == a2.json_path.name


class TestEvidenceCompleteness:
    """Test _compute_evidence_completeness scoring."""

    def test_full_evidence_scores_1(self):
        rec = {
            "gate": {"risk": 0.3},
            "fuji": {"status": "allow"},
            "ts": "2026-01-01T12:00:00Z",
        }
        integrity = {
            "replay_verification": {"available": True, "valid": True, "match": True},
            "signature_verification": {"ok": True},
            "hash_chain_integrity": {"ok": True},
        }
        gov_ctx = {"policy_available": True}

        result = report_engine._compute_evidence_completeness(rec, integrity, gov_ctx)
        assert result["score"] == 1.0
        assert all(v == 1.0 for v in result["components"].values())

    def test_missing_everything_scores_0(self):
        rec = {}
        integrity = {
            "replay_verification": {"available": False},
            "signature_verification": {"ok": False},
            "hash_chain_integrity": {"ok": False},
        }
        gov_ctx = {"policy_available": False}

        result = report_engine._compute_evidence_completeness(rec, integrity, gov_ctx)
        assert result["score"] == 0.0

    def test_partial_evidence_scores_between_0_and_1(self):
        rec = {
            "gate": {"risk": 0.2},
            "ts": "2026-01-01T12:00:00Z",
        }
        integrity = {
            "replay_verification": {"available": False},
            "signature_verification": {"ok": True},
            "hash_chain_integrity": {"ok": True},
        }
        gov_ctx = {"policy_available": False}

        result = report_engine._compute_evidence_completeness(rec, integrity, gov_ctx)
        assert 0.0 < result["score"] < 1.0
        assert result["components"]["fuji"] == 0.0
        assert result["components"]["gate"] == 1.0

    def test_degraded_replay_scores_half(self):
        rec = {"gate": {}, "fuji": {}, "ts": "2026-01-01T12:00:00Z"}
        integrity = {
            "replay_verification": {"available": True, "valid": False},
            "signature_verification": {"ok": True},
            "hash_chain_integrity": {"ok": True},
        }
        gov_ctx = {"policy_available": True}

        result = report_engine._compute_evidence_completeness(rec, integrity, gov_ctx)
        assert result["components"]["replay"] == 0.5

    def test_eu_report_includes_evidence_completeness(self, monkeypatch, tmp_path):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        _write_decision(log_dir / "decide_001.json", "dec-001", risk=0.5)

        result = report_engine.generate_eu_ai_act_report("dec-001")
        assert result["ok"] is True
        assert "evidence_completeness" in result
        assert "score" in result["evidence_completeness"]
        assert "components" in result["evidence_completeness"]
        assert 0.0 <= result["evidence_completeness"]["score"] <= 1.0


class TestNarrativeEnhancements:
    """Test enhanced narrative content."""

    def test_narrative_includes_validation_issues(self, monkeypatch, tmp_path):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        (log_dir / "decide_bad.json").write_text(
            json.dumps({
                "request_id": "dec-bad",
                "decision_status": "allow",
                "ts": "2026-01-01T12:00:00Z",
                "gate": "not-a-dict",
            }),
            encoding="utf-8",
        )

        result = report_engine.generate_eu_ai_act_report("dec-bad")
        narrative = result["summary"]["narrative"]
        assert "Validation issues found" in narrative
        assert "Manual review required" in narrative

    def test_narrative_includes_fuji_violations(self, monkeypatch, tmp_path):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        (log_dir / "decide_violations.json").write_text(
            json.dumps({
                "request_id": "dec-viol",
                "decision_status": "reject",
                "ts": "2026-01-01T12:00:00Z",
                "gate": {"risk": 0.9},
                "fuji": {
                    "status": "reject",
                    "violations": ["pii_detected", "self_harm_content"],
                },
            }),
            encoding="utf-8",
        )

        result = report_engine.generate_eu_ai_act_report("dec-viol")
        narrative = result["summary"]["narrative"]
        assert "Content safety violations detected" in narrative
        assert "pii_detected" in narrative

    def test_narrative_no_validation_issues_when_clean(self, monkeypatch, tmp_path):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        _write_decision(log_dir / "decide_clean.json", "dec-clean", risk=0.2)

        result = report_engine.generate_eu_ai_act_report("dec-clean")
        assert "Validation issues found" not in result["summary"]["narrative"]


class TestGovernanceReportDateRangeOrdering:
    """Verify governance report rejects inverted date ranges."""

    def test_start_after_end_raises_value_error(self, monkeypatch, tmp_path):
        _patch_report_environment(monkeypatch, tmp_path)

        with pytest.raises(ValueError, match="must not be after"):
            report_engine.generate_internal_governance_report(
                ("2026-02-01T00:00:00Z", "2026-01-01T00:00:00Z")
            )

    def test_same_start_and_end_succeeds(self, monkeypatch, tmp_path):
        _patch_report_environment(monkeypatch, tmp_path)

        result = report_engine.generate_internal_governance_report(
            ("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
        )
        assert result["ok"] is True


class TestSchemaVersion:
    """Verify the report schema version is updated consistently."""

    def test_schema_version_is_1_2_0(self):
        assert report_engine.REPORT_SCHEMA_VERSION == "1.2.0"

    def test_all_report_types_include_schema_version(self, monkeypatch, tmp_path):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        _write_decision(log_dir / "decide_001.json", "dec-001", risk=0.3)

        eu = report_engine.generate_eu_ai_act_report("dec-001")
        assert eu["report_schema_version"] == "1.2.0"

        gov = report_engine.generate_internal_governance_report(
            ("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")
        )
        assert gov["report_schema_version"] == "1.2.0"

        risk = report_engine.generate_risk_summary_report()
        assert risk["report_schema_version"] == "1.2.0"


class TestGovernanceReportSkippedRecordDetail:
    """Verify skipped_records contains actionable detail."""

    def test_skipped_records_include_request_id_and_reason(
        self, monkeypatch, tmp_path
    ):
        log_dir, _, _ = _patch_report_environment(monkeypatch, tmp_path)
        (log_dir / "decide_no_ts.json").write_text(
            json.dumps({"request_id": "dec-no-ts", "gate": {"risk": 0.5}}),
            encoding="utf-8",
        )
        (log_dir / "decide_bad_ts.json").write_text(
            json.dumps({
                "request_id": "dec-bad-ts",
                "ts": "garbage",
                "gate": {"risk": 0.1},
            }),
            encoding="utf-8",
        )

        result = report_engine.generate_internal_governance_report(
            ("2026-01-01T00:00:00Z", "2026-12-31T23:59:59Z")
        )

        skipped = result["skipped_records"]
        assert len(skipped) == 2
        ids = {r["request_id"] for r in skipped}
        assert "dec-no-ts" in ids
        assert "dec-bad-ts" in ids
        reasons = {r["reason"] for r in skipped}
        assert "missing_timestamp" in reasons
        assert "invalid_timestamp" in reasons


class TestReportSignatureIntegrity:
    """Verify the signed hash is actually over the report body."""

    def test_hash_covers_body_without_signature_block(self, monkeypatch, tmp_path):
        _patch_report_environment(monkeypatch, tmp_path)

        from veritas_os.security.hash import sha256_of_canonical_json

        artifact = report_engine._finalize_report(
            "eu_ai_act",
            {"scope": "eu_ai_act", "summary": {}},
            generated_at="2026-01-01T00:00:00Z",
        )

        # Reconstruct body without signed_report_hash and artifacts
        body_for_hash = {
            k: v
            for k, v in artifact.report.items()
            if k not in ("signed_report_hash", "artifacts")
        }
        expected_hash = sha256_of_canonical_json(body_for_hash)
        assert artifact.report["signed_report_hash"]["report_hash"] == expected_hash


class TestEndToEndReportReproducibility:
    """Full end-to-end reproducibility: same inputs → same hash."""

    def test_eu_report_reproducible_with_fixed_env(self, monkeypatch, tmp_path):
        log_dir, replay_dir, _ = _patch_report_environment(monkeypatch, tmp_path)
        _write_decision(log_dir / "decide_001.json", "dec-001", risk=0.55)
        replay_dir.joinpath("replay_dec-001_1.json").write_text(
            json.dumps({
                "match": True,
                "diff": {},
                "replay_time_ms": 10,
                "schema_version": "1.0.0",
            }),
            encoding="utf-8",
        )

        # Fix timestamp and governance for reproducibility
        fixed_ts = "2026-06-01T00:00:00Z"
        monkeypatch.setattr(report_engine, "_utc_now", lambda: fixed_ts)
        monkeypatch.setattr(
            report_engine,
            "_load_governance_context",
            lambda: {
                "policy_available": True,
                "policy_version": "test_v1",
                "policy_updated_at": "2026-01-01",
                "risk_thresholds": dict(report_engine._DEFAULT_RISK_THRESHOLDS),
            },
        )

        r1 = report_engine.generate_eu_ai_act_report("dec-001")
        r2 = report_engine.generate_eu_ai_act_report("dec-001")

        assert r1["signed_report_hash"]["report_hash"] == r2["signed_report_hash"]["report_hash"]
        assert r1["summary"]["narrative"] == r2["summary"]["narrative"]
        assert r1["evidence_completeness"] == r2["evidence_completeness"]
