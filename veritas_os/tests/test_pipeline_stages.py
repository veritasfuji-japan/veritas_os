"""Tests for new pipeline stage modules introduced during refactoring.

These tests verify that the extracted stage modules work correctly in isolation
while the existing integration tests (test_decide_pipeline_core_extra.py etc.)
continue to exercise the full orchestration path.
"""
from __future__ import annotations

import time
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from veritas_os.core.pipeline_types import PipelineContext, BASE_TELOS_THRESHOLD


# =========================================================
# pipeline_types: PipelineContext
# =========================================================


class TestPipelineContext:
    """PipelineContext dataclass creation and defaults."""

    def test_default_values(self) -> None:
        ctx = PipelineContext()
        assert ctx.query == ""
        assert ctx.user_id == "anon"
        assert ctx.fast_mode is False
        assert ctx.replay_mode is False
        assert ctx.decision_status == "allow"
        assert ctx.rejection_reason is None
        assert ctx.telos_threshold == BASE_TELOS_THRESHOLD
        assert isinstance(ctx.evidence, list)
        assert isinstance(ctx.alternatives, list)
        assert isinstance(ctx.response_extras, dict)
        assert isinstance(ctx.healing_attempts, list)

    def test_custom_values(self) -> None:
        ctx = PipelineContext(
            query="test query",
            user_id="user-1",
            fast_mode=True,
            replay_mode=True,
            decision_status="rejected",
        )
        assert ctx.query == "test query"
        assert ctx.user_id == "user-1"
        assert ctx.fast_mode is True
        assert ctx.replay_mode is True
        assert ctx.decision_status == "rejected"

    def test_mutable_defaults_isolated(self) -> None:
        """Each PipelineContext instance should have its own mutable containers."""
        ctx1 = PipelineContext()
        ctx2 = PipelineContext()
        ctx1.evidence.append({"source": "test"})
        assert len(ctx2.evidence) == 0


# =========================================================
# pipeline_inputs: normalize_pipeline_inputs
# =========================================================


class TestNormalizePipelineInputs:
    """Input normalization stage."""

    def test_basic_normalization(self) -> None:
        from veritas_os.core.pipeline_inputs import normalize_pipeline_inputs

        class DummyReq:
            def model_dump(self):
                return {"query": "  hello world  ", "context": {}}

        class DummyRequest:
            query_params: Dict[str, Any] = {}

        ctx = normalize_pipeline_inputs(DummyReq(), DummyRequest())
        assert ctx.query == "hello world"
        assert isinstance(ctx.request_id, str)
        assert len(ctx.request_id) > 0
        assert ctx.fast_mode is False
        assert ctx.replay_mode is False

    def test_fast_mode_from_body(self) -> None:
        from veritas_os.core.pipeline_inputs import normalize_pipeline_inputs

        class DummyReq:
            def model_dump(self):
                return {"query": "test", "fast": True, "context": {}}

        class DummyRequest:
            query_params: Dict[str, Any] = {}

        ctx = normalize_pipeline_inputs(DummyReq(), DummyRequest())
        assert ctx.fast_mode is True

    def test_replay_mode_from_context(self) -> None:
        from veritas_os.core.pipeline_inputs import normalize_pipeline_inputs

        class DummyReq:
            def model_dump(self):
                return {"query": "test", "context": {"_replay_mode": True}}

        class DummyRequest:
            query_params: Dict[str, Any] = {}

        ctx = normalize_pipeline_inputs(DummyReq(), DummyRequest())
        assert ctx.replay_mode is True
        assert ctx.mock_external_apis is True

    def test_private_fields_stripped(self) -> None:
        from veritas_os.core.pipeline_inputs import normalize_pipeline_inputs

        class DummyReq:
            def model_dump(self):
                return {
                    "query": "test",
                    "context": {
                        "_pipeline_secret": "evil",
                        "_orchestrated_by_pipeline": True,
                        "safe_field": "ok",
                    },
                }

        class DummyRequest:
            query_params: Dict[str, Any] = {}

        ctx = normalize_pipeline_inputs(DummyReq(), DummyRequest())
        assert "_pipeline_secret" not in ctx.context
        assert "_orchestrated_by_pipeline" not in ctx.context
        assert ctx.context.get("safe_field") == "ok"

    def test_user_id_always_string(self) -> None:
        from veritas_os.core.pipeline_inputs import normalize_pipeline_inputs

        class DummyReq:
            def model_dump(self):
                return {"query": "test", "context": {"user_id": 12345}}

        class DummyRequest:
            query_params: Dict[str, Any] = {}

        ctx = normalize_pipeline_inputs(DummyReq(), DummyRequest())
        assert ctx.user_id == "12345"
        assert isinstance(ctx.user_id, str)


