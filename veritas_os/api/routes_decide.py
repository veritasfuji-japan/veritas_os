# veritas_os/api/routes_decide.py
"""Decision pipeline, replay, and FUJI validation endpoints."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from veritas_os.api.schemas import DecideRequest, DecideResponse, FujiDecision
from veritas_os.api.pipeline_orchestrator import (
    ComplianceStopException,
    enforce_compliance_stop,
    resolve_dynamic_steps,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_server():
    """Late import to avoid circular dependency at module load time."""
    from veritas_os.api import server as srv
    return srv



# ------------------------------------------------------------------
# /v1/decide
# ------------------------------------------------------------------

@router.post("/v1/decide", response_model=DecideResponse)
async def decide(req: DecideRequest, request: Request):
    srv = _get_server()
    p = srv.get_decision_pipeline()
    if p is None:
        srv._log_decide_failure("decision_pipeline unavailable", srv._pipeline_state.err)
        srv._publish_event("decide.completed", {"ok": False, "error": srv.DECIDE_GENERIC_ERROR})
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": srv.DECIDE_GENERIC_ERROR,
                "detail": srv.DECIDE_GENERIC_ERROR,
                "trust_log": None,
            },
        )

    try:
        payload = await p.run_decide_pipeline(req=req, request=request)
    except Exception as e:
        failure_category = srv._classify_decide_failure(e)
        srv._log_decide_failure("decision_pipeline execution failed", e)
        srv._publish_event(
            "decide.completed",
            {
                "ok": False,
                "error": srv.DECIDE_GENERIC_ERROR,
                "failure_category": failure_category,
            },
        )
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": srv.DECIDE_GENERIC_ERROR,
                "detail": srv.DECIDE_GENERIC_ERROR,
                "failure_category": failure_category,
                "trust_log": None,
            },
        )

    if isinstance(payload, dict):
        resolve_dynamic_steps(payload)
        srv._publish_event(
            "trustlog.debate",
            {
                "request_id": payload.get("request_id"),
                "summary": srv._stage_summary(
                    payload.get("debate"),
                    "debate stage completed",
                ),
            },
        )
        srv._publish_event(
            "trustlog.critique",
            {
                "request_id": payload.get("request_id"),
                "summary": srv._stage_summary(
                    payload.get("critique"),
                    "critique stage completed",
                ),
            },
        )

    coerced = srv._coerce_decide_payload(payload, seed=getattr(req, "query", "") or "")
    try:
        coerced = enforce_compliance_stop(coerced)
    except ComplianceStopException as stop:
        srv._publish_event(
            "compliance.pending_review",
            {
                "request_id": stop.payload.get("request_id"),
                "status": stop.payload.get("status"),
            },
        )
        return JSONResponse(status_code=200, content=stop.payload)

    try:
        srv._publish_event(
            "decide.completed",
            {
                "ok": bool(coerced.get("ok", True)),
                "request_id": coerced.get("request_id"),
                "decision": coerced.get("decision"),
            },
        )
        fuji_payload = coerced.get("fuji") or {}
        if str(fuji_payload.get("status", "")).lower() in {"reject", "rejected", srv.DECISION_REJECTED}:
            srv._publish_event(
                "fuji.rejected",
                {
                    "request_id": coerced.get("request_id"),
                    "status": fuji_payload.get("status"),
                    "reasons": fuji_payload.get("reasons", []),
                },
            )
        return DecideResponse.model_validate(coerced)
    except Exception as e:
        logger.error("DecideResponse validation failed: %s", srv._errstr(e))
        content: Dict[str, Any] = {
            **coerced,
            "ok": False,
            "warn": "response_model_validation_failed",
        }
        if srv._is_debug_mode():
            content["warn_detail"] = srv._errstr(e)
        srv._publish_event(
            "decide.completed",
            {"ok": False, "warn": "response_model_validation_failed", "request_id": coerced.get("request_id")},
        )
        return JSONResponse(status_code=200, content=content)


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
        logger.error("replay endpoint failed: %s", srv._errstr(e))
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
                "diff": {"error": srv.DECIDE_GENERIC_ERROR},
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
        logger.error("decision replay failed: %s", srv._errstr(e))
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


@router.post("/v1/fuji/validate", response_model=FujiDecision)
def fuji_validate(payload: dict):
    srv = _get_server()
    if not srv._is_direct_fuji_api_enabled():
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
                content={"detail": err_msg}
            )
        logger.error("fuji_validate RuntimeError: %s", err_msg)
        return JSONResponse(
            status_code=200,
            content={
                "status": "error",
                "reasons": ["Validation failed"],
                "violations": []
            }
        )
    except Exception as e:
        logger.error("fuji_validate error: %s", srv._errstr(e))
        return JSONResponse(
            status_code=200,
            content={
                "status": "error",
                "reasons": ["Validation failed"],
                "violations": []
            }
        )

    coerced = srv._coerce_fuji_payload(result, action=action)
    if str(coerced.get("status", "")).lower() in {"reject", "rejected", srv.DECISION_REJECTED}:
        srv._publish_event(
            "fuji.rejected",
            {"action": action, "status": coerced.get("status"), "reasons": coerced.get("reasons", [])},
        )
    try:
        return FujiDecision.model_validate(coerced)
    except Exception as e:
        logger.error("FujiDecision validation failed: %s", srv._errstr(e))
        content: Dict[str, Any] = {
            **coerced,
            "warn": "response_model_validation_failed",
        }
        if srv._is_debug_mode():
            content["warn_detail"] = srv._errstr(e)
        srv._publish_event(
            "decide.completed",
            {"ok": False, "warn": "response_model_validation_failed", "request_id": coerced.get("request_id")},
        )
        return JSONResponse(status_code=200, content=content)
