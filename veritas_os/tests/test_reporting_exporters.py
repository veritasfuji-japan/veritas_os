"""Tests for reporting exporters to improve coverage."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from veritas_os.reporting import exporters


def test_build_w3c_prov_document_clamps_risk_and_actor_fallback() -> None:
    """Risk is clamped into [0, 1] and empty actor uses unknown agent id."""
    document = exporters.build_w3c_prov_document(
        request_id="req-42",
        decision_status="allow",
        risk=9.9,
        timestamp="2026-03-01T00:00:00Z",
        actor="",
    )

    entity_id = "entity:decision:req-42"
    agent_id = "agent:unknown"

    assert document["entity"][entity_id]["veritas:risk"] == 1.0
    assert agent_id in document["agent"]
    assert document["agent"][agent_id]["prov:label"] == ""


def test_build_w3c_prov_document_handles_none_risk() -> None:
    """None risk is normalized to 0.0 for stable downstream parsing."""
    document = exporters.build_w3c_prov_document(
        request_id="req-0",
        decision_status="review",
        risk=None,
        timestamp="2026-03-01T00:00:00Z",
        actor="planner",
    )

    entity_id = "entity:decision:req-0"
    assert document["entity"][entity_id]["veritas:risk"] == 0.0


def test_build_pdf_bytes_escapes_special_characters() -> None:
    """PDF text stream escapes control characters for literal text operators."""
    payload = {
        "report_type": "security",
        "generated_at": "2026-03-01T00:00:00Z",
        "summary": {
            "note": r"slashes\\and(parens)",
        },
    }

    pdf_bytes = exporters.build_pdf_bytes(payload)

    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert b"slashes" in pdf_bytes
    assert b"and\\(parens\\)" in pdf_bytes
    assert b"xref" in pdf_bytes
    assert b"startxref" in pdf_bytes


def test_persist_report_json_creates_parent_and_writes_payload(tmp_path: Path) -> None:
    """JSON exporter creates missing parents and persists valid JSON."""
    path = tmp_path / "nested" / "report.json"
    payload = {"ok": True, "score": 0.3}

    exporters.persist_report_json(path, payload)

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == payload


def test_persist_report_pdf_creates_parent_and_writes_pdf(tmp_path: Path) -> None:
    """PDF exporter creates missing parents and writes a parseable PDF header."""
    path = tmp_path / "nested" / "report.pdf"
    payload = {
        "report_type": "ops",
        "generated_at": "2026-03-01T00:00:00Z",
        "summary": {"status": "ok"},
    }

    exporters.persist_report_pdf(path, payload)

    assert path.exists()
    assert path.read_bytes().startswith(b"%PDF-1.4")


def test_pipeline_trace_session_noop_stage_records_duration(monkeypatch) -> None:
    """Trace session records stage duration even when OTel tracing is disabled."""
    monkeypatch.delenv("VERITAS_ENABLE_OTEL_TRACE", raising=False)
    session = exporters.PipelineTraceSession.start(request_id="req-1", user_id="u-1")

    with session.stage("input_norm"):
        pass

    assert "input_norm" in session._stage_durations_ms
    assert session._stage_durations_ms["input_norm"] >= 0


def test_pipeline_trace_session_falls_back_when_otel_missing(monkeypatch) -> None:
    """Missing OpenTelemetry package must not break pipeline tracing setup."""
    monkeypatch.setenv("VERITAS_ENABLE_OTEL_TRACE", "1")
    monkeypatch.setitem(sys.modules, "opentelemetry", None)

    session = exporters.PipelineTraceSession.start(request_id="req-2", user_id="u-2")
    with session.stage("kernel_execute"):
        pass
    session.finalize(decision_status="allow", stage_failures=[])

    assert session._enabled is False