# =========================================================
# pipeline_replay: replay functions
# =========================================================


class TestPipelineReplay:
    """Replay helper functions."""

    def test_sanitize_for_diff_removes_volatile(self) -> None:
        from veritas_os.core.pipeline_replay import _sanitize_for_diff

        data = {
            "query": "test",
            "created_at": "2025-01-01",
            "latency_ms": 42,
            "chosen": {"title": "A"},
        }
        result = _sanitize_for_diff(data)
        assert "query" in result
        assert "chosen" in result
        assert "created_at" not in result
        assert "latency_ms" not in result

    def test_build_replay_diff_no_change(self) -> None:
        from veritas_os.core.pipeline_replay import _build_replay_diff

        original = {"query": "test", "chosen": {"title": "A"}}
        replayed = {"query": "test", "chosen": {"title": "A"}}
        diff = _build_replay_diff(original, replayed)
        assert diff["changed"] is False
        assert diff["summary"] == "no_diff"

    def test_build_replay_diff_with_changes(self) -> None:
        from veritas_os.core.pipeline_replay import _build_replay_diff

        original = {"query": "test", "chosen": {"title": "A"}}
        replayed = {"query": "test", "chosen": {"title": "B"}}
        diff = _build_replay_diff(original, replayed)
        assert diff["changed"] is True
        assert "chosen" in diff["keys"]

    def test_safe_filename_id(self) -> None:
        from veritas_os.core.pipeline_replay import _safe_filename_id

        assert _safe_filename_id("abc-123_def") == "abc-123_def"
        assert "/" not in _safe_filename_id("../../etc/passwd")
        assert len(_safe_filename_id("x" * 200)) <= 128

    def test_replay_request_has_query_params(self) -> None:
        from veritas_os.core.pipeline_replay import _ReplayRequest

        req = _ReplayRequest()
        assert isinstance(req.query_params, dict)


# =========================================================
# pipeline_response: assemble_response
# =========================================================


class TestAssembleResponse:
    """Response assembly stage."""

    def test_basic_assembly(self) -> None:
        from veritas_os.core.pipeline_response import assemble_response

        ctx = PipelineContext(
            query="test",
            request_id="req-1",
            chosen={"title": "A"},
            alternatives=[{"title": "A"}, {"title": "B"}],
            decision_status="allow",
        )
        res = assemble_response(
            ctx,
            load_persona_fn=lambda: {"name": "test"},
            plan={"steps": []},
        )
        assert res["ok"] is True
        assert res["query"] == "test"
        assert res["request_id"] == "req-1"
        assert res["chosen"] == {"title": "A"}
        assert len(res["alternatives"]) == 2
        assert res["decision_status"] == "allow"
        assert res["gate"]["decision_status"] == "allow"


# =========================================================
# pipeline_policy: stage_gate_decision
# =========================================================


