# veritas_os/tests/test_routes_system.py
"""Coverage tests for routes_system.py endpoints (halt, resume, reports, etc.)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

_TEST_KEY = "routes-system-test-key-12345"
os.environ["VERITAS_API_KEY"] = _TEST_KEY
_AUTH = {"X-API-Key": _TEST_KEY}

import pytest
from fastapi.testclient import TestClient

import veritas_os.api.server as server

client = TestClient(server.app)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_KEY)
    server._rate_bucket.clear()


# ------------------------------------------------------------------
# _collect_recent_decide_files
# ------------------------------------------------------------------

def test_collect_recent_decide_files_empty(tmp_path):
    from veritas_os.api.routes_system import _collect_recent_decide_files
    files, total = _collect_recent_decide_files(tmp_path, limit=10)
    assert files == []
    assert total == 0


def test_collect_recent_decide_files_overflow(tmp_path):
    """When more files than limit, only top-N by name are returned."""
    from veritas_os.api.routes_system import _collect_recent_decide_files
    for i in range(5):
        (tmp_path / f"decide_{i:04d}.json").write_text("{}")
    files, total = _collect_recent_decide_files(tmp_path, limit=3)
    assert total == 5
    assert len(files) == 3
    # Should have the 3 newest (highest names)
    names = [f.name for f in files]
    assert "decide_0004.json" in names
    assert "decide_0003.json" in names
    assert "decide_0002.json" in names


# ------------------------------------------------------------------
# /v1/metrics
# ------------------------------------------------------------------

def test_metrics_endpoint():
    resp = client.get("/v1/metrics", headers=_AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert "decide_files" in data
    assert "trust_jsonl_lines" in data


# ------------------------------------------------------------------
# system halt / resume / halt-status
# ------------------------------------------------------------------

class _FakeHaltController:
    @staticmethod
    def halt(reason, operator):
        return {"halted": True, "reason": reason}

    @staticmethod
    def resume(operator, comment=""):
        return {"halted": False}

    @staticmethod
    def status():
        return {"halted": False, "reason": None}


def test_system_halt(monkeypatch):
    monkeypatch.setattr(server, "SystemHaltController", _FakeHaltController)
    resp = client.post(
        "/v1/system/halt",
        json={"reason": "emergency test", "operator": "tester"},
        headers=_AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["halted"] is True


def test_system_halt_error(monkeypatch):
    class _Broken:
        @staticmethod
        def halt(reason, operator):
            raise RuntimeError("boom")
    monkeypatch.setattr(server, "SystemHaltController", _Broken)
    resp = client.post(
        "/v1/system/halt",
        json={"reason": "test error", "operator": "tester"},
        headers=_AUTH,
    )
    assert resp.status_code == 500


def test_system_resume(monkeypatch):
    monkeypatch.setattr(server, "SystemHaltController", _FakeHaltController)
    resp = client.post(
        "/v1/system/resume",
        json={"operator": "tester", "comment": "all clear"},
        headers=_AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_system_resume_error(monkeypatch):
    class _Broken:
        @staticmethod
        def resume(operator, comment=""):
            raise RuntimeError("boom")
    monkeypatch.setattr(server, "SystemHaltController", _Broken)
    resp = client.post(
        "/v1/system/resume",
        json={"operator": "tester"},
        headers=_AUTH,
    )
    assert resp.status_code == 500


def test_system_halt_status(monkeypatch):
    monkeypatch.setattr(server, "SystemHaltController", _FakeHaltController)
    resp = client.get("/v1/system/halt-status", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_system_halt_status_error(monkeypatch):
    class _Broken:
        @staticmethod
        def status():
            raise RuntimeError("boom")
    monkeypatch.setattr(server, "SystemHaltController", _Broken)
    resp = client.get("/v1/system/halt-status", headers=_AUTH)
    assert resp.status_code == 500


# ------------------------------------------------------------------
# /v1/report/eu_ai_act/<decision_id>
# ------------------------------------------------------------------

def test_report_eu_ai_act_success(monkeypatch):
    monkeypatch.setattr(server, "generate_eu_ai_act_report",
                        lambda decision_id: {"ok": True, "report": "data"})
    resp = client.get("/v1/report/eu_ai_act/test-id-123", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_report_eu_ai_act_not_found(monkeypatch):
    monkeypatch.setattr(server, "generate_eu_ai_act_report",
                        lambda decision_id: {"ok": False, "error": "not found"})
    resp = client.get("/v1/report/eu_ai_act/missing-id", headers=_AUTH)
    assert resp.status_code == 404


def test_report_eu_ai_act_error(monkeypatch):
    def _boom(decision_id):
        raise RuntimeError("boom")
    monkeypatch.setattr(server, "generate_eu_ai_act_report", _boom)
    resp = client.get("/v1/report/eu_ai_act/err-id", headers=_AUTH)
    assert resp.status_code == 500


# ------------------------------------------------------------------
# /v1/report/governance
# ------------------------------------------------------------------

def test_report_governance_success(monkeypatch):
    monkeypatch.setattr(server, "generate_internal_governance_report",
                        lambda date_range: {"ok": True, "report": "gov"})
    resp = client.get(
        "/v1/report/governance",
        params={"from": "2026-01-01T00:00:00Z", "to": "2026-01-31T00:00:00Z"},
        headers=_AUTH,
    )
    assert resp.status_code == 200


def test_report_governance_bad_date(monkeypatch):
    def _bad(date_range):
        raise ValueError("bad date")
    monkeypatch.setattr(server, "generate_internal_governance_report", _bad)
    resp = client.get(
        "/v1/report/governance",
        params={"from": "bad", "to": "bad"},
        headers=_AUTH,
    )
    assert resp.status_code == 400


def test_report_governance_error(monkeypatch):
    def _boom(date_range):
        raise RuntimeError("boom")
    monkeypatch.setattr(server, "generate_internal_governance_report", _boom)
    resp = client.get(
        "/v1/report/governance",
        params={"from": "2026-01-01T00:00:00Z", "to": "2026-01-31T00:00:00Z"},
        headers=_AUTH,
    )
    assert resp.status_code == 500


# ------------------------------------------------------------------
# /v1/compliance/deployment-readiness
# ------------------------------------------------------------------

def test_deployment_readiness_success(monkeypatch):
    monkeypatch.setattr(server, "validate_deployment_readiness",
                        lambda: {"ready": True, "checks": []})
    resp = client.get("/v1/compliance/deployment-readiness", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_deployment_readiness_error(monkeypatch):
    monkeypatch.setattr(server, "validate_deployment_readiness",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    # Need a callable that raises
    def _boom():
        raise RuntimeError("boom")
    monkeypatch.setattr(server, "validate_deployment_readiness", _boom)
    resp = client.get("/v1/compliance/deployment-readiness", headers=_AUTH)
    assert resp.status_code == 500


# ------------------------------------------------------------------
# /v1/compliance/config
# ------------------------------------------------------------------

def test_compliance_get_config():
    resp = client.get("/v1/compliance/config", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_compliance_put_config():
    resp = client.put(
        "/v1/compliance/config",
        json={"eu_ai_act_mode": True, "safety_threshold": 0.9},
        headers=_AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
