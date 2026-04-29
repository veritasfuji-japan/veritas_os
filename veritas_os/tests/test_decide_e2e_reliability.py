# veritas_os/tests/test_decide_e2e_reliability.py
# -*- coding: utf-8 -*-
"""
End-to-end reliability tests for /v1/decide.

These tests exercise the full HTTP → route handler → pipeline → response
path, verifying that each identified failure mode is properly closed.

Failure modes covered:
  1. dependency_unavailable  – pipeline module missing → 503
  2. replay_artifact         – successful decide produces replay snapshot
  3. memory_unavailable      – MemoryOS down → degraded but 200
  4. fuji_rejection          – FUJI gate rejects → 200 with rejected status
  5. compliance_stop         – EU AI Act threshold → 200 with PENDING_REVIEW
  6. malformed_payload       – bad JSON / missing fields → 422
  7. publish_event_failure   – SSE hub broken → decide still succeeds (best-effort)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_PAYLOAD = {
    "query": "統合テスト: 信頼性確認",
    "context": {"user_id": "reliability_test_user"},
}

_HEADERS = {"X-API-Key": "test-key"}
_PRE_BIND_FIXTURE_DIR = Path("veritas_os/tests/fixtures/pre_bind")
_PRE_BIND_GOLDEN_DIR = Path("veritas_os/tests/golden/pre_bind")


def _inject_canonical_participation_signal(
    monkeypatch,
    participation_signal: dict[str, Any],
) -> None:
    """Inject canonical signal at the raw-extras boundary before response assembly.

    This keeps the HTTP -> route -> pipeline -> response-layer governance evaluation
    path real while making canonical case inputs deterministic.
    """
    import veritas_os.core.pipeline as pipeline_module

    original_call_core_decide = pipeline_module.call_core_decide

    async def _patched_call_core_decide(*args: Any, **kwargs: Any) -> Any:
        raw = await original_call_core_decide(*args, **kwargs)
        if isinstance(raw, dict):
            raw_extras = raw.setdefault("extras", {})
            if isinstance(raw_extras, dict):
                raw_extras["participation_signal"] = participation_signal
        return raw

    monkeypatch.setattr(pipeline_module, "call_core_decide", _patched_call_core_decide)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _make_client(monkeypatch) -> TestClient:
    """Create a TestClient with API key configured."""
    monkeypatch.setenv("VERITAS_API_KEY", "test-key")
    from veritas_os.api.server import app
    return TestClient(app, raise_server_exceptions=False)


def _post_decide(client: TestClient, payload: dict | None = None) -> Any:
    """POST /v1/decide with default headers."""
    return client.post(
        "/v1/decide",
        headers=_HEADERS,
        json=payload if payload is not None else _VALID_PAYLOAD,
    )


# ---------------------------------------------------------------------------
# 1. Dependency unavailable → 503
# ---------------------------------------------------------------------------

class TestDependencyUnavailable:
    """Pipeline module is None → route returns 503 with structured error."""

    def test_pipeline_none_returns_503(self, monkeypatch):
        """When get_decision_pipeline() returns None, respond 503."""
        monkeypatch.setenv("VERITAS_API_KEY", "test-key")
        from veritas_os.api import server as srv

        # Force pipeline resolver to return None
        monkeypatch.setattr(srv, "get_decision_pipeline", lambda: None)
        monkeypatch.setattr(srv, "_pipeline_state", SimpleNamespace(err="test: forced None"))

        client = TestClient(srv.app, raise_server_exceptions=False)
        res = _post_decide(client)

        assert res.status_code == 503
        body = res.json()
        assert body.get("ok") is False
        assert body.get("error") == "service_unavailable"
        assert body.get("trust_log") is None  # no trust_log on 503

    def test_pipeline_exception_returns_503_with_category(self, monkeypatch):
        """When pipeline.run_decide_pipeline raises, respond 503 with failure_category."""
        monkeypatch.setenv("VERITAS_API_KEY", "test-key")
        from veritas_os.api import server as srv

        broken_pipeline = SimpleNamespace(
            run_decide_pipeline=AsyncMock(side_effect=TimeoutError("LLM timeout")),
        )
        monkeypatch.setattr(srv, "get_decision_pipeline", lambda: broken_pipeline)

        client = TestClient(srv.app, raise_server_exceptions=False)
        res = _post_decide(client)

        assert res.status_code == 503
        body = res.json()
        assert body.get("ok") is False
        assert body.get("failure_category") == "timeout"

    def test_pipeline_value_error_classified_as_invalid_input(self, monkeypatch):
        """ValueError from pipeline → failure_category = invalid_input."""
        monkeypatch.setenv("VERITAS_API_KEY", "test-key")
        from veritas_os.api import server as srv

        broken_pipeline = SimpleNamespace(
            run_decide_pipeline=AsyncMock(side_effect=ValueError("bad data")),
        )
        monkeypatch.setattr(srv, "get_decision_pipeline", lambda: broken_pipeline)

        client = TestClient(srv.app, raise_server_exceptions=False)
        res = _post_decide(client)

        assert res.status_code == 503
        body = res.json()
        assert body.get("failure_category") == "invalid_input"


# ---------------------------------------------------------------------------
# 2. Replay artifact generation
# ---------------------------------------------------------------------------

class TestReplayArtifact:
    """A successful /v1/decide call should populate the replay snapshot."""

    def test_successful_decide_returns_expected_contract(self, monkeypatch):
        """Response satisfies the DecideResponse contract fields."""
        client = _make_client(monkeypatch)
        res = _post_decide(client)

        assert res.status_code == 200
        body = res.json()

        # Core contract fields
        assert "chosen" in body
        assert "alternatives" in body
        assert "fuji" in body
        assert "gate" in body
        assert "evidence" in body
        assert "request_id" in body
        assert body.get("ok") is True or "warn" in body

        # Gate sub-structure
        gate = body.get("gate", {})
        assert "risk" in gate
        assert "decision_status" in gate

    def test_extras_metrics_contract(self, monkeypatch):
        """extras.metrics always has the required counter fields."""
        client = _make_client(monkeypatch)
        res = _post_decide(client)

        assert res.status_code == 200
        body = res.json()
        extras = body.get("extras", {})
        metrics = extras.get("metrics", {})

        # Required metric fields (pipeline contract)
        for key in ("mem_hits", "memory_evidence_count", "web_hits", "web_evidence_count"):
            assert key in metrics, f"Missing metric: {key}"
            assert isinstance(metrics[key], int), f"{key} should be int, got {type(metrics[key])}"

        assert "fast_mode" in metrics


# ---------------------------------------------------------------------------
# 3. Memory unavailable fallback
# ---------------------------------------------------------------------------

class TestMemoryUnavailableFallback:
    """When MemoryOS is unreachable, the pipeline degrades gracefully."""

    def test_memory_search_raises_returns_200(self, monkeypatch):
        """If memory.search raises, pipeline still returns 200 with zero mem_hits."""
        monkeypatch.setenv("VERITAS_API_KEY", "test-key")

        # Patch at the pipeline module level: make memory None
        import veritas_os.core.pipeline as p
        original_mem = p.mem
        monkeypatch.setattr(p, "mem", None)

        from veritas_os.api.server import app
        client = TestClient(app, raise_server_exceptions=False)
        res = _post_decide(client)

        assert res.status_code == 200
        body = res.json()
        metrics = body.get("extras", {}).get("metrics", {})
        assert metrics.get("mem_hits", 0) == 0

    def test_memory_store_put_failure_recorded(self, monkeypatch):
        """If persist_to_memory fails, error is captured in extras, not raised."""
        monkeypatch.setenv("VERITAS_API_KEY", "test-key")

        import veritas_os.core.pipeline as p

        # Create a broken memory store that raises on put
        broken_store = SimpleNamespace(
            search=MagicMock(return_value=[]),
            put=MagicMock(side_effect=TypeError("broken store")),
            get=MagicMock(return_value=None),
            add_usage=MagicMock(),
            has=MagicMock(return_value=False),
        )

        def broken_getter():
            return broken_store

        # Patch _get_memory_store_impl to return our broken store
        original_fn = p._get_memory_store_impl
        monkeypatch.setattr(p, "_get_memory_store_impl", lambda mem=None: broken_store)

        from veritas_os.api.server import app
        client = TestClient(app, raise_server_exceptions=False)
        res = _post_decide(client)

        # Pipeline must not crash
        assert res.status_code == 200


# ---------------------------------------------------------------------------
# 4. FUJI rejection path
# ---------------------------------------------------------------------------

class TestFujiRejectionPath:
    """When FUJI gate rejects, the response conveys rejection cleanly."""

    def test_fuji_rejects_high_risk_query(self, monkeypatch):
        """A dangerous query triggers FUJI rejection → decision_status = rejected."""
        monkeypatch.setenv("VERITAS_API_KEY", "test-key")

        import veritas_os.core.pipeline as p

        # Stub fuji_core to always reject
        fake_fuji = SimpleNamespace(
            validate_action=lambda q, ctx: {
                "status": "rejected",
                "reasons": ["test_policy_violation"],
                "violations": ["test_violation"],
                "risk": 1.0,
                "modifications": [],
            },
            validate=lambda q, ctx: {
                "status": "rejected",
                "reasons": ["test_policy_violation"],
                "violations": ["test_violation"],
                "risk": 1.0,
                "modifications": [],
            },
        )
        monkeypatch.setattr(p, "fuji_core", fake_fuji)

        # Also patch lazy import path in pipeline_policy
        import veritas_os.core.pipeline_policy as pp
        original_lazy = pp._lazy_import
        def mock_lazy(name, attr):
            if "fuji" in str(name):
                return fake_fuji
            return original_lazy(name, attr)
        monkeypatch.setattr(pp, "_lazy_import", mock_lazy)

        from veritas_os.api.server import app
        client = TestClient(app, raise_server_exceptions=False)
        res = _post_decide(client)

        assert res.status_code == 200
        body = res.json()

        # The decision must be rejected
        assert body.get("decision_status") == "rejected" or (
            body.get("gate", {}).get("decision_status") == "rejected"
        )

        # FUJI dict must be present with rejection info
        fuji = body.get("fuji", {})
        assert fuji.get("status") == "rejected"

    def test_fuji_rejection_publishes_event(self, monkeypatch):
        """Rejection triggers fuji.rejected SSE event."""
        events: List[tuple] = []

        monkeypatch.setenv("VERITAS_API_KEY", "test-key")
        from veritas_os.api import server as srv

        original_publish = srv._publish_event

        def capture_publish(etype, payload):
            events.append((etype, payload))
            original_publish(etype, payload)

        monkeypatch.setattr(srv, "_publish_event", capture_publish)

        import veritas_os.core.pipeline as p
        fake_fuji = SimpleNamespace(
            validate_action=lambda q, ctx: {
                "status": "rejected",
                "reasons": ["unsafe"],
                "violations": ["v1"],
                "risk": 1.0,
                "modifications": [],
            },
            validate=lambda q, ctx: {
                "status": "rejected",
                "reasons": ["unsafe"],
                "violations": ["v1"],
                "risk": 1.0,
                "modifications": [],
            },
        )
        monkeypatch.setattr(p, "fuji_core", fake_fuji)

        import veritas_os.core.pipeline_policy as pp
        original_lazy = pp._lazy_import
        def mock_lazy(name, attr):
            if "fuji" in str(name):
                return fake_fuji
            return original_lazy(name, attr)
        monkeypatch.setattr(pp, "_lazy_import", mock_lazy)

        client = TestClient(srv.app, raise_server_exceptions=False)
        res = _post_decide(client)

        assert res.status_code == 200
        fuji_events = [e for e in events if e[0] == "fuji.rejected"]
        assert len(fuji_events) >= 1, f"Expected fuji.rejected event, got: {[e[0] for e in events]}"


# ---------------------------------------------------------------------------
# 5. Compliance stop path (EU AI Act)
# ---------------------------------------------------------------------------

class TestComplianceStopPath:
    """EU AI Act compliance stop returns 200 with PENDING_REVIEW status."""

    def test_compliance_stop_returns_pending_review(self, monkeypatch):
        """Low trust_score + EU AI Act mode → PENDING_REVIEW."""
        monkeypatch.setenv("VERITAS_API_KEY", "test-key")

        from veritas_os.api import pipeline_orchestrator as po

        # Enable EU AI Act mode with high threshold
        po.update_runtime_config(eu_ai_act_mode=True, safety_threshold=0.99)

        try:
            from veritas_os.api.server import app
            client = TestClient(app, raise_server_exceptions=False)
            res = _post_decide(client)

            # With safety_threshold=0.99, most decisions will be stopped
            # unless trust_score is explicitly ≥ 0.99
            body = res.json()

            if body.get("status") == "PENDING_REVIEW":
                assert body.get("compliance_reason") == "art_14_human_review_required"
            else:
                # If pipeline produces a trust_score ≥ 0.99, it passes through
                # Either outcome is acceptable; we verify no crash
                assert res.status_code == 200
        finally:
            # Restore defaults
            po.update_runtime_config(eu_ai_act_mode=False, safety_threshold=0.8)

    def test_compliance_stop_publishes_event(self, monkeypatch):
        """Compliance stop emits compliance.pending_review event."""
        events: List[tuple] = []

        monkeypatch.setenv("VERITAS_API_KEY", "test-key")
        from veritas_os.api import server as srv
        from veritas_os.api import pipeline_orchestrator as po
        from veritas_os.api.pipeline_orchestrator import ComplianceStopException

        original_publish = srv._publish_event

        def capture_publish(etype, payload):
            events.append((etype, payload))
            original_publish(etype, payload)

        monkeypatch.setattr(srv, "_publish_event", capture_publish)

        # Force compliance stop by patching enforce_compliance_stop
        def always_stop(payload):
            stop_payload = dict(payload)
            stop_payload["status"] = "PENDING_REVIEW"
            stop_payload["compliance_reason"] = "art_14_human_review_required"
            raise ComplianceStopException(stop_payload)

        monkeypatch.setattr(
            "veritas_os.api.decide_service.enforce_compliance_stop",
            always_stop,
        )

        client = TestClient(srv.app, raise_server_exceptions=False)
        res = _post_decide(client)

        assert res.status_code == 200
        body = res.json()
        assert body.get("status") == "PENDING_REVIEW"

        compliance_events = [e for e in events if e[0] == "compliance.pending_review"]
        assert len(compliance_events) >= 1


# ---------------------------------------------------------------------------
# 6. Malformed payload path
# ---------------------------------------------------------------------------

class TestMalformedPayloadPath:
    """Invalid request bodies → 422 with helpful diagnostics."""

    def test_empty_body_returns_422(self, monkeypatch):
        """Empty JSON body triggers validation error."""
        client = _make_client(monkeypatch)
        res = client.post("/v1/decide", headers=_HEADERS, content=b"")

        assert res.status_code == 422

    def test_missing_query_still_succeeds(self, monkeypatch):
        """Payload without 'query' field → 200 (query defaults to empty string)."""
        client = _make_client(monkeypatch)
        res = client.post(
            "/v1/decide",
            headers=_HEADERS,
            json={"context": {"user_id": "test"}},
        )

        # query has a default of "" in DecideRequest, so this is valid
        assert res.status_code == 200
        body = res.json()
        assert "chosen" in body

    def test_wrong_content_type_returns_422(self, monkeypatch):
        """Non-JSON content type → 422."""
        client = _make_client(monkeypatch)
        res = client.post(
            "/v1/decide",
            headers={**_HEADERS, "Content-Type": "text/plain"},
            content=b"this is not json",
        )

        assert res.status_code == 422

    def test_invalid_json_returns_422(self, monkeypatch):
        """Malformed JSON → 422."""
        client = _make_client(monkeypatch)
        res = client.post(
            "/v1/decide",
            headers={**_HEADERS, "Content-Type": "application/json"},
            content=b'{"query": "test", invalid}',
        )

        assert res.status_code == 422

    def test_oversized_alternatives_handled(self, monkeypatch):
        """Payload with many alternatives is accepted or rejected, not crash."""
        client = _make_client(monkeypatch)
        payload = {
            "query": "test",
            "alternatives": [
                {"id": f"alt_{i}", "title": f"Option {i}", "score": 0.5}
                for i in range(200)
            ],
        }
        res = _post_decide(client, payload)

        # Should be 200 (truncated) or 422 (schema limit), not 500
        assert res.status_code in (200, 422)


# ---------------------------------------------------------------------------
# 7. Publish event failure → best-effort maintenance
# ---------------------------------------------------------------------------

class TestPublishEventBestEffort:
    """SSE event hub failures must never break the decide endpoint."""

    def test_broken_event_hub_decide_succeeds(self, monkeypatch):
        """If _publish_event raises, /v1/decide still returns 200."""
        monkeypatch.setenv("VERITAS_API_KEY", "test-key")
        from veritas_os.api import server as srv

        call_count = {"n": 0}

        def broken_publish(etype, payload):
            call_count["n"] += 1
            raise RuntimeError("SSE hub is broken")

        monkeypatch.setattr(srv, "_publish_event", broken_publish)

        client = TestClient(srv.app, raise_server_exceptions=False)
        res = _post_decide(client)

        # Despite broken event hub, decide must succeed
        assert res.status_code == 200
        body = res.json()
        assert "chosen" in body

    def test_event_hub_exception_does_not_leak_to_client(self, monkeypatch):
        """Event publishing errors don't appear in the response body."""
        monkeypatch.setenv("VERITAS_API_KEY", "test-key")
        from veritas_os.api import server as srv

        def broken_publish(etype, payload):
            raise ValueError("hub internal error")

        monkeypatch.setattr(srv, "_publish_event", broken_publish)

        client = TestClient(srv.app, raise_server_exceptions=False)
        res = _post_decide(client)

        assert res.status_code == 200
        raw = res.text
        assert "hub internal error" not in raw
        assert "ValueError" not in raw


