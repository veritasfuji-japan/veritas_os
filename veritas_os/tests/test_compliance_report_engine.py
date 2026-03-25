from __future__ import annotations

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

    assert result == {"available": False, "result": "invalid"}
