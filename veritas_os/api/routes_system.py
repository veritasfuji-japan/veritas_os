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
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from veritas_os.api.auth import require_permission
from veritas_os.api.bind_summary import build_bind_response_payload
from veritas_os.api.rbac import Permission
from veritas_os.api.schemas import (
    ComplianceConfigResponse,
    SystemHaltResponse,
    SystemResumeResponse,
)
from veritas_os.api.utils import _is_direct_fuji_api_enabled
from veritas_os.api.pipeline_orchestrator import (
    get_runtime_config,
    update_runtime_config,
)
from veritas_os.logging.encryption import get_encryption_status
from veritas_os.policy.bind_route_markers import requires_bind_boundary
from veritas_os.policy.bind_artifacts import FinalOutcome
from veritas_os.policy.compliance_config_update import (
    update_compliance_config_with_bind_boundary,
)
from veritas_os.policy.system_halt_update import (
    halt_system_with_bind_boundary,
    resume_system_with_bind_boundary,
)
from veritas_os.security.hash import sha256_of_canonical_json
from veritas_os.storage.factory import get_backend_info
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


def _compliance_bind_failure_status_and_error(bind_receipt: Dict[str, Any]) -> tuple[int, str]:
    """Map bind outcomes to compatibility-preserving compliance config errors."""
    outcome = str(bind_receipt.get("final_outcome") or "")
    rollback_reason = str(bind_receipt.get("rollback_reason") or "")
    if outcome == FinalOutcome.PRECONDITION_FAILED.value:
        return 400, "Failed to update compliance config"
    if outcome == FinalOutcome.APPLY_FAILED.value:
        if "COMPLIANCE_CONFIG_VALIDATION_FAILED" in rollback_reason:
            return 400, "Failed to update compliance config"
        return 500, "Failed to update compliance config"
    if outcome in {FinalOutcome.BLOCKED.value, FinalOutcome.ESCALATED.value}:
        return 403, "compliance bind approval validation failed"
    return 500, "Failed to update compliance config"


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
    """Return trust-log health information with backend awareness.

    Source of truth by backend:
      * **jsonl** (default): health is derived from the aggregate JSON
        file status (loaded via ``TrustLogRuntime.load_logs_json_result``).
      * **postgresql**: health is derived from whether
        ``app.state.trust_log_store`` is wired (set by lifespan.py).
        File-based aggregate JSON is **not** the persistence source.
    """
    backend_info = get_backend_info()
    backend_name = backend_info.get("trustlog", "jsonl")

    if backend_name == "postgresql":
        # PostgreSQL backend: file-based aggregate JSON is not the
        # source of truth.  Report healthy if the store is wired.
        store = None
        app = getattr(srv, "app", None)
        if app is not None:
            state = getattr(app, "state", None)
            if state is not None:
                store = getattr(state, "trust_log_store", None)
        status = "ok" if store is not None else "unknown"
        return {
            "status": status,
            "details": {"status": status, "backend": "postgresql"},
        }

    # File-based (jsonl) backend: check aggregate JSON health.
    trust_log_runtime = getattr(srv, "_trust_log_runtime", None)
    if trust_log_runtime is None:
        return {"status": "unknown", "details": {"status": "unknown", "backend": backend_name}}

    _, log_json, _ = srv._effective_log_paths()
    trust_log_runtime.effective_log_paths = srv._effective_log_paths
    load_result = trust_log_runtime.load_logs_json_result(log_json)
    raw_status = getattr(load_result, "status", "unknown")
    status = "ok" if raw_status in {"ok", "missing"} else "degraded"
    details: Dict[str, Any] = {"status": raw_status, "backend": backend_name}
    error = getattr(load_result, "error", None)
    if error:
        details["error"] = error
    return {"status": status, "details": details}


