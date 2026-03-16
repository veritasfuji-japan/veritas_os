# veritas_os/api/routes_trust.py
"""Trust log, feedback, verify, export, and PROV endpoints."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from veritas_os.api.schemas import TrustFeedbackRequest

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_server():
    """Late import to avoid circular dependency at module load time."""
    from veritas_os.api import server as srv
    return srv


def _parse_risk_from_trust_entry(entry: Dict[str, Any]) -> float | None:
    """Extract risk score from trust-log payload in a backward compatible way."""
    if not isinstance(entry, dict):
        return None
    candidates = (
        entry.get("risk"),
        (entry.get("gate") or {}).get("risk") if isinstance(entry.get("gate"), dict) else None,
        (entry.get("fuji") or {}).get("risk") if isinstance(entry.get("fuji"), dict) else None,
    )
    for item in candidates:
        try:
            if item is None:
                continue
            return float(item)
        except (TypeError, ValueError):
            continue
    return None


def _prov_actor_for_entry(entry: Dict[str, Any]) -> str:
    """Resolve PROV agent label from trust entry metadata."""
    for key in ("updated_by", "actor", "user_id", "request_user_id"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "veritas_api"


# ------------------------------------------------------------------
# Trust Log read endpoints
# ------------------------------------------------------------------

@router.get("/v1/trust/logs")
def trust_logs(cursor: Optional[str] = None, limit: int = 50):
    """TrustLog をページング取得する。"""
    srv = _get_server()
    return srv.get_trust_log_page(cursor=cursor, limit=limit)


@router.get("/v1/trust/stats")
def trust_log_stats():
    """Return TrustLog append success/failure counters for operational monitoring."""
    try:
        from veritas_os.logging.trust_log import get_trust_log_stats
        stats = get_trust_log_stats()
        return {"ok": True, **stats}
    except Exception as e:
        logger.error("trust_log_stats failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to read trust log stats"},
        )


@router.get("/v1/trust/{request_id}/prov")
def trust_prov_export(request_id: str) -> Dict[str, Any]:
    """Export one decision trace as W3C PROV JSON for external audit tooling."""
    srv = _get_server()
    try:
        entries = srv.get_trust_logs_by_request(request_id)
        if not entries:
            return JSONResponse(
                status_code=404,
                content={"ok": False, "error": "trust trace not found"},
            )
        latest = entries[-1]
        prov = srv.build_w3c_prov_document(
            request_id=request_id,
            decision_status=str(latest.get("decision_status") or latest.get("status") or "unknown"),
            risk=_parse_risk_from_trust_entry(latest),
            timestamp=str(latest.get("ts") or latest.get("timestamp") or srv.utc_now_iso_z()),
            actor=_prov_actor_for_entry(latest),
        )
        return {"ok": True, "request_id": request_id, "prov": prov}
    except Exception as e:
        logger.error("trust_prov_export failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to export PROV trace"},
        )


@router.get("/v1/trust/{request_id}")
def trust_log_by_request(request_id: str):
    """request_id 単位で TrustLog を取得する。"""
    srv = _get_server()
    return srv.get_trust_logs_by_request(request_id=request_id)


# ------------------------------------------------------------------
# Trust Feedback
# ------------------------------------------------------------------

@router.post("/v1/trust/feedback")
def trust_feedback(body: TrustFeedbackRequest):
    """人間からのフィードバックを trust_log に記録する簡易API。"""
    srv = _get_server()
    vc = srv.get_value_core()
    if vc is None:
        logger.warning("trust_feedback: value_core unavailable: %s", srv._value_core_state.err)
        return {"status": "error", "detail": "value_core unavailable"}

    try:
        uid = str(body.user_id or "anon")[:500]
        score = body.score
        note = body.note
        source = body.source
        extra = {"api": "/v1/trust/feedback"}

        if hasattr(vc, "append_trust_log"):
            vc.append_trust_log(
                user_id=uid,
                score=score,
                note=note,
                source=source,
                extra=extra,
            )
            srv._publish_event(
                "trustlog.appended",
                {"kind": "feedback", "user_id": uid, "source": source},
            )
            return {"status": "ok", "user_id": uid}

        return {"status": "error", "detail": "value_core.append_trust_log not found"}

    except Exception as e:
        logger.error("[Trust] feedback failed: %s", e)
        return {"status": "error", "detail": "internal error in trust_feedback"}


# ------------------------------------------------------------------
# TrustLog verify / export
# ------------------------------------------------------------------

@router.get("/v1/trustlog/verify")
def trustlog_verify() -> Dict[str, Any]:
    """Verify signed append-only TrustLog integrity and signatures."""
    srv = _get_server()
    try:
        return srv.verify_trustlog_chain()
    except Exception as e:
        logger.error("[TrustLog] verify failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "trustlog verification failed"},
        )


@router.get("/v1/trustlog/export")
def trustlog_export() -> Dict[str, Any]:
    """Export signed append-only TrustLog entries for external audit."""
    srv = _get_server()
    try:
        return srv.export_signed_trustlog()
    except Exception as e:
        logger.error("[TrustLog] export failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "trustlog export failed"},
        )
