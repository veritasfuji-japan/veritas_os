# veritas_os/api/routes_decide.py
"""Decision pipeline, replay, and FUJI validation endpoints.

Route handlers are intentionally kept thin ("controller" style).
Business logic for failure handling, event publishing, compliance
stops, and response coercion/validation lives in
:mod:`~veritas_os.api.decide_service` and :mod:`~veritas_os.api.utils`.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from veritas_os.api.auth import require_permission
from veritas_os.api.rbac import Permission
from veritas_os.api.schemas import DecideRequest, DecideResponse, FujiDecision
from veritas_os.api.pipeline_orchestrator import resolve_dynamic_steps
from veritas_os.api.utils import (
    _classify_decide_failure,
    _coerce_decide_payload,
    _coerce_fuji_payload,
    _errstr,
    _is_debug_mode,
    _is_direct_fuji_api_enabled,
    _log_decide_failure,
    _stage_summary,
    DECIDE_GENERIC_ERROR,
)
from veritas_os.api.constants import DECISION_REJECTED
from veritas_os.api import decide_service as _svc

logger = logging.getLogger(__name__)

try:
    from veritas_os.observability.metrics import record_decide, set_telos_score
except Exception:  # pragma: no cover - optional observability dependency
    def record_decide(status: Any, mode: Any, intent: Any, duration_seconds: float | None = None) -> None:
        return None

    def set_telos_score(user_id: Any, score: Any) -> None:
        return None

router = APIRouter()

# Rejection status set, shared across handlers.
# DECISION_REJECTED is "rejected" (lowercase) — the .lower() comparison
# in check_fuji_rejection handles any casing from pipeline output.
_REJECTED_STATUSES: set[str] = {"reject", "rejected", DECISION_REJECTED}


def _get_server():
    """Late import to avoid circular dependency at module load time."""
    from veritas_os.api import server as srv
    return srv


# ------------------------------------------------------------------
# /v1/decide
# ------------------------------------------------------------------

@router.post("/v1/decide", response_model=DecideResponse, dependencies=[Depends(require_permission(Permission.decide))])
async def decide(req: DecideRequest, request: Request):
    started_at = time.perf_counter()
    mode = "fast" if bool(getattr(req, "fast_mode", False)) else "normal"
    intent = "unknown"
    req_context = getattr(req, "context", None)
    if isinstance(req_context, dict):
        intent = req_context.get("intent") or intent

    def _record(status: str) -> None:
        record_decide(
            status=status,
            mode=mode,
            intent=intent,
            duration_seconds=time.perf_counter() - started_at,
        )

    srv = _get_server()
    p = srv.get_decision_pipeline()
    if p is None:
        _log_decide_failure("decision_pipeline unavailable", srv._pipeline_state.err)
        # Best-effort recovery for subsequent requests when availability is
        # temporarily degraded by test/runtime mutation of lazy state.
        if (
            getattr(srv._pipeline_state, "obj", None) is None
            and getattr(srv._pipeline_state, "attempted", False)
            and getattr(srv._pipeline_state, "err", None) is not None
        ):
            srv._pipeline_state = srv._LazyState()
        try:
            srv._publish_event("decide.completed", {"ok": False, "error": DECIDE_GENERIC_ERROR})
        except Exception:
            logger.debug("event publish failed on pipeline unavailable (best-effort)", exc_info=True)
        _record("unavailable")
        return _svc.error_response(503, error=DECIDE_GENERIC_ERROR)

    try:
        payload = await p.run_decide_pipeline(req=req, request=request)
    except Exception as e:
        failure_category = _classify_decide_failure(e)
        _log_decide_failure("decision_pipeline execution failed", e)
        try:
            srv._publish_event(
                "decide.completed",
                {"ok": False, "error": DECIDE_GENERIC_ERROR, "failure_category": failure_category},
            )
        except Exception:
            logger.debug("event publish failed on pipeline error (best-effort)", exc_info=True)
        _record("error")
        return _svc.error_response(503, error=DECIDE_GENERIC_ERROR, failure_category=failure_category)

    if isinstance(payload, dict):
        resolve_dynamic_steps(payload)
        try:
            _svc.publish_stage_events(srv._publish_event, _stage_summary, payload)
        except Exception:
            logger.debug("stage event publish failed (best-effort)", exc_info=True)

    coerced = _coerce_decide_payload(payload, seed=getattr(req, "query", "") or "")

    coerced, stop_response = _svc.apply_compliance_stop(coerced, srv._publish_event)
    if stop_response is not None:
        _record("compliance_stop")
        return stop_response

    try:
        _svc.publish_decide_completion(srv._publish_event, coerced)
        _svc.check_fuji_rejection(
            srv._publish_event,
            coerced.get("fuji") or {},
            rejected_statuses=_REJECTED_STATUSES,
            extra_event_fields={"request_id": coerced.get("request_id")},
        )
    except Exception:
        logger.debug("post-pipeline event publish failed (best-effort)", exc_info=True)

    fuji = coerced.get("fuji") if isinstance(coerced, dict) else {}
    status = "allow"
    if isinstance(fuji, dict):
        status = str(fuji.get("decision_status") or fuji.get("status") or status)

    user_id = getattr(getattr(request, "state", None), "user_id", None)
    if user_id is None and isinstance(req_context, dict):
        user_id = req_context.get("user_id")
    set_telos_score(user_id=user_id or "anonymous", score=coerced.get("telos_score"))
    _record(status)

    return _svc.validate_and_respond(
        DecideResponse, coerced,
        publish_fn=srv._publish_event,
        errstr_fn=_errstr,
        is_debug_fn=_is_debug_mode,
    )


# ------------------------------------------------------------------
# /v1/replay
# ------------------------------------------------------------------

@router.post("/v1/replay/{decision_id}")
async def replay_endpoint(decision_id: str, request: Request):
    """Replay one persisted decision and write replay report JSON.

    Note: This endpoint requires HMAC signature verification in addition
    to the router-level API key + rate limit dependencies.
    """
    srv = _get_server()
    # Manually invoke HMAC signature verification (originally a Depends())
    await srv.verify_signature(
        request,
        x_api_key=request.headers.get("X-API-Key"),
        x_timestamp=request.headers.get("X-Timestamp"),
        x_nonce=request.headers.get("X-Nonce"),
        x_signature=request.headers.get("X-Signature"),
        x_veritas_timestamp=request.headers.get("X-VERITAS-TIMESTAMP"),
        x_veritas_nonce=request.headers.get("X-VERITAS-NONCE"),
        x_veritas_signature=request.headers.get("X-VERITAS-SIGNATURE"),
    )
    try:
        result = await srv.run_replay(decision_id=decision_id)
    except ValueError:
        return JSONResponse(
            status_code=404,
            content={"ok": False, "decision_id": decision_id, "error": "decision_not_found"},
        )
    except Exception as e:
        logger.error("replay endpoint failed: %s", _errstr(e))
        return JSONResponse(
            status_code=500,
            content={"ok": False, "decision_id": decision_id, "error": "replay_failed"},
        )

    return {
        "ok": True,
        "decision_id": result.decision_id,
        "replay_path": result.replay_path,
        "match": result.match,
        "diff_summary": result.diff_summary,
        "replay_time_ms": result.replay_time_ms,
        "schema_version": result.schema_version,
        "severity": result.severity,
        "divergence_level": result.divergence_level,
        "audit_summary": result.audit_summary,
    }


@router.post("/v1/decision/replay/{decision_id}")
async def replay_decision_endpoint(decision_id: str, request: Request):
    """Replay a persisted decision deterministically and return diff report."""
    srv = _get_server()
    p = srv.get_decision_pipeline()
    if p is None or not hasattr(p, "replay_decision"):
        return JSONResponse(
            status_code=503,
            content={
                "match": False,
                "diff": {"error": DECIDE_GENERIC_ERROR},
                "replay_time_ms": 0,
            },
        )

    mock_external_apis = True
    try:
        qv = request.query_params.get("mock_external_apis")
        if qv is not None:
            mock_external_apis = str(qv).strip().lower() not in {"0", "false", "no", "off"}
    except Exception:
        mock_external_apis = True

    try:
        result = await p.replay_decision(
            decision_id=decision_id,
            mock_external_apis=mock_external_apis,
        )
    except Exception as e:
        logger.error("decision replay failed: %s", _errstr(e))
        return JSONResponse(
            status_code=500,
            content={
                "match": False,
                "diff": {"error": "replay_failed"},
                "replay_time_ms": 0,
            },
        )
    return result


# ------------------------------------------------------------------
# /v1/fuji/validate
# ------------------------------------------------------------------

def _call_fuji(fc: Any, action: str, context: dict) -> dict:
    """validate_action / validate の微妙なシグネチャ差を吸収する。"""
    if hasattr(fc, "validate_action"):
        fn = fc.validate_action
        try:
            return fn(action=action, context=context)
        except TypeError:
            return fn(action, context)
    if hasattr(fc, "validate"):
        fn = fc.validate
        try:
            return fn(action=action, context=context)
        except TypeError:
            try:
                return fn(action, context)
            except TypeError:
                return fn(action)
    raise RuntimeError("fuji_core has neither validate_action nor validate")


@router.post("/v1/fuji/validate", response_model=FujiDecision, dependencies=[Depends(require_permission(Permission.decide))])
def fuji_validate(payload: dict):
    srv = _get_server()
    if not _is_direct_fuji_api_enabled():
        return JSONResponse(
            status_code=403,
            content={
                "detail": (
                    "direct_fuji_api_disabled: use /v1/decide pipeline or set "
                    "VERITAS_ENABLE_DIRECT_FUJI_API=1"
                )
            },
        )

    fc = srv.get_fuji_core()
    if fc is None:
        logger.warning("fuji_validate: fuji_core unavailable: %s", srv._fuji_state.err)
        return JSONResponse(
            status_code=503,
            content={"detail": "fuji_core unavailable"}
        )

    action = str(payload.get("action", "") or "")[:10_000]
    context = payload.get("context") or {}

    try:
        result = _call_fuji(fc, action, context)
    except RuntimeError as e:
        err_msg = str(e)
        if "neither validate_action nor validate" in err_msg:
            logger.error("fuji_validate: %s", err_msg)
            return JSONResponse(
                status_code=500,
                content={"detail": "FUJI core interface error"}
            )
        logger.error("fuji_validate RuntimeError: %s", err_msg)
        return JSONResponse(
            status_code=200,
            content={"status": "error", "reasons": ["Validation failed"], "violations": []}
        )
    except Exception as e:
        logger.error("fuji_validate error: %s", _errstr(e))
        return JSONResponse(
            status_code=200,
            content={"status": "error", "reasons": ["Validation failed"], "violations": []}
        )

    coerced = _coerce_fuji_payload(result, action=action)
    _svc.check_fuji_rejection(
        srv._publish_event,
        coerced,
        rejected_statuses=_REJECTED_STATUSES,
        extra_event_fields={"action": action},
    )
    return _svc.validate_and_respond(
        FujiDecision, coerced,
        publish_fn=srv._publish_event,
        errstr_fn=_errstr,
        is_debug_fn=_is_debug_mode,
        set_ok_false=False,
    )