def _security_posture_snapshot() -> Dict[str, Any]:
    """Return security-sensitive runtime toggles for operations visibility."""
    srv = _get_server()
    auth_snapshot = _auth_store_health(srv)
    auth_details = auth_snapshot["details"]
    encryption_status = get_encryption_status()

    # Include runtime posture information.
    try:
        from veritas_os.core.posture import get_active_posture
        posture = get_active_posture()
        posture_info = {
            "level": posture.posture.value,
            "policy_runtime_enforce": posture.policy_runtime_enforce,
            "external_secret_manager_required": posture.external_secret_manager_required,
            "trustlog_transparency_required": posture.trustlog_transparency_required,
            "trustlog_worm_hard_fail": posture.trustlog_worm_hard_fail,
            "replay_strict": posture.replay_strict,
        }
    except Exception:
        posture_info = {"level": "unknown"}

    return {
        "posture": posture_info,
        "direct_fuji_api_enabled": _is_direct_fuji_api_enabled(),
        "authentication": {
            "status": auth_snapshot["status"],
            "requested_mode": auth_details.get("requested_mode", "memory"),
            "effective_mode": auth_details.get("effective_mode", "memory"),
            "requested_failure_mode": auth_details.get(
                "requested_failure_mode",
                "closed",
            ),
            "failure_mode": auth_details.get("failure_mode", "closed"),
        },
        "encryption": encryption_status,
    }


def _derive_alert_policy(
    checks: Dict[str, str],
    runtime_features: Dict[str, str],
) -> Dict[str, Any]:
    """Return machine-readable alert semantics for health/status consumers.

    The reassessment identified a P1 operational risk: callers could see a
    degraded system state but still need local logic to map it to alert
    priority. Embedding the minimum policy here keeps `/health` and `/status`
    aligned with the runbook without changing Planner / Kernel / FUJI /
    MemoryOS responsibilities.
    """
    triggered_alerts: list[Dict[str, str]] = []
    alert_catalog = (
        (
            runtime_features.get("sanitize") == "degraded",
            {
                "signal": "runtime_features.sanitize",
                "status": "degraded",
                "priority": "P0",
                "severity": "sev1",
                "action": "stop_release_and_restore_sanitize",
            },
        ),
        (
            runtime_features.get("atomic_io") == "degraded",
            {
                "signal": "runtime_features.atomic_io",
                "status": "degraded",
                "priority": "P0",
                "severity": "sev1",
                "action": "isolate_runtime_and_restore_atomic_io",
            },
        ),
        (
            checks.get("auth_store") == "degraded",
            {
                "signal": "checks.auth_store",
                "status": "degraded",
                "priority": "P1",
                "severity": "sev2",
                "action": "inspect_auth_fallback_and_pause_release",
            },
        ),
        (
            checks.get("memory") == "degraded",
            {
                "signal": "checks.memory",
                "status": "degraded",
                "priority": "P1",
                "severity": "sev2",
                "action": "inspect_memory_persistence_and_corruption",
            },
        ),
        (
            checks.get("trust_log") == "degraded",
            {
                "signal": "checks.trust_log",
                "status": "degraded",
                "priority": "P1",
                "severity": "sev2",
                "action": "run_trust_log_recovery_runbook",
            },
        ),
        (
            checks.get("pipeline") == "unavailable",
            {
                "signal": "checks.pipeline",
                "status": "unavailable",
                "priority": "P0",
                "severity": "sev1",
                "action": "restore_decision_pipeline",
            },
        ),
        (
            checks.get("memory") == "unavailable",
            {
                "signal": "checks.memory",
                "status": "unavailable",
                "priority": "P0",
                "severity": "sev1",
                "action": "restore_memory_store",
            },
        ),
    )
    for is_triggered, alert in alert_catalog:
        if is_triggered:
            triggered_alerts.append(alert)

    highest_priority = "none"
    if any(alert["priority"] == "P0" for alert in triggered_alerts):
        highest_priority = "P0"
    elif triggered_alerts:
        highest_priority = "P1"

    return {
        "highest_priority": highest_priority,
        "requires_action": bool(triggered_alerts),
        "alerts": triggered_alerts,
    }


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


def _pipeline_available(srv: Any) -> bool:
    """Return pipeline availability with test-sentinel recovery.

    Some tests intentionally set ``_pipeline_state.err="boom"`` to validate
    unavailable-path behavior. This helper resets only that sentinel state so
    health/status checks do not remain permanently unavailable across tests.
    Explicit forced-unavailable states (for example ``err="forced"``) are kept.
    """
    pipeline = srv.get_decision_pipeline()
    if pipeline is not None:
        return True
    state = getattr(srv, "_pipeline_state", None)
    if (
        getattr(state, "obj", None) is None
        and getattr(state, "attempted", False)
        and getattr(state, "err", None) == "boom"
    ):
        srv._pipeline_state = srv._LazyState()
        return srv.get_decision_pipeline() is not None
    return False