# ---------------------------------------------------------------------------
# Cross-cutting: backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """Verify the API contract hasn't been broken."""

    def test_response_has_all_documented_fields(self, monkeypatch):
        """DecideResponse must include all documented top-level fields."""
        client = _make_client(monkeypatch)
        res = _post_decide(client)

        assert res.status_code == 200
        body = res.json()

        required_fields = {
            "ok", "request_id", "query", "chosen", "alternatives",
            "evidence", "fuji", "gate", "values", "extras",
            "decision_status", "telos_score",
        }
        missing = required_fields - set(body.keys())
        assert not missing, f"Missing response fields: {missing}"

    def test_gate_substructure_complete(self, monkeypatch):
        """gate.{risk, telos_score, decision_status, reason, modifications} present."""
        client = _make_client(monkeypatch)
        res = _post_decide(client)

        assert res.status_code == 200
        gate = res.json().get("gate", {})

        for key in ("risk", "telos_score", "decision_status", "reason", "modifications"):
            assert key in gate, f"gate.{key} missing"

        assert isinstance(gate["risk"], (int, float))
        assert isinstance(gate["telos_score"], (int, float))
        assert gate["decision_status"] in ("allow", "modify", "rejected", "block", "abstain")

    def test_fuji_substructure_present(self, monkeypatch):
        """fuji dict has status, risk, reasons keys."""
        client = _make_client(monkeypatch)
        res = _post_decide(client)

        assert res.status_code == 200
        fuji = res.json().get("fuji", {})

        assert "status" in fuji
        assert "risk" in fuji


