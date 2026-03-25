# veritas_os/tests/test_decide_service.py
"""Tests for veritas_os.api.decide_service — extracted service helpers."""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from veritas_os.api.decide_service import (
    apply_compliance_stop,
    check_fuji_rejection,
    error_response,
    publish_decide_completion,
    publish_stage_events,
    validate_and_respond,
)
from veritas_os.api.pipeline_orchestrator import ComplianceStopException


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

class _DummyModel(BaseModel):
    """Minimal Pydantic model for validate_and_respond tests."""
    ok: bool = True
    request_id: str = "test"


def _errstr(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"


def _is_debug_false() -> bool:
    return False


def _is_debug_true() -> bool:
    return True


def _decode_json_response(resp: JSONResponse) -> dict:
    """Extract the JSON body from a JSONResponse instance."""
    return json.loads(resp.body.decode())


class _EventCollector:
    """Callable that records (event_type, payload) tuples."""

    def __init__(self) -> None:
        self.events: List[tuple] = []

    def __call__(self, etype: str, payload: Any) -> None:
        self.events.append((etype, payload))


# ------------------------------------------------------------------
# error_response
# ------------------------------------------------------------------

class TestErrorResponse:
    def test_basic_error(self):
        resp = error_response(503, error="service_unavailable")
        body = _decode_json_response(resp)
        assert resp.status_code == 503
        assert body["ok"] is False
        assert body["error"] == "service_unavailable"
        assert body["detail"] == "service_unavailable"
        assert body["trust_log"] is None

    def test_custom_detail(self):
        resp = error_response(500, error="err", detail="custom detail")
        body = _decode_json_response(resp)
        assert body["detail"] == "custom detail"

    def test_extra_fields(self):
        resp = error_response(
            503, error="err", failure_category="timeout",
        )
        body = _decode_json_response(resp)
        assert body["failure_category"] == "timeout"

    def test_ok_override(self):
        resp = error_response(400, ok=True, error="warn")
        body = _decode_json_response(resp)
        assert body["ok"] is True


# ------------------------------------------------------------------
# publish_stage_events
# ------------------------------------------------------------------

class TestPublishStageEvents:
    def test_emits_debate_and_critique(self):
        publish = _EventCollector()

        def summary_fn(payload: Any, default: str) -> str:
            return payload if isinstance(payload, str) else default

        publish_stage_events(
            publish,
            summary_fn,
            {"request_id": "r1", "debate": "debate summary", "critique": None},
        )
        assert len(publish.events) == 2
        assert publish.events[0][0] == "trustlog.debate"
        assert publish.events[0][1]["summary"] == "debate summary"
        assert publish.events[1][0] == "trustlog.critique"
        assert publish.events[1][1]["summary"] == "critique stage completed"

    def test_missing_stages(self):
        publish = _EventCollector()

        def summary_fn(payload: Any, default: str) -> str:
            return default

        publish_stage_events(publish, summary_fn, {})
        assert len(publish.events) == 2
        assert publish.events[0][1]["request_id"] is None
        assert publish.events[1][1]["request_id"] is None


# ------------------------------------------------------------------
# publish_decide_completion
# ------------------------------------------------------------------

class TestPublishDecideCompletion:
    def test_emits_completion_event(self):
        publish = _EventCollector()

        publish_decide_completion(publish, {"ok": True, "request_id": "r1", "decision": "go"})
        assert len(publish.events) == 1
        assert publish.events[0][0] == "decide.completed"
        assert publish.events[0][1]["ok"] is True
        assert publish.events[0][1]["request_id"] == "r1"
        assert publish.events[0][1]["decision"] == "go"

    def test_defaults_ok_to_true(self):
        publish = _EventCollector()

        publish_decide_completion(publish, {})
        assert publish.events[0][1]["ok"] is True


# ------------------------------------------------------------------
# check_fuji_rejection
# ------------------------------------------------------------------

class TestCheckFujiRejection:
    def test_no_event_when_allowed(self):
        publish = _EventCollector()

        check_fuji_rejection(
            publish,
            {"status": "allow", "reasons": []},
            rejected_statuses={"reject", "rejected"},
        )
        assert publish.events == []

    def test_event_on_rejection(self):
        publish = _EventCollector()

        check_fuji_rejection(
            publish,
            {"status": "rejected", "reasons": ["safety"]},
            rejected_statuses={"reject", "rejected"},
            extra_event_fields={"request_id": "r1"},
        )
        assert len(publish.events) == 1
        assert publish.events[0][0] == "fuji.rejected"
        assert publish.events[0][1]["status"] == "rejected"
        assert publish.events[0][1]["reasons"] == ["safety"]
        assert publish.events[0][1]["request_id"] == "r1"

    def test_case_insensitive(self):
        publish = _EventCollector()

        check_fuji_rejection(
            publish,
            {"status": "REJECT"},
            rejected_statuses={"reject", "rejected"},
        )
        assert len(publish.events) == 1

    def test_missing_status(self):
        publish = _EventCollector()

        check_fuji_rejection(
            publish, {}, rejected_statuses={"reject", "rejected"},
        )
        assert publish.events == []


# ------------------------------------------------------------------
# apply_compliance_stop
# ------------------------------------------------------------------

class TestApplyComplianceStop:
    def test_pass_through(self):
        """No compliance issue → returns (coerced, None)."""
        publish = MagicMock()
        coerced = {"ok": True, "status": "allow"}
        result, resp = apply_compliance_stop(coerced, publish)
        assert resp is None
        assert result["ok"] is True
        publish.assert_not_called()

    def test_compliance_stop_triggered(self, monkeypatch):
        """ComplianceStopException → returns stop response and publishes event."""
        publish = _EventCollector()

        stop_payload = {"request_id": "r1", "status": "pending_review", "ok": False}

        def fake_enforce(c):
            raise ComplianceStopException(stop_payload)

        monkeypatch.setattr(
            "veritas_os.api.decide_service.enforce_compliance_stop",
            fake_enforce,
        )
        coerced = {"ok": True}
        _, resp = apply_compliance_stop(coerced, publish)
        assert resp is not None
        assert resp.status_code == 200
        body = _decode_json_response(resp)
        assert body["request_id"] == "r1"
        assert len(publish.events) == 1
        assert publish.events[0][0] == "compliance.pending_review"


# ------------------------------------------------------------------
# validate_and_respond
# ------------------------------------------------------------------

class TestValidateAndRespond:
    def test_success_returns_model(self):
        publish = MagicMock()
        result = validate_and_respond(
            _DummyModel,
            {"ok": True, "request_id": "r1"},
            publish_fn=publish,
            errstr_fn=_errstr,
            is_debug_fn=_is_debug_false,
        )
        assert isinstance(result, _DummyModel)
        assert result.ok is True

    def test_failure_returns_json_response(self):
        """Invalid data → JSONResponse with warn field."""
        publish = MagicMock()

        class StrictModel(BaseModel):
            required_field: int  # not provided

        result = validate_and_respond(
            StrictModel,
            {"wrong": "data"},
            publish_fn=publish,
            errstr_fn=_errstr,
            is_debug_fn=_is_debug_false,
        )
        assert isinstance(result, JSONResponse)
        body = _decode_json_response(result)
        assert body["warn"] == "response_model_validation_failed"
        assert body.get("ok") is False  # set_ok_false=True by default
        assert "warn_detail" not in body  # debug mode off
        publish.assert_called_once()

    def test_debug_mode_adds_warn_detail(self):
        publish = MagicMock()

        class StrictModel(BaseModel):
            required_field: int

        result = validate_and_respond(
            StrictModel,
            {"wrong": "data"},
            publish_fn=publish,
            errstr_fn=_errstr,
            is_debug_fn=_is_debug_true,
        )
        body = _decode_json_response(result)
        assert "warn_detail" in body

    def test_set_ok_false_disabled(self):
        """When set_ok_false=False, 'ok' is not forced to False."""
        publish = MagicMock()

        class StrictModel(BaseModel):
            required_field: int

        result = validate_and_respond(
            StrictModel,
            {"wrong": "data"},
            publish_fn=publish,
            errstr_fn=_errstr,
            is_debug_fn=_is_debug_false,
            set_ok_false=False,
        )
        body = _decode_json_response(result)
        # ok should not be explicitly set to False
        assert body.get("ok") is not False or "ok" not in body

    def test_custom_event_type(self):
        publish = _EventCollector()

        class StrictModel(BaseModel):
            required_field: int

        validate_and_respond(
            StrictModel,
            {"wrong": "data"},
            publish_fn=publish,
            errstr_fn=_errstr,
            is_debug_fn=_is_debug_false,
            event_type="fuji.completed",
        )
        assert publish.events[0][0] == "fuji.completed"