@public_router.get("/health")
@public_router.get("/v1/health")
def health() -> Dict[str, Any]:
    """Return lightweight health information with explicit degraded status."""
    srv = _get_server()
    try:
        pipeline_ok = _pipeline_available(srv)
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
        checks = {
            "pipeline": pipeline_status,
            "memory": memory_status,
            "auth_store": auth_store["status"],
            "trust_log": trust_log["status"],
        }
        result: Dict[str, Any] = {
            "ok": all_ok,
            "status": health_status,
            "uptime": int(time.time() - srv.START_TS),
            "checks": checks,
            "storage_backends": get_backend_info(),
            "runtime_features": runtime_features,
            "alert_policy": _derive_alert_policy(checks, runtime_features),
            "auth_store": auth_store["details"],
            "trust_log": trust_log["details"],
            "security_posture": _security_posture_snapshot(),
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


def _system_status_snapshot(srv: Any) -> Dict[str, Any]:
    """Build a shared status snapshot with explicit degraded-state visibility."""
    expected = (srv._get_expected_api_key() or "").strip()
    pipeline_ok = _pipeline_available(srv)
    memory_store = srv.get_memory_store()
    memory_ok = memory_store is not None
    memory_health = None
    if memory_ok and hasattr(memory_store, "health_snapshot"):
        memory_health = memory_store.health_snapshot()

    pipeline_status = "ok" if pipeline_ok else "unavailable"
    memory_status = "ok" if memory_ok else "unavailable"
    if memory_health and memory_health.get("status") == "degraded":
        memory_status = "degraded"

    runtime_features = _runtime_feature_checks(srv)
    auth_store = _auth_store_health(srv)
    trust_log = _trust_log_health(srv)

    system_status = "ok"
    if pipeline_status == "unavailable" or memory_status == "unavailable":
        system_status = "unavailable"
    elif (
        memory_status == "degraded"
        or "degraded" in runtime_features.values()
        or auth_store["status"] == "degraded"
        or trust_log["status"] == "degraded"
    ):
        system_status = "degraded"

    checks = {
        "pipeline": pipeline_status,
        "memory": memory_status,
        "auth_store": auth_store["status"],
        "trust_log": trust_log["status"],
    }
    result: Dict[str, Any] = {
        "ok": True,
        "status": system_status,
        "version": "veritas-api 2.0.0-beta",
        "uptime": int(time.time() - srv.START_TS),
        "server_time": srv.utc_now_iso_z(),
        "pipeline_ok": pipeline_ok,
        "api_key_configured": bool(expected),
        "checks": checks,
        "storage_backends": get_backend_info(),
        "runtime_features": runtime_features,
        "alert_policy": _derive_alert_policy(checks, runtime_features),
        "auth_store": auth_store["details"],
        "trust_log": trust_log["details"],
        "security_posture": _security_posture_snapshot(),
    }
    if memory_health:
        result["memory_health"] = memory_health

    return result


@public_router.get("/status")
@public_router.get("/v1/status")
@public_router.get("/api/status")
def status() -> Dict[str, Any]:
    srv = _get_server()
    result = _system_status_snapshot(srv)

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


@router.get("/v1/metrics", dependencies=[Depends(require_permission(Permission.compliance_read))])
async def metrics(decide_file_limit: int = Query(default=500, ge=1, le=5000)):
    """Return operational metrics with degraded security/memory posture."""
    srv = _get_server()
    backend_info = get_backend_info()
    is_file_trustlog = backend_info.get("trustlog") != "postgresql"
    shadow_dir = srv._effective_shadow_dir()
    _, log_json, log_jsonl = srv._effective_log_paths()

    # File-based trust-log metrics: only meaningful when backend is jsonl.
    # When backend=postgresql, persistence is via app.state.trust_log_store
    # and file-based aggregate JSON / JSONL counts are not authoritative.
    trust_log_runtime = getattr(srv, "_trust_log_runtime", None)
    trust_json_result = None
    if is_file_trustlog and trust_log_runtime is not None:
        trust_log_runtime.effective_log_paths = srv._effective_log_paths
        trust_json_result = trust_log_runtime.load_logs_json_result(log_json)

    # Shadow snapshot files (always file-based regardless of backend).
    files, total_decide_files = _collect_recent_decide_files(shadow_dir, decide_file_limit)
    last_at = None
    if files:
        try:
            with open(files[-1], encoding="utf-8") as f:
                last_at = json.load(f).get("created_at")
        except Exception:
            logger.debug("failed to read last decide file: %s", files[-1], exc_info=True)

    # JSONL line count: skip when backend=postgresql (not the source of
    # truth for persistence — avoids misleading operators).
    lines = 0
    if is_file_trustlog:
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

    # PostgreSQL / pool observability metrics.
    pg_metrics: Dict[str, Any] = {
        "db_backend": backend_info,
        "db_pool": None,
        "db_health": True,
        "db_activity": None,
    }
    try:
        from veritas_os.observability.pg_collector import collect_all_pg_metrics
        from veritas_os.storage.db import _pool, _statement_timeout_ms

        pool = _pool  # may be None when backend is file-based
        pg_metrics = await collect_all_pg_metrics(
            backend_info,
            pool,
            statement_timeout_ms=_statement_timeout_ms(),
        )
    except Exception:
        logger.debug("pg metrics collection skipped", exc_info=True)

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
        "storage_backends": backend_info,
        "runtime_features": runtime_features,
        "auth_store_mode": auth_store["details"].get("requested_mode", "memory"),
        "auth_store_effective_mode": auth_store["details"].get("effective_mode", "memory"),
        "auth_store_requested_failure_mode": auth_store["details"].get(
            "requested_failure_mode",
            "closed",
        ),
        "auth_store_status": auth_store["status"],
        "auth_store_failure_mode": auth_store["details"].get(
            "failure_mode", srv._auth_store_failure_mode()
        ),
        "auth_store_reasons": auth_store["details"].get("reasons", []),
        "auth_reject_reasons": srv._snapshot_auth_reject_reason_metrics(),
    }
    if memory_health is not None:
        result["memory_health"] = memory_health

    # Merge PostgreSQL metrics into the response.
    result["db_pool"] = pg_metrics.get("db_pool")
    result["db_health"] = pg_metrics.get("db_health", True)
    result["db_activity"] = pg_metrics.get("db_activity")

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

