# veritas_os/api/routes_system.py
"""System halt/resume, compliance config, deployment readiness, reports,
health, status, metrics, and SSE/WebSocket endpoints."""
from __future__ import annotations

import asyncio
import heapq
import json
import logging
import queue
import time
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from veritas_os.api.pipeline_orchestrator import (
    get_runtime_config,
    update_runtime_config,
)
# Note: report/compliance functions accessed via _get_server() to support
# test monkeypatching on the server module.

logger = logging.getLogger(__name__)

# Public router: health/status endpoints (no auth required)
public_router = APIRouter()

# Protected router: metrics, compliance, reports, system halt/resume
router = APIRouter()

# Events router: SSE/WebSocket with header-or-query auth
events_router = APIRouter()


def _get_server():
    """Late import to avoid circular dependency at module load time."""
    from veritas_os.api import server as srv
    return srv


def _runtime_feature_checks(srv: Any) -> Dict[str, str]:
    """Return runtime feature statuses for health visibility."""
    sanitize_status = "ok" if getattr(srv, "_HAS_SANITIZE", False) else "degraded"
    atomic_io_status = "ok" if getattr(srv, "_HAS_ATOMIC_IO", False) else "degraded"
    return {
        "sanitize": sanitize_status,
        "atomic_io": atomic_io_status,
    }


def _auth_store_health(srv: Any) -> Dict[str, Any]:
    """Return auth-store runtime health details for system health responses."""
    snapshot = srv.auth_store_health_snapshot()
    status = snapshot.get("status", "ok")
    return {
        "status": status if status in {"ok", "degraded"} else "degraded",
        "details": snapshot,
    }


def _trust_log_health(srv: Any) -> Dict[str, Any]:
    """Return trust-log aggregate JSON health for audit visibility."""
    trust_log_runtime = getattr(srv, "_trust_log_runtime", None)
    if trust_log_runtime is None:
        return {"status": "unknown", "details": {"status": "unknown"}}

    _, log_json, _ = srv._effective_log_paths()
    trust_log_runtime.effective_log_paths = srv._effective_log_paths
    load_result = trust_log_runtime.load_logs_json_result(log_json)
    raw_status = getattr(load_result, "status", "unknown")
    status = "ok" if raw_status in {"ok", "missing"} else "degraded"
    details: Dict[str, Any] = {"status": raw_status}
    error = getattr(load_result, "error", None)
    if error:
        details["error"] = error
    return {"status": status, "details": details}


# ------------------------------------------------------------------
# Pydantic models
# ------------------------------------------------------------------

class ComplianceConfigBody(BaseModel):
    """Runtime compliance config payload."""
    eu_ai_act_mode: bool = Field(default=False)
    safety_threshold: float = Field(default=0.8, ge=0.0, le=1.0)


class SystemHaltRequest(BaseModel):
    """Request body for POST /v1/system/halt."""
    reason: str = Field(..., min_length=1, max_length=500)
    operator: str = Field(..., min_length=1, max_length=200)


class SystemResumeRequest(BaseModel):
    """Request body for POST /v1/system/resume."""
    operator: str = Field(..., min_length=1, max_length=200)
    comment: str = Field(default="", max_length=500)


# ------------------------------------------------------------------
# Health / Status
# ------------------------------------------------------------------

@public_router.get("/")
def root() -> Dict[str, Any]:
    srv = _get_server()
    return {"ok": True, "service": "veritas-api", "server_time": srv.utc_now_iso_z()}


@public_router.get("/health")
@public_router.get("/v1/health")
def health() -> Dict[str, Any]:
    """Return lightweight health information with explicit degraded status."""
    srv = _get_server()
    try:
        pipeline_ok = srv.get_decision_pipeline() is not None
        memory_store = srv.get_memory_store()
        memory_ok = memory_store is not None
        memory_health = None
        if memory_ok and hasattr(memory_store, "health_snapshot"):
            memory_health = memory_store.health_snapshot()

        pipeline_status = "ok" if pipeline_ok else "unavailable"
        memory_status = "ok" if memory_ok else "unavailable"
        runtime_features = _runtime_feature_checks(srv)
        auth_store = _auth_store_health(srv)
        trust_log = _trust_log_health(srv)
        if memory_health and memory_health.get("status") == "degraded":
            memory_status = "degraded"

        health_status = "ok"
        if pipeline_status == "unavailable" or memory_status == "unavailable":
            health_status = "unavailable"
        elif (
            memory_status == "degraded"
            or "degraded" in runtime_features.values()
            or auth_store["status"] == "degraded"
            or trust_log["status"] == "degraded"
        ):
            health_status = "degraded"

        all_ok = health_status == "ok"
        result: Dict[str, Any] = {
            "ok": all_ok,
            "status": health_status,
            "uptime": int(time.time() - srv.START_TS),
            "checks": {
                "pipeline": pipeline_status,
                "memory": memory_status,
                "auth_store": auth_store["status"],
                "trust_log": trust_log["status"],
            },
            "runtime_features": runtime_features,
            "auth_store": auth_store["details"],
            "trust_log": trust_log["details"],
        }
        if memory_health:
            result["memory_health"] = memory_health
        return result
    except Exception as e:
        logger.error("[Health] check failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "health check failed"},
        )


