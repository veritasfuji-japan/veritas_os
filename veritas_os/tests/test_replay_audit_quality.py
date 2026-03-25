"""Tests for replay audit-quality improvements: schema versioning, severity, divergence, audit summary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from veritas_os.replay import replay_engine
from veritas_os.replay.replay_engine import (
    DIVERGENCE_ACCEPTABLE,
    DIVERGENCE_CRITICAL,
    DIVERGENCE_NONE,
    REPLAY_SCHEMA_VERSION,
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    _audit_summary,
    _build_diff,
    _classify_field_severity,
    _determine_divergence,
)


# ── Unit tests: _classify_field_severity ──────────────────────────────


class TestClassifyFieldSeverity:
    def test_decision_is_critical(self) -> None:
        assert _classify_field_severity("decision") == SEVERITY_CRITICAL

    def test_fuji_is_critical(self) -> None:
        assert _classify_field_severity("fuji") == SEVERITY_CRITICAL

    def test_value_scores_is_warning(self) -> None:
        assert _classify_field_severity("value_scores") == SEVERITY_WARNING

    def test_evidence_is_info(self) -> None:
        assert _classify_field_severity("evidence") == SEVERITY_INFO

    def test_unknown_field_defaults_to_info(self) -> None:
        assert _classify_field_severity("some_custom_field") == SEVERITY_INFO


# ── Unit tests: _determine_divergence ─────────────────────────────────


class TestDetermineDivergence:
    def test_empty_yields_no_divergence(self) -> None:
        assert _determine_divergence([]) == DIVERGENCE_NONE

    def test_critical_yields_critical_divergence(self) -> None:
        assert _determine_divergence([SEVERITY_CRITICAL, SEVERITY_INFO]) == DIVERGENCE_CRITICAL

    def test_warning_only_yields_acceptable(self) -> None:
        assert _determine_divergence([SEVERITY_WARNING]) == DIVERGENCE_ACCEPTABLE

    def test_info_only_yields_acceptable(self) -> None:
        assert _determine_divergence([SEVERITY_INFO]) == DIVERGENCE_ACCEPTABLE

    def test_mixed_warning_info_yields_acceptable(self) -> None:
        assert _determine_divergence([SEVERITY_WARNING, SEVERITY_INFO]) == DIVERGENCE_ACCEPTABLE


# ── Unit tests: _build_diff with severity ─────────────────────────────


class TestBuildDiffSeverity:
    def test_no_changes_produces_info_severity_and_no_divergence(self) -> None:
        before = {"decision": {"output": "allow"}, "evidence": []}
        diff = _build_diff(before, before)
        assert diff["fields_changed"] == []
        assert diff["max_severity"] == SEVERITY_INFO
        assert diff["divergence_level"] == DIVERGENCE_NONE
        assert diff["field_details"] == []

    def test_decision_change_is_critical(self) -> None:
        before = {"decision": {"output": "allow"}, "evidence": []}
        after = {"decision": {"output": "reject"}, "evidence": []}
        diff = _build_diff(before, after)

        assert "decision" in diff["fields_changed"]
        assert diff["max_severity"] == SEVERITY_CRITICAL
        assert diff["divergence_level"] == DIVERGENCE_CRITICAL

        details = {d["field"]: d for d in diff["field_details"]}
        assert details["decision"]["severity"] == SEVERITY_CRITICAL

    def test_evidence_only_change_is_acceptable(self) -> None:
        before = {"evidence": [{"id": "1"}]}
        after = {"evidence": [{"id": "2"}]}
        diff = _build_diff(before, after)

        assert diff["max_severity"] == SEVERITY_INFO
        assert diff["divergence_level"] == DIVERGENCE_ACCEPTABLE

    def test_value_scores_change_yields_warning(self) -> None:
        before = {"value_scores": {"safety": 0.9}}
        after = {"value_scores": {"safety": 0.3}}
        diff = _build_diff(before, after)

        assert diff["max_severity"] == SEVERITY_WARNING
        assert diff["divergence_level"] == DIVERGENCE_ACCEPTABLE

    def test_mixed_severity_picks_max(self) -> None:
        before = {"decision": {"output": "allow"}, "value_scores": {"safety": 0.9}, "evidence": []}
        after = {"decision": {"output": "reject"}, "value_scores": {"safety": 0.3}, "evidence": [{"id": "x"}]}
        diff = _build_diff(before, after)

        assert diff["max_severity"] == SEVERITY_CRITICAL
        assert diff["divergence_level"] == DIVERGENCE_CRITICAL
        assert len(diff["field_details"]) == 3


# ── Unit tests: _audit_summary ────────────────────────────────────────


class TestAuditSummary:
    def test_match_summary(self) -> None:
        diff = {"divergence_level": DIVERGENCE_NONE, "max_severity": SEVERITY_INFO, "high_level": []}
        summary = _audit_summary(decision_id="dec-1", match=True, strict=True, diff=diff)
        assert "MATCH" in summary
        assert "no divergence" in summary
        assert "strict" in summary

    def test_mismatch_critical_summary(self) -> None:
        diff = {
            "divergence_level": DIVERGENCE_CRITICAL,
            "max_severity": SEVERITY_CRITICAL,
            "high_level": ["Decision output differs.", "Fuji result differs."],
        }
        summary = _audit_summary(decision_id="dec-2", match=False, strict=False, diff=diff)
        assert "MISMATCH" in summary
        assert "critical" in summary
        assert "Decision output differs." in summary

    def test_mismatch_acceptable_summary(self) -> None:
        diff = {
            "divergence_level": DIVERGENCE_ACCEPTABLE,
            "max_severity": SEVERITY_INFO,
            "high_level": ["Evidence set differs."],
        }
        summary = _audit_summary(decision_id="dec-3", match=False, strict=True, diff=diff)
        assert "MISMATCH" in summary
        assert "Evidence set differs." in summary


# ── Integration test: run_replay populates new fields ─────────────────


@pytest.mark.asyncio
async def test_run_replay_populates_schema_version_and_severity(
    monkeypatch, tmp_path: Path,
) -> None:
    """run_replay should include schema_version, severity, divergence_level, and audit_summary."""
    snapshot = {
        "request_id": "dec-audit-1",
        "query": "test",
        "deterministic_replay": {
            "model_version": "gpt-5-thinking",
            "seed": 1,
            "temperature": 0,
            "request_body": {"query": "test", "context": {}},
            "final_output": {
                "decision": {"output": "allow", "answer": "ok"},
                "fuji": {"result": "allow", "status": "allow"},
                "value_scores": {"safety": 0.9},
                "evidence": [],
            },
        },
    }

    async def _fake_run(_req, _request, **_kw):
        return {
            "decision": {"output": "reject", "answer": "ng"},
            "fuji": {"result": "reject", "status": "reject"},
            "value_scores": {"safety": 0.2},
            "evidence": [],
        }

    monkeypatch.setattr(replay_engine.pipeline, "_load_persisted_decision", lambda _id: snapshot)
    monkeypatch.setattr(replay_engine.pipeline, "run_decide_pipeline", _fake_run)
    monkeypatch.setattr(replay_engine.pipeline, "REPLAY_REPORT_DIR", tmp_path)
    monkeypatch.setenv("VERITAS_MODEL_NAME", "gpt-5-thinking")

    result = await replay_engine.run_replay("dec-audit-1", strict=False)

    # New fields populated
    assert result.schema_version == REPLAY_SCHEMA_VERSION
    assert result.severity == SEVERITY_CRITICAL
    assert result.divergence_level == DIVERGENCE_CRITICAL
    assert "MISMATCH" in result.audit_summary
    assert "critical" in result.audit_summary
    assert result.match is False

    # Report file includes new fields
    report = json.loads(Path(result.replay_path).read_text(encoding="utf-8"))
    assert report["schema_version"] == REPLAY_SCHEMA_VERSION
    assert report["severity"] == SEVERITY_CRITICAL
    assert report["divergence_level"] == DIVERGENCE_CRITICAL
    assert report["audit_summary"] == result.audit_summary


@pytest.mark.asyncio
async def test_run_replay_match_has_no_divergence(
    monkeypatch, tmp_path: Path,
) -> None:
    """A matching replay should report no_divergence and info severity."""
    snapshot = {
        "request_id": "dec-match-1",
        "query": "hello",
        "deterministic_replay": {
            "model_version": "gpt-5-thinking",
            "seed": 42,
            "temperature": 0,
            "request_body": {"query": "hello", "context": {}},
            "final_output": {
                "decision": {"output": "allow", "answer": "ok"},
                "fuji": {"result": "allow", "status": "allow"},
                "value_scores": {"safety": 0.9},
                "evidence": [],
            },
        },
    }

    async def _fake_run(_req, _request, **_kw):
        return {
            "decision": {"output": "allow", "answer": "ok"},
            "fuji": {"result": "allow", "status": "allow"},
            "value_scores": {"safety": 0.9},
            "evidence": [],
        }

    monkeypatch.setattr(replay_engine.pipeline, "_load_persisted_decision", lambda _id: snapshot)
    monkeypatch.setattr(replay_engine.pipeline, "run_decide_pipeline", _fake_run)
    monkeypatch.setattr(replay_engine.pipeline, "REPLAY_REPORT_DIR", tmp_path)
    monkeypatch.setenv("VERITAS_MODEL_NAME", "gpt-5-thinking")

    result = await replay_engine.run_replay("dec-match-1", strict=True)

    assert result.match is True
    assert result.severity == SEVERITY_INFO
    assert result.divergence_level == DIVERGENCE_NONE
    assert "MATCH" in result.audit_summary
    assert "no divergence" in result.audit_summary


# ── pipeline_replay._build_replay_diff severity tests ────────────────


class TestPipelineReplayDiffSeverity:
    def test_no_diff_includes_severity(self) -> None:
        from veritas_os.core.pipeline_replay import _build_replay_diff

        diff = _build_replay_diff({"a": 1}, {"a": 1})
        assert diff["severity"] == "info"
        assert diff["divergence_level"] == "no_divergence"

    def test_critical_key_change(self) -> None:
        from veritas_os.core.pipeline_replay import _build_replay_diff

        diff = _build_replay_diff(
            {"decision": "allow", "meta": {}},
            {"decision": "reject", "meta": {}},
        )
        assert diff["severity"] == "critical"
        assert diff["divergence_level"] == "critical_divergence"

    def test_non_critical_key_change(self) -> None:
        from veritas_os.core.pipeline_replay import _build_replay_diff

        diff = _build_replay_diff(
            {"evidence": [1]},
            {"evidence": [2]},
        )
        assert diff["severity"] == "info"
        assert diff["divergence_level"] == "acceptable_divergence"