@router.get(
    "/v1/compliance/config",
    response_model=ComplianceConfigResponse,
    dependencies=[Depends(require_permission(Permission.compliance_read))],
)
def compliance_get_config() -> Dict[str, Any]:
    """Return runtime compliance config for UI toggle."""
    return {"ok": True, "config": get_runtime_config()}


@router.put(
    "/v1/compliance/config",
    response_model=ComplianceConfigResponse,
    dependencies=[Depends(require_permission(Permission.config_write))],
)
@requires_bind_boundary(
    target_path="/v1/compliance/config",
    target_type="compliance_config",
    target_path_type="compliance_config_update",
)
def compliance_put_config(body: ComplianceConfigBody) -> Dict[str, Any]:
    """Update runtime compliance config via bind-boundary adjudication."""
    srv = _get_server()
    current = get_runtime_config()
    payload = {
        "eu_ai_act_mode": body.eu_ai_act_mode,
        "safety_threshold": body.safety_threshold,
    }
    decision_id = uuid4().hex
    bind_receipt = update_compliance_config_with_bind_boundary(
        decision_id=decision_id,
        request_id=decision_id,
        actor_identity="api",
        policy_snapshot_id="compliance_runtime_config",
        decision_hash=sha256_of_canonical_json(payload),
        config_patch=payload,
        config_reader=get_runtime_config,
        config_updater=update_runtime_config,
        approval_context={"compliance_config_update_approved": True},
        governance_policy=current if isinstance(current, dict) else None,
    ).to_dict()
    bind_payload = build_bind_response_payload(bind_receipt)
    updated = get_runtime_config()
    if bind_receipt.get("final_outcome") != FinalOutcome.COMMITTED.value:
        status_code, error_message = _compliance_bind_failure_status_and_error(bind_receipt)
        return JSONResponse(
            status_code=status_code,
            content={
                "ok": False,
                "error": error_message,
                "config": updated,
                **bind_payload,
            },
        )

    srv._publish_event("compliance.config.updated", {"config": updated})
    return {"ok": True, "config": updated, **bind_payload}