@public_router.get("/status")
@public_router.get("/v1/status")
@public_router.get("/api/status")
def status() -> Dict[str, Any]:
    srv = _get_server()
    expected = (srv._get_expected_api_key() or "").strip()
    result = {
        "ok": True,
        "version": "veritas-api 1.0.3",
        "uptime": int(time.time() - srv.START_TS),
        "server_time": srv.utc_now_iso_z(),
        "pipeline_ok": srv.get_decision_pipeline() is not None,
        "api_key_configured": bool(expected),
    }

    if srv._is_debug_mode():
        result["cfg_error"] = srv._cfg_state.err
        result["pipeline_error"] = srv._pipeline_state.err
    else:
        result["cfg_error"] = bool(srv._cfg_state.err)
        result["pipeline_error"] = bool(srv._pipeline_state.err)
    return result


# ------------------------------------------------------------------
# Metrics
# ------------------------------------------------------------------

def _collect_recent_decide_files(shadow_dir: Path, limit: int) -> tuple[list[Path], int]:
    """Return latest decide files while keeping memory usage bounded."""
    total_count = 0
    min_heap: list[tuple[str, Path]] = []
    for file_path in shadow_dir.glob("decide_*.json"):
        total_count += 1
        item = (file_path.name, file_path)
        if len(min_heap) < limit:
            heapq.heappush(min_heap, item)
            continue
        if item[0] > min_heap[0][0]:
            heapq.heapreplace(min_heap, item)
    newest = sorted((path for _, path in min_heap), key=lambda file_path: file_path.name)
    return newest, total_count


@router.get("/v1/metrics")
def metrics(decide_file_limit: int = Query(default=500, ge=1, le=5000)):
    """Return operational metrics with degraded security/memory posture."""
    srv = _get_server()
    shadow_dir = srv._effective_shadow_dir()
    _, log_json, log_jsonl = srv._effective_log_paths()
    trust_log_runtime = getattr(srv, "_trust_log_runtime", None)
    trust_json_result = None
    if trust_log_runtime is not None:
        trust_log_runtime.effective_log_paths = srv._effective_log_paths
        trust_json_result = trust_log_runtime.load_logs_json_result(log_json)

    files, total_decide_files = _collect_recent_decide_files(shadow_dir, decide_file_limit)
    last_at = None
    if files:
        try:
            with open(files[-1], encoding="utf-8") as f:
                last_at = json.load(f).get("created_at")
        except Exception:
            logger.debug("failed to read last decide file: %s", files[-1], exc_info=True)

    lines = 0
    try:
        if log_jsonl.exists():
            with open(log_jsonl, encoding="utf-8") as f:
                for _ in f:
                    lines += 1
    except Exception as e:
        logger.warning("read trust_log.jsonl failed: %s", srv._errstr(e))

    auth_store = _auth_store_health(srv)
    runtime_features = _runtime_feature_checks(srv)
    memory_store = srv.get_memory_store()
    memory_health = None
    memory_status = "unavailable"
    if memory_store is not None:
        memory_status = "ok"
        if hasattr(memory_store, "health_snapshot"):
            memory_health = memory_store.health_snapshot()
            if memory_health.get("status") == "degraded":
                memory_status = "degraded"

    result = {
        "decide_files": total_decide_files,
        "decide_files_returned": len(files),
        "decide_files_truncated": total_decide_files > len(files),
        "trust_jsonl_lines": lines,
        "trust_json_status": (
            trust_json_result.status if trust_json_result is not None else "unknown"
        ),
        "last_decide_at": last_at,
        "server_time": srv.utc_now_iso_z(),
        "pipeline_ok": srv.get_decision_pipeline() is not None,
        "memory_status": memory_status,
        "runtime_features": runtime_features,
        "auth_store_mode": auth_store["details"].get("requested_mode", "memory"),
        "auth_store_effective_mode": auth_store["details"].get("effective_mode", "memory"),
        "auth_store_status": auth_store["status"],
        "auth_store_failure_mode": auth_store["details"].get(
            "failure_mode", srv._auth_store_failure_mode()
        ),
        "auth_store_reasons": auth_store["details"].get("reasons", []),
        "auth_reject_reasons": srv._snapshot_auth_reject_reason_metrics(),
    }
    if memory_health is not None:
        result["memory_health"] = memory_health

    if srv._is_debug_mode():
        result["pipeline_error"] = srv._pipeline_state.err
        result["cfg_error"] = srv._cfg_state.err
        result["trust_json_error"] = (
            None if trust_json_result is None else trust_json_result.error
        )
    else:
        result["pipeline_error"] = bool(srv._pipeline_state.err)
        result["cfg_error"] = bool(srv._cfg_state.err)
        result["trust_json_error"] = bool(
            trust_json_result is not None and trust_json_result.error
        )
    return result


# ------------------------------------------------------------------
# SSE events
# ------------------------------------------------------------------