class TestStageGateDecision:
    """Gate decision stage."""

    def test_allow_by_default(self) -> None:
        from veritas_os.core.pipeline_policy import stage_gate_decision

        ctx = PipelineContext(
            fuji_dict={"status": "allow", "risk": 0.1},
            response_extras={"metrics": {"stage_latency": {"gate": 0}}},
        )
        stage_gate_decision(ctx)
        assert ctx.decision_status == "allow"
        assert ctx.rejection_reason is None

    def test_rejected_on_fuji_rejected(self) -> None:
        from veritas_os.core.pipeline_policy import stage_gate_decision

        ctx = PipelineContext(
            fuji_dict={"status": "rejected", "reasons": ["policy_violation"]},
            response_extras={"metrics": {"stage_latency": {"gate": 0}}},
        )
        stage_gate_decision(ctx)
        assert ctx.decision_status == "rejected"
        assert "FUJI gate" in (ctx.rejection_reason or "")


# =========================================================
# pipeline_persist: persist_audit_log
# =========================================================


class TestPersistAuditLog:
    """Audit log persistence (best-effort, should not raise)."""

    def test_audit_log_called(self) -> None:
        from veritas_os.core.pipeline_persist import persist_audit_log

        log_entries = []
        shadow_calls = []

        ctx = PipelineContext(
            query="test",
            request_id="req-1",
            body={"query": "test"},
            chosen={"title": "A"},
        )
        persist_audit_log(
            ctx,
            append_trust_log_fn=lambda e: log_entries.append(e),
            write_shadow_decide_fn=lambda *args: shadow_calls.append(args),
        )
        assert len(log_entries) == 1
        assert log_entries[0]["request_id"] == "req-1"
        assert len(shadow_calls) == 1

    def test_audit_log_resilient_to_errors(self) -> None:
        from veritas_os.core.pipeline_persist import persist_audit_log

        def _raise(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("boom")

        ctx = PipelineContext(query="test", request_id="req-1")
        # Should not raise even if callbacks fail
        persist_audit_log(
            ctx,
            append_trust_log_fn=_raise,
            write_shadow_decide_fn=lambda *a: None,
        )


# =========================================================
# pipeline_response: finalize_evidence
# =========================================================


class TestFinalizeEvidence:
    """Evidence finalization / dedup / cap."""

    def test_caps_evidence(self) -> None:
        from veritas_os.core.pipeline_response import finalize_evidence

        payload: Dict[str, Any] = {
            "evidence": [
                {"source": "web", "uri": f"http://x.com/{i}", "snippet": f"s{i}", "confidence": 0.5}
                for i in range(100)
            ]
        }
        finalize_evidence(payload, web_evidence=[], evidence_max=10)
        assert len(payload["evidence"]) <= 10

    def test_merges_web_evidence(self) -> None:
        from veritas_os.core.pipeline_response import finalize_evidence

        payload: Dict[str, Any] = {
            "evidence": [
                {"source": "memory:semantic", "uri": "mem-1", "snippet": "mem", "confidence": 0.8}
            ]
        }
        web_ev = [
            {"source": "web", "uri": "http://example.com", "snippet": "web result", "confidence": 0.7}
        ]
        finalize_evidence(payload, web_evidence=web_ev, evidence_max=50)
        sources = [e.get("source") for e in payload["evidence"]]
        assert "web" in sources


def test_build_replay_snapshot_includes_external_dependency_versions() -> None:
    from veritas_os.core.pipeline_persist import build_replay_snapshot
    from veritas_os.core.pipeline_types import PipelineContext

    ctx = PipelineContext(
        request_id="req-1",
        query="q",
        body={"temperature": 0},
        context={},
    )
    ctx.retrieved = []
    ctx.response_extras = {"web_search": None}
    ctx.seed = 123

    payload = {"meta": {}, "evidence": []}
    build_replay_snapshot(ctx, payload, should_run_web=False)

    replay = payload.get("deterministic_replay")
    assert isinstance(replay, dict)
    deps = replay.get("external_dependency_versions")
    assert isinstance(deps, dict)
    assert isinstance(deps.get("packages"), dict)
    assert "python_version" in deps