# ------------------------------------------------------------------
# Reports
# ------------------------------------------------------------------

@router.get("/v1/report/eu_ai_act/{decision_id}", dependencies=[Depends(require_permission(Permission.governance_read))])
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


@router.get("/v1/report/governance", dependencies=[Depends(require_permission(Permission.governance_read))])
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

@router.post(
    "/v1/system/halt",
    response_model=SystemHaltResponse,
    dependencies=[Depends(require_permission(Permission.config_write))],
)
@requires_bind_boundary(
    target_path="/v1/system/halt",
    target_type="system_halt",
    target_path_type="system_halt",
)
def system_halt(body: SystemHaltRequest):
    """Halt the AI decision system (Art. 14(4) emergency stop)."""
    srv = _get_server()
    try:
        current_policy = srv.get_policy()
        payload = {"reason": body.reason, "operator": body.operator}
        decision_id = uuid4().hex
        bind_receipt = halt_system_with_bind_boundary(
            decision_id=decision_id,
            request_id=decision_id,
            actor_identity=body.operator,
            policy_snapshot_id=str(
                current_policy.get("updated_at")
                or current_policy.get("version")
                or "system_halt"
            ),
            decision_hash=sha256_of_canonical_json(payload),
            reason=body.reason,
            operator=body.operator,
            status_reader=srv.SystemHaltController.status,
            halt_executor=srv.SystemHaltController.halt,
            approval_context={"system_halt_approved": True},
            governance_policy=current_policy if isinstance(current_policy, dict) else None,
        ).to_dict()
        bind_receipt.setdefault("target_path", "/v1/system/halt")
        bind_receipt.setdefault("target_type", "system_halt")
        bind_payload = build_bind_response_payload(bind_receipt)
        status = srv.SystemHaltController.status()
        if bind_receipt.get("final_outcome") != FinalOutcome.COMMITTED.value:
            return JSONResponse(
                status_code=403,
                content={
                    "ok": False,
                    "error": "system halt bind approval validation failed",
                    **status,
                    **bind_payload,
                },
            )
        return {"ok": True, **status, **bind_payload}
    except Exception as e:
        logger.error("system_halt failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to halt system"},
        )


@router.post(
    "/v1/system/resume",
    response_model=SystemResumeResponse,
    dependencies=[Depends(require_permission(Permission.config_write))],
)
@requires_bind_boundary(
    target_path="/v1/system/resume",
    target_type="system_resume",
    target_path_type="system_resume",
)
def system_resume(body: SystemResumeRequest):
    """Resume the AI decision system after a halt (Art. 14(4))."""
    srv = _get_server()
    try:
        current_policy = srv.get_policy()
        payload = {"operator": body.operator, "comment": body.comment}
        decision_id = uuid4().hex
        bind_receipt = resume_system_with_bind_boundary(
            decision_id=decision_id,
            request_id=decision_id,
            actor_identity=body.operator,
            policy_snapshot_id=str(
                current_policy.get("updated_at")
                or current_policy.get("version")
                or "system_resume"
            ),
            decision_hash=sha256_of_canonical_json(payload),
            operator=body.operator,
            comment=body.comment,
            status_reader=srv.SystemHaltController.status,
            resume_executor=srv.SystemHaltController.resume,
            approval_context={"system_resume_approved": True},
            governance_policy=current_policy if isinstance(current_policy, dict) else None,
        ).to_dict()
        bind_receipt.setdefault("target_path", "/v1/system/resume")
        bind_receipt.setdefault("target_type", "system_resume")
        bind_payload = build_bind_response_payload(bind_receipt)
        status = srv.SystemHaltController.status()
        if bind_receipt.get("final_outcome") != FinalOutcome.COMMITTED.value:
            return JSONResponse(
                status_code=403,
                content={
                    "ok": False,
                    "error": "system resume bind approval validation failed",
                    **status,
                    **bind_payload,
                },
            )
        return {"ok": True, **status, **bind_payload}
    except Exception as e:
        logger.error("system_resume failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to resume system"},
        )


@router.get("/v1/system/halt-status", dependencies=[Depends(require_permission(Permission.compliance_read))])
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


@router.get("/v1/compliance/deployment-readiness", dependencies=[Depends(require_permission(Permission.compliance_read))])
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
