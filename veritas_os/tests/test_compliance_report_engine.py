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