@events_router.get("/v1/events")
async def events(request: Request, heartbeat_sec: int = Query(default=15, ge=5, le=60)):
    """Server-Sent Events stream for near-real-time UI updates."""
    srv = _get_server()
    subscriber = srv._event_hub.register()

    async def _stream():
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.to_thread(subscriber.get, timeout=heartbeat_sec)
                    yield srv._format_sse_message(item)
                except queue.Empty:
                    yield f": heartbeat {srv.utc_now_iso_z()}\n\n"
        finally:
            srv._event_hub.unregister(subscriber)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(_stream(), media_type="text/event-stream", headers=headers)


@events_router.websocket("/v1/ws/trustlog")
async def trustlog_ws(websocket: WebSocket):
    """WebSocket stream for Debate/Critique trust logs."""
    srv = _get_server()
    if not srv._authenticate_websocket_api_key(websocket):
        await websocket.close(code=1008, reason="invalid_api_key")
        return

    await websocket.accept()
    subscriber = srv._event_hub.register()
    allowed_types = {
        "trustlog.debate",
        "trustlog.critique",
        "trustlog.appended",
        "compliance.pending_review",
    }
    try:
        while True:
            try:
                item = await asyncio.to_thread(subscriber.get, timeout=15)
            except queue.Empty:
                await websocket.send_json({"type": "heartbeat", "ts": srv.utc_now_iso_z()})
                continue
            if item.get("type") in allowed_types:
                await websocket.send_json(item)
    except WebSocketDisconnect:
        logger.debug("trustlog ws disconnected")
    finally:
        srv._event_hub.unregister(subscriber)


# ------------------------------------------------------------------
# Compliance config
# ------------------------------------------------------------------

@router.get("/v1/compliance/config")
def compliance_get_config() -> Dict[str, Any]:
    """Return runtime compliance config for UI toggle."""
    return {"ok": True, "config": get_runtime_config()}


@router.put("/v1/compliance/config")
def compliance_put_config(body: ComplianceConfigBody) -> Dict[str, Any]:
    """Update runtime compliance config."""
    srv = _get_server()
    updated = update_runtime_config(
        eu_ai_act_mode=body.eu_ai_act_mode,
        safety_threshold=body.safety_threshold,
    )
    srv._publish_event("compliance.config.updated", {"config": updated})
    return {"ok": True, "config": updated}


# ------------------------------------------------------------------
# Reports
# ------------------------------------------------------------------

@router.get("/v1/report/eu_ai_act/{decision_id}")
def report_eu_ai_act(decision_id: str):
    """Generate an enterprise-ready EU AI Act compliance report."""
    srv = _get_server()
    try:
        result = srv.generate_eu_ai_act_report(decision_id)
        if not result.get("ok"):
            return JSONResponse(status_code=404, content=result)
        return result
    except Exception as e:
        logger.error("report_eu_ai_act failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to generate EU AI Act report"},
        )


@router.get("/v1/report/governance")
def report_governance(from_: str = Query(alias="from"), to: str = Query(alias="to")):
    """Generate internal governance report for the requested date range."""
    srv = _get_server()
    try:
        result = srv.generate_internal_governance_report((from_, to))
        return result
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "Invalid date format. Use ISO-8601 (e.g. 2026-01-01T00:00:00Z)",
            },
        )
    except Exception as e:
        logger.error("report_governance failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to generate governance report"},
        )


# ------------------------------------------------------------------
# System halt / resume (Art. 14(4))
# ------------------------------------------------------------------

@router.post("/v1/system/halt")
def system_halt(body: SystemHaltRequest):
    """Halt the AI decision system (Art. 14(4) emergency stop)."""
    srv = _get_server()
    try:
        result = srv.SystemHaltController.halt(
            reason=body.reason, operator=body.operator,
        )
        return {"ok": True, **result}
    except Exception as e:
        logger.error("system_halt failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to halt system"},
        )


@router.post("/v1/system/resume")
def system_resume(body: SystemResumeRequest):
    """Resume the AI decision system after a halt (Art. 14(4))."""
    srv = _get_server()
    try:
        result = srv.SystemHaltController.resume(
            operator=body.operator, comment=body.comment,
        )
        return {"ok": True, **result}
    except Exception as e:
        logger.error("system_resume failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to resume system"},
        )


@router.get("/v1/system/halt-status")
def system_halt_status():
    """Return the current halt status of the AI decision system."""
    srv = _get_server()
    try:
        halt_status = srv.SystemHaltController.status()
        return {"ok": True, **halt_status}
    except Exception as e:
        logger.error("system_halt_status failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to retrieve halt status"},
        )


@router.get("/v1/compliance/deployment-readiness")
def compliance_deployment_readiness():
    """Check deployment readiness for EU AI Act compliance (P1-5)."""
    srv = _get_server()
    try:
        result = srv.validate_deployment_readiness()
        return {"ok": True, **result}
    except Exception as e:
        logger.error("compliance_deployment_readiness failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to check deployment readiness"},
        )
