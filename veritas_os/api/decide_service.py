# veritas_os/api/decide_service.py
"""Service helpers for decision pipeline endpoints.

Extracts shared failure handling, event publishing, response
coercion/validation, and compliance stop logic so that route handlers
in ``routes_decide.py`` stay thin ("controller" style).

Every public function is a pure helper that accepts explicit
dependencies (callbacks/values) — no hidden ``server`` import.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Set

from fastapi.responses import JSONResponse

from veritas_os.api.pipeline_orchestrator import (
    ComplianceStopException,
    enforce_compliance_stop,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Error response builders
# ------------------------------------------------------------------

def error_response(
    status_code: int,
    *,
    ok: bool = False,
    error: str = "",
    detail: Optional[str] = None,
    trust_log: Any = None,
    **extra: Any,
) -> JSONResponse:
    """Build a standardised error ``JSONResponse`` for decide endpoints."""
    content: Dict[str, Any] = {
        "ok": ok,
        "error": error,
        "detail": detail if detail is not None else error,
        "trust_log": trust_log,
    }
    content.update(extra)
    return JSONResponse(status_code=status_code, content=content)


# ------------------------------------------------------------------
# Event publishing helpers
# ------------------------------------------------------------------

def publish_stage_events(
    publish_fn: Callable[..., Any],
    stage_summary_fn: Callable[..., str],
    payload: Dict[str, Any],
) -> None:
    """Emit ``trustlog.debate`` / ``trustlog.critique`` events."""
    request_id = payload.get("request_id")
    publish_fn(
        "trustlog.debate",
        {
            "request_id": request_id,
            "summary": stage_summary_fn(
                payload.get("debate"), "debate stage completed"
            ),
        },
    )
    publish_fn(
        "trustlog.critique",
        {
            "request_id": request_id,
            "summary": stage_summary_fn(
                payload.get("critique"), "critique stage completed"
            ),
        },
    )


def publish_decide_completion(
    publish_fn: Callable[..., Any],
    coerced: Dict[str, Any],
) -> None:
    """Emit ``decide.completed`` success event."""
    publish_fn(
        "decide.completed",
        {
            "ok": bool(coerced.get("ok", True)),
            "request_id": coerced.get("request_id"),
            "decision": coerced.get("decision"),
        },
    )


def check_fuji_rejection(
    publish_fn: Callable[..., Any],
    fuji_payload: Dict[str, Any],
    *,
    rejected_statuses: Set[str],
    extra_event_fields: Optional[Dict[str, Any]] = None,
) -> None:
    """Publish ``fuji.rejected`` event when the FUJI status signals rejection."""
    status_str = str(fuji_payload.get("status", "")).lower()
    if status_str not in rejected_statuses:
        return
    event_data: Dict[str, Any] = {
        "status": fuji_payload.get("status"),
        "reasons": fuji_payload.get("reasons", []),
    }
    if extra_event_fields:
        event_data.update(extra_event_fields)
    publish_fn("fuji.rejected", event_data)


# ------------------------------------------------------------------
# Compliance stop
# ------------------------------------------------------------------

def apply_compliance_stop(
    coerced: Dict[str, Any],
    publish_fn: Callable[..., Any],
) -> tuple[Dict[str, Any], Optional[JSONResponse]]:
    """Run ``enforce_compliance_stop`` and handle ``ComplianceStopException``.

    Returns ``(coerced, None)`` if processing should continue, or
    ``(coerced, stop_response)`` if a compliance stop was triggered.
    """
    try:
        coerced = enforce_compliance_stop(coerced)
    except ComplianceStopException as stop:
        publish_fn(
            "compliance.pending_review",
            {
                "request_id": stop.payload.get("request_id"),
                "status": stop.payload.get("status"),
            },
        )
        return coerced, JSONResponse(status_code=200, content=stop.payload)
    return coerced, None


# ------------------------------------------------------------------
# Response validation with fallback
# ------------------------------------------------------------------

def validate_and_respond(
    model_class: type,
    coerced: Dict[str, Any],
    *,
    publish_fn: Callable[..., Any],
    errstr_fn: Callable[[Exception], str],
    is_debug_fn: Callable[[], bool],
    event_type: str = "decide.completed",
    set_ok_false: bool = True,
) -> Any:
    """Validate *coerced* against a Pydantic *model_class*.

    On success the validated model instance is returned.
    On failure a ``JSONResponse(200)`` is returned with a ``warn`` field
    and an event is published to *event_type*.
    """
    try:
        return model_class.model_validate(coerced)
    except Exception as e:
        logger.error(
            "%s validation failed: %s", model_class.__name__, errstr_fn(e)
        )
        content: Dict[str, Any] = {**coerced, "warn": "response_model_validation_failed"}
        if set_ok_false:
            content["ok"] = False
        if is_debug_fn():
            content["warn_detail"] = errstr_fn(e)
        publish_fn(
            event_type,
            {
                "ok": False,
                "warn": "response_model_validation_failed",
                "request_id": coerced.get("request_id"),
            },
        )
        return JSONResponse(status_code=200, content=content)