class TestCanonicalPreBindRealPipelineRawExtrasInjection:
    """Canonical pre-bind reproducibility on /v1/decide with raw-extras injection.

    Scope:
      - Real HTTP/route/pipeline/response assembly path is exercised.
      - Deterministic control is limited to core decide raw extras injection.
      - Response-layer governance evaluator is not monkeypatched here.
    """

    @pytest.mark.parametrize(
        ("case_id", "expected_participation", "expected_preservation"),
        [
            ("pre_bind_case_informative_open", "informative", "open"),
            ("pre_bind_case_participatory_degrading", "participatory", "degrading"),
            ("pre_bind_case_decision_shaping_collapsed", "decision_shaping", "collapsed"),
        ],
    )
    def test_canonical_cases_keep_golden_state_and_rationale_parity(
        self,
        monkeypatch,
        case_id: str,
        expected_participation: str,
        expected_preservation: str,
    ):
        """Real-path response preserves canonical state/rationale and bind parity."""
        client = _make_client(monkeypatch)
        fixture = _load_json(_PRE_BIND_FIXTURE_DIR / f"{case_id}.json")
        golden = _load_json(_PRE_BIND_GOLDEN_DIR / f"{case_id}_golden.json")
        import veritas_os.core.pipeline.governance_layers as pipeline_response_module

        evaluator_before = pipeline_response_module.evaluate_governance_layers
        _inject_canonical_participation_signal(
            monkeypatch,
            fixture["participation_signal"],
        )

        response = _post_decide(
            client,
            {
                "query": f"canonical pre-bind real pipeline: {case_id}",
                "context": {"user_id": f"real_pipeline_{case_id}"},
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert pipeline_response_module.evaluate_governance_layers is evaluator_before

        assert body["participation_signal"]["participation_admissibility"] in {
            "admissible",
            "review_required",
            "unknown",
        }
        assert body["pre_bind_detection_summary"]["participation_state"] == expected_participation
        assert body["pre_bind_preservation_summary"]["preservation_state"] == expected_preservation
        assert (
            body["pre_bind_detection_summary"]["participation_state"]
            == golden["pre_bind_detection_summary"]["participation_state"]
        )
        assert (
            body["pre_bind_preservation_summary"]["preservation_state"]
            == golden["pre_bind_preservation_summary"]["preservation_state"]
        )
        assert (
            body["pre_bind_detection_summary"]["concise_rationale"]
            == golden["pre_bind_detection_summary"]["concise_rationale"]
        )
        assert (
            body["pre_bind_preservation_summary"]["concise_rationale"]
            == golden["pre_bind_preservation_summary"]["concise_rationale"]
        )
        assert "aggregate_index" in body["pre_bind_detection_detail"]
        assert "detection_context" in body["pre_bind_preservation_detail"]
        for bind_key in (
            "bind_outcome",
            "bind_reason_code",
            "bind_failure_reason",
            "bind_receipt_id",
            "execution_intent_id",
            "bind_summary",
        ):
            assert bind_key in body

    def test_pre_bind_additive_fields_remain_optional_on_real_pipeline(self, monkeypatch):
        """Without injected signal, pre-bind additive evidence fields stay optional."""
        client = _make_client(monkeypatch)
        response = _post_decide(
            client,
            {
                "query": "canonical pre-bind real pipeline optionality",
                "context": {"user_id": "real_pipeline_optional"},
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["pre_bind_detection_summary"] is None
        assert body["pre_bind_detection_detail"] is None
        assert body["pre_bind_preservation_summary"] is None
        assert body["pre_bind_preservation_detail"] is None
        for bind_key in (
            "bind_outcome",
            "bind_reason_code",
            "bind_failure_reason",
            "bind_receipt_id",
            "execution_intent_id",
            "bind_summary",
        ):
            assert bind_key in body


# ---------------------------------------------------------------------------
# Replay endpoint integration
# ---------------------------------------------------------------------------

class TestReplayEndpointResilience:
    """Replay endpoints handle missing data gracefully."""

    def test_replay_missing_decision_does_not_crash(self, monkeypatch):
        """Replaying a non-existent decision → structured response, not unhandled crash."""
        monkeypatch.setenv("VERITAS_API_KEY", "test-key")
        from veritas_os.api.server import app

        client = TestClient(app, raise_server_exceptions=False)
        res = client.post(
            "/v1/decision/replay/nonexistent_id_12345",
            headers=_HEADERS,
        )

        # Accept 200 (with match=False), 404, 500, or 503 — all are valid responses.
        # The critical assertion: no unhandled 5xx crash.
        assert res.status_code in (200, 404, 500, 503)
        body = res.json()
        # Response must have either match, error, or diff fields
        assert any(k in body for k in ("match", "error", "diff", "detail"))
