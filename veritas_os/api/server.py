# veritas_os/api/server.py
from __future__ import annotations

import hashlib
import heapq
import hmac
import importlib
import json
import logging
import math
import queue
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional, Protocol, Tuple

# ---- ロガー設定（標準化: print → logging）----
logger = logging.getLogger(__name__)

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Security,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security.api_key import APIKeyHeader

# ---- API層（ここは基本 "安定" 前提）----
from veritas_os.api.schemas import (
    DecideRequest,
    DecideResponse,
    FujiDecision,
    MemoryEraseRequest,
    MemoryGetRequest,
    MemoryPutRequest,
    MemorySearchRequest,
    TrustFeedbackRequest,
)
from veritas_os.api.governance import (
    enforce_four_eyes_approval,
    get_policy,
    get_policy_history,
    get_value_drift,
    update_policy,
)
from veritas_os.compliance.report_engine import (
    generate_eu_ai_act_report,
    generate_internal_governance_report,
)
from veritas_os.reporting.exporters import build_w3c_prov_document
from veritas_os.replay.replay_engine import run_replay
from veritas_os.api.constants import (
    DECISION_ALLOW,
    DECISION_REJECTED,
    MAX_LOG_FILE_SIZE,
    MAX_RAW_BODY_LENGTH,
    VALID_MEMORY_KINDS,
)  # noqa: F401
from veritas_os.api.pipeline_orchestrator import (
    ComplianceStopException,
    enforce_compliance_stop,
    get_runtime_config,
    resolve_dynamic_steps,
    update_runtime_config,
)
from veritas_os.core.config import eu_ai_act_cfg
from veritas_os.core.eu_ai_act_compliance_module import (
    SystemHaltController,
    validate_deployment_readiness,
)

from pydantic import BaseModel, Field

from veritas_os.logging.trust_log import (
    get_trust_log_page,
    get_trust_logs_by_request,
)
from veritas_os.audit.trustlog_signed import (
    export_signed_trustlog,
    verify_trustlog_chain,
)

from veritas_os.api.sse_hub import (
    SSEEventHub,
    format_sse_message,
    publish_event_best_effort,
)
from veritas_os.api.log_path_resolver import (
    effective_log_paths,
    effective_shadow_dir,
)
from veritas_os.api.trust_log_runtime import TrustLogRuntime

try:
    from veritas_os.observability.middleware import observe_request_metrics
    from veritas_os.observability.exporters import configure_metrics_exporter
except Exception:  # pragma: no cover - optional observability dependency
    observe_request_metrics = None  # type: ignore

    def configure_metrics_exporter(app: Any, auth_dependency: Optional[Any] = None) -> str:
        return "none"

from veritas_os.api.dependency_resolver import (
    LazyState,
    resolve_cfg,
    resolve_decision_pipeline,
    resolve_fuji_core,
    resolve_memory_store,
    resolve_value_core,
)

# ---- アトミック I/O（信頼性向上）----
try:
    from veritas_os.core.atomic_io import atomic_append_line, atomic_write_json
    _HAS_ATOMIC_IO = True
except Exception as _atomic_import_err:
    _HAS_ATOMIC_IO = False
    atomic_append_line = None  # type: ignore
    atomic_write_json = None  # type: ignore
    logger.warning("atomic_io import failed, using fallback: %s", _atomic_import_err)

# ---- LLM 接続プール管理 ----
try:
    from veritas_os.core.llm_client import close_pool as _close_llm_pool
except Exception:
    _close_llm_pool = None  # type: ignore

# ---- PII検出・マスク（sanitize.py から。失敗時はフォールバック）----
try:
    from veritas_os.core.sanitize import mask_pii as _sanitize_mask_pii
    _HAS_SANITIZE = True
except Exception as _sanitize_import_err:
    _HAS_SANITIZE = False
    _sanitize_mask_pii = None  # type: ignore
    logger.warning("sanitize import failed, PII masking disabled: %s", _sanitize_import_err)

# ============================================================
# ISSUE-4 方針:
# - import時に "重い/脆い" モジュールを確定importしない
# - /health は必ず 200
# - /v1/decide は依存が壊れてたら 503 で返す（落ちない）
# ============================================================

REPO_ROOT = Path(__file__).resolve().parents[1]  # .../veritas_os
START_TS = time.time()

# ---- .env（dotenv が無い/壊れていても server import は落とさない）----
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(REPO_ROOT / ".env")
except Exception as e:
    logger.warning("dotenv load failed: %s: %s", type(e).__name__, e)


try:
    from veritas_os.core.utils import utc_now_iso_z
except Exception as _utils_import_err:
    logger.debug("utils import failed, using fallback utc_now_iso_z: %s", _utils_import_err)
    def utc_now_iso_z() -> str:  # type: ignore[misc]
        """UTC now helper（fallback: utils import failed）"""
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ==============================
# Backward-compat exports (TESTS EXPECT THESE)
# ==============================
# tests monkeypatch:
# - server.value_core.append_trust_log
# - server.fuji_core.validate_action / validate
# - server.MEMORY_STORE.search/get
# - server.LOG_DIR / LOG_JSON / LOG_JSONL / SHADOW_DIR
#
# これらは import 時に必ず存在させる。実体は lazy import で後から差し替える。

_DEFAULT_LOG_DIR = (REPO_ROOT / "logs").resolve()
_DEFAULT_LOG_JSON = _DEFAULT_LOG_DIR / "trust_log.json"
_DEFAULT_LOG_JSONL = _DEFAULT_LOG_DIR / "trust_log.jsonl"
_DEFAULT_SHADOW_DIR = _DEFAULT_LOG_DIR / "DASH"

# LEGACY COMPAT: File-based log path constants.
# ─────────────────────────────────────────────────────────────
# Purpose:
#   Tests monkeypatch these (server.LOG_DIR, server.LOG_JSON, etc.).
#   They are the *persistence path* ONLY when VERITAS_TRUSTLOG_BACKEND=jsonl
#   (the default).
#
# When backend=postgresql:
#   • These paths are NOT the persistence source of truth.
#   • Persistence is handled entirely by app.state.trust_log_store
#     (set via lifespan.py → storage.factory.create_trust_log_store).
#   • Shadow snapshot writes (_effective_shadow_dir) still use local
#     files regardless of backend for replay / audit.
#   • /v1/metrics reads these paths for shadow file counts only;
#     JSONL line counts and aggregate JSON status are skipped.
#
# Migration: New code SHOULD use app.state.trust_log_store (via
#   dependency_resolver.get_trust_log_store) for TrustLog persistence.
#   Use _is_file_trustlog_backend() to guard file-only code paths.
# ─────────────────────────────────────────────────────────────
LOG_DIR: Path = _DEFAULT_LOG_DIR
LOG_JSON: Path = _DEFAULT_LOG_JSON
LOG_JSONL: Path = _DEFAULT_LOG_JSONL
SHADOW_DIR: Path = _DEFAULT_SHADOW_DIR


def _is_file_trustlog_backend() -> bool:
    """Return True when the TrustLog backend is file-based (jsonl).

    Use this predicate to guard code paths that read/write trust-log
    files (aggregate JSON, JSONL append, JSONL line counts).  When the
    backend is ``postgresql``, persistence is handled by
    ``app.state.trust_log_store`` and file I/O is not the source of truth.

    Shadow snapshot writes and replay artifacts are always file-based
    regardless of this flag.
    """
    from veritas_os.api.dependency_resolver import is_file_backend

    return is_file_backend()


def _effective_log_paths() -> Tuple[Path, Path, Path]:
    """Backward-compatible wrapper for trust-log path resolution."""
    return effective_log_paths(
        log_dir=LOG_DIR,
        log_json=LOG_JSON,
        log_jsonl=LOG_JSONL,
        default_log_dir=_DEFAULT_LOG_DIR,
        default_log_json=_DEFAULT_LOG_JSON,
        default_log_jsonl=_DEFAULT_LOG_JSONL,
    )


def _effective_shadow_dir() -> Path:
    """Backward-compatible wrapper for shadow directory resolution."""
    log_dir, _, _ = _effective_log_paths()
    return effective_shadow_dir(
        shadow_dir=SHADOW_DIR,
        log_dir=log_dir,
        default_shadow_dir=_DEFAULT_SHADOW_DIR,
        default_log_dir=_DEFAULT_LOG_DIR,
    )


# ==============================
# Placeholder stubs (tests expect attributes to EXIST at import time)
# ==============================

def _is_placeholder(obj: Any) -> bool:
    return bool(getattr(obj, "__veritas_placeholder__", False))


def _fuji_validate_stub(action: str, context: dict) -> dict:
    return {
        "status": "allow",
        "reasons": ["stub"],
        "violations": [],
        "risk": 0.0,
        "modifications": [],
        "action": action,
    }


def _append_trust_log_stub(*args: Any, **kwargs: Any) -> None:
    return None


def _memory_search_stub(*args: Any, **kwargs: Any):
    return []


def _memory_get_stub(*args: Any, **kwargs: Any):
    return None


# place-holders that are always present (so monkeypatch.setattr won't fail)
fuji_core: Any = SimpleNamespace(
    __veritas_placeholder__=True,
    validate_action=_fuji_validate_stub,
    validate=_fuji_validate_stub,
)
value_core: Any = SimpleNamespace(
    __veritas_placeholder__=True,
    append_trust_log=_append_trust_log_stub,
)
MEMORY_STORE: Any = SimpleNamespace(
    __veritas_placeholder__=True,
    search=_memory_search_stub,
    get=_memory_get_stub,
)


# ==============================
# Lazy import helpers / caches
# ==============================

class _LazyState(LazyState):
    """Backward-compatible alias for dependency_resolver.LazyState."""



_cfg_state = _LazyState()
_pipeline_state = _LazyState()
_fuji_state = _LazyState()
_value_core_state = _LazyState()
_memory_store_state = _LazyState()


class _SSEEventHub(SSEEventHub):
    """Backward-compat wrapper expected by legacy tests."""

    def __init__(self, history_size: int = 128):
        super().__init__(timestamp_factory=utc_now_iso_z, history_size=history_size)


_event_hub = _SSEEventHub()


def _publish_event(event_type: str, payload: Dict[str, Any]) -> None:
    """Best-effort SSE event publication. Must never break API handlers."""
    publish_event_best_effort(event_hub=_event_hub, event_type=event_type, payload=payload)


def _format_sse_message(event: Dict[str, Any]) -> str:
    """Format one SSE event frame."""
    return format_sse_message(event)


try:
    update_runtime_config(
        eu_ai_act_mode=bool(eu_ai_act_cfg.eu_ai_act_mode),
        safety_threshold=float(eu_ai_act_cfg.safety_threshold),
    )
except ValueError:
    logger.warning(
        "Invalid VERITAS_SAFETY_THRESHOLD=%s. Falling back to 0.8.",
        eu_ai_act_cfg.safety_threshold,
    )
    update_runtime_config(eu_ai_act_mode=bool(eu_ai_act_cfg.eu_ai_act_mode), safety_threshold=0.8)


# ==============================
# Imported utility functions (backward-compat re-exports)
# ==============================

from veritas_os.api.utils import (  # noqa: E402,F401
    _errstr,
    _stage_summary,
    redact,
    _gen_request_id,
    _coerce_alt_list,
    _coerce_decide_payload,
    _coerce_fuji_payload,
    _decide_example,
    DECIDE_GENERIC_ERROR,
    _log_decide_failure,
    _classify_decide_failure,
    _is_debug_mode,
    _is_direct_fuji_api_enabled,
)


# ==============================
# Lazy getters for core modules
# ==============================

def get_cfg() -> Any:
    """
    cfg は "無い/壊れてる" 可能性があるので必ずフォールバックを返す。
    CORS設定など起動に関わるため、ここで絶対に例外を外へ出さない。
    """
    global _cfg_state
    return resolve_cfg(_cfg_state, errstr=_errstr, logger=logger)


def get_decision_pipeline() -> Optional[Any]:
    """
    pipeline は壊れていても server を落とさない。
    /v1/decide 呼び出し時に 503 へ変換する。
    """
    global _pipeline_state
    return resolve_decision_pipeline(_pipeline_state, errstr=_errstr, logger=logger)


def get_fuji_core() -> Optional[Any]:
    """
    - tests: monkeypatch server.fuji_core を「任意のオブジェクト」に差し替える
      → その場合は絶対にそれを尊重して返す（lazy import で上書きしない）
    - prod : placeholder のままなら lazy import して module を返す（差し替え）
    """
    global _fuji_state, fuji_core

    resolved, updated_fuji_core = resolve_fuji_core(
        _fuji_state,
        current_fuji_core=fuji_core,
        is_placeholder=_is_placeholder,
        fuji_validate_stub=_fuji_validate_stub,
        errstr=_errstr,
        logger=logger,
    )
    fuji_core = updated_fuji_core
    return resolved


def get_value_core() -> Optional[Any]:
    """
    - tests: monkeypatch server.value_core.append_trust_log
    - prod : placeholder のままなら lazy import して module を返す（差し替え）
    """
    global _value_core_state, value_core

    resolved, updated_value_core = resolve_value_core(
        _value_core_state,
        current_value_core=value_core,
        is_placeholder=_is_placeholder,
        append_trust_log_stub=_append_trust_log_stub,
        errstr=_errstr,
        logger=logger,
    )
    value_core = updated_value_core
    return resolved


def get_memory_store() -> Optional[Any]:
    """
    - tests: monkeypatch server.MEMORY_STORE.search/get
    - prod : placeholder のままなら veritas_os.core.memory の MEM を lazy 取得して更新
    """
    global _memory_store_state, MEMORY_STORE
    resolved, updated_memory_store = resolve_memory_store(
        _memory_store_state,
        current_memory_store=MEMORY_STORE,
        is_placeholder=_is_placeholder,
        memory_search_stub=_memory_search_stub,
        memory_get_stub=_memory_get_stub,
        errstr=_errstr,
        logger=logger,
    )
    MEMORY_STORE = updated_memory_store
    return resolved


# ==============================
# FastAPI app init (must not crash)
# ==============================

cfg = get_cfg()

def _should_fail_fast_startup(profile: Optional[str] = None) -> bool:
    """Return whether startup validation failures should stop app boot."""
    from veritas_os.api.startup_health import should_fail_fast_startup

    return should_fail_fast_startup(profile)


def _run_startup_config_validation() -> None:
    """Validate startup configuration with environment-specific strictness."""
    from veritas_os.api.startup_health import run_startup_config_validation

    run_startup_config_validation(
        logger=logger,
        should_fail_fast=_should_fail_fast_startup,
        validator=globals().get("validate_startup_config"),
    )


def _check_runtime_feature_health() -> None:
    """Warn about degraded runtime features so operators are never silently misled."""
    from veritas_os.api.startup_health import check_runtime_feature_health

    check_runtime_feature_health(
        logger=logger,
        has_sanitize=_HAS_SANITIZE,
        has_atomic_io=_HAS_ATOMIC_IO,
    )


# ==============================
# Auth imports (backward-compat re-exports from extracted modules)
# ==============================

from veritas_os.api.auth import (  # noqa: E402,F401
    AuthSecurityStore,
    InMemoryAuthSecurityStore,
    RedisAuthSecurityStore,
    _AUTH_SECURITY_STORE,
    _AUTH_REJECT_REASON_METRICS,
    _AUTH_REJECT_REASON_LOCK,
    _record_auth_reject_reason,
    _snapshot_auth_reject_reason_metrics,
    _AUTH_FAIL_RATE_LIMIT,
    _AUTH_FAIL_WINDOW,
    _AUTH_FAIL_BUCKET_MAX,
    _auth_fail_bucket,
    _auth_fail_lock,
    _cleanup_auth_fail_bucket_unsafe,
    _auth_store_failure_mode,
    auth_store_health_snapshot,
    _auth_store_register_nonce,
    _auth_store_increment_auth_failure,
    _auth_store_increment_rate_limit,
    _create_auth_security_store,
    API_KEY_DEFAULT,
    api_key_scheme,
    _resolve_expected_api_key_with_source,
    _get_expected_api_key,
    _resolve_client_ip,
    _enforce_auth_failure_rate_limit,
    require_api_key,
    _derive_api_user_id,
    _resolve_memory_user_id,
    require_api_key_header_or_query,
    _allow_sse_query_api_key,
    _authenticate_websocket_api_key,
    _allow_ws_query_api_key,
    _env_int_safe,
    _NONCE_TTL_SEC,
    _NONCE_MAX_LENGTH,
    API_SECRET,
    _DEFAULT_API_SECRET_PLACEHOLDER,
    _is_placeholder_secret,
    _get_api_secret,
    _check_and_register_nonce,
    verify_signature,
    _check_multiworker_auth_store,
    _parse_api_keys_config,
    _is_valid_api_key,
    resolve_role_for_key,
    _resolve_role_from_request,
    require_permission,
)
from veritas_os.api.rbac import (  # noqa: E402,F401
    Role,
    Permission,
    ROLE_PERMISSIONS,
    RBACPolicy,
)

# Keep _log_api_key_source_once in server.py so tests that patch server.logger work
@lru_cache(maxsize=4)
def _log_api_key_source_once(source: str) -> None:
    """Log API key source with fixed messages to avoid secret-log findings."""
    if source == "env":
        logger.info("Resolved API key source: env")
        return
    if source == "api_key_default":
        logger.info("Resolved API key source: api_key_default")
        return
    if source == "config":
        logger.info("Resolved API key source: config")
        return
    logger.info("Resolved API key source: missing")

from veritas_os.api.rate_limiting import (  # noqa: E402,F401
    _RATE_LIMIT,
    _RATE_WINDOW,
    _RATE_BUCKET_MAX,
    _rate_bucket,
    _rate_lock,
    _cleanup_rate_bucket_unsafe,
    _cleanup_rate_bucket,
    enforce_rate_limit,
    _NONCE_MAX,
    _nonce_store,
    _nonce_lock,
    _cleanup_nonces_unsafe,
    _cleanup_nonces,
    _start_nonce_cleanup_scheduler,
    _stop_nonce_cleanup_scheduler,
    _RATE_CLEANUP_INTERVAL,
    _start_rate_cleanup_scheduler,
    _stop_rate_cleanup_scheduler,
)
import veritas_os.api.rate_limiting as _rate_mod  # noqa: E402


# ==============================
# Middleware imports (backward-compat re-exports from extracted modules)
# ==============================

from veritas_os.api.middleware import (  # noqa: E402,F401
    DEFAULT_MAX_REQUEST_BODY_SIZE,
    PROFILE_MAX_REQUEST_BODY_SIZE,
    _resolve_max_request_body_size,
    MAX_REQUEST_BODY_SIZE,
    TRACE_ID_HEADER_NAME,
    _TRACE_ID_PATTERN,
    _resolve_trace_id_from_request,
    _inflight_count,
    _inflight_lock,
    _shutting_down,
    _inflight_snapshot,
    attach_trace_id,
    add_response_time,
    add_rate_limit_headers,
    track_inflight_requests,
    limit_body_size,
    add_security_headers,
)


# ==============================
# Lifespan manager
# ==============================

@asynccontextmanager
async def _app_lifespan(_: FastAPI):
    """Manage startup/shutdown actions using FastAPI lifespan API."""
    from veritas_os.api.lifespan import run_lifespan

    async with run_lifespan(
        app=app,
        startup_validation=_run_startup_config_validation,
        runtime_health_check=_check_runtime_feature_health,
        check_multiworker_auth_store=_check_multiworker_auth_store,
        start_nonce_cleanup_scheduler=_start_nonce_cleanup_scheduler,
        start_rate_cleanup_scheduler=_start_rate_cleanup_scheduler,
        stop_nonce_cleanup_scheduler=_stop_nonce_cleanup_scheduler,
        stop_rate_cleanup_scheduler=_stop_rate_cleanup_scheduler,
        close_llm_pool=_close_llm_pool,
        logger=logger,
    ):
        yield


app = FastAPI(title="VERITAS Public API", version="1.0.3", lifespan=_app_lifespan)

# ★ セキュリティ: allow_credentials は明示的なオリジンが設定されている場合のみ True
def _resolve_cors_settings(origins: Any) -> tuple[list[str], bool]:
    """Resolve safe CORS settings from config values."""
    from veritas_os.api.cors_settings import resolve_cors_settings

    return resolve_cors_settings(origins=origins, logger=logger)


_cors_origins, _cors_allow_credentials = _resolve_cors_settings(
    getattr(cfg, "cors_allow_origins", []),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=[
        "X-API-Key",
        "X-Timestamp",
        "X-Nonce",
        "X-Signature",
        "X-VERITAS-TIMESTAMP",
        "X-VERITAS-NONCE",
        "X-VERITAS-SIGNATURE",
        "Content-Type",
        "Authorization",
    ],
)

# Register all HTTP middleware from the middleware module
app.middleware("http")(attach_trace_id)
app.middleware("http")(add_response_time)
app.middleware("http")(add_rate_limit_headers)
app.middleware("http")(track_inflight_requests)
app.middleware("http")(limit_body_size)
app.middleware("http")(add_security_headers)
if observe_request_metrics is not None:
    app.middleware("http")(observe_request_metrics)

configure_metrics_exporter(app, auth_dependency=require_api_key)

# ==============================
# 422 error handler
# ==============================

@app.exception_handler(RequestValidationError)
async def on_validation_error(request: Request, exc: RequestValidationError):
    """Handle validation errors with limited information disclosure."""
    trace_id = (
        getattr(request.state, "trace_id", None)
        if hasattr(request, "state") else None
    ) or secrets.token_hex(16)

    # Sanitize errors: Pydantic v2 ctx may contain non-serializable objects
    safe_errors = []
    for err in exc.errors():
        safe_err = {
            "type": err.get("type"),
            "loc": err.get("loc"),
            "msg": err.get("msg"),
        }
        ctx = err.get("ctx")
        if ctx:
            safe_err["ctx"] = {k: str(v) for k, v in ctx.items()}
        safe_errors.append(safe_err)

    content: Dict[str, Any] = {
        "detail": safe_errors,
        "request_id": trace_id,
        "hint": {"expected_example": _decide_example()},
    }

    if _is_debug_mode():
        raw_body_bytes = await request.body()
        raw = raw_body_bytes.decode("utf-8", "replace") if raw_body_bytes else ""
        raw_safe = redact(raw)[:MAX_RAW_BODY_LENGTH]
        content["raw_body"] = raw_safe

    return JSONResponse(status_code=422, content=content)


# ==============================
# Trust log helpers（server 側でも軽く読めるように）
# ==============================
# LEGACY COMPAT: The helpers below wrap file-based trust-log I/O
# (aggregate JSON load, JSONL append, shadow snapshot writes).
#
# Source-of-truth mapping:
#   ┌─────────────────────────┬───────────────────────────────────────┐
#   │ Backend                 │ Persistence source of truth          │
#   ├─────────────────────────┼───────────────────────────────────────┤
#   │ jsonl (default)         │ These helpers → LOG_JSONL / LOG_JSON │
#   │ postgresql              │ app.state.trust_log_store (DI)       │
#   └─────────────────────────┴───────────────────────────────────────┘
#
# Shadow snapshot writes (_effective_shadow_dir / write_shadow_decide)
# are always file-based regardless of backend — they serve replay and
# audit workflows, not primary persistence.
#
# These wrappers remain for:
#   1. Test backward-compatibility — many tests monkeypatch
#      server.LOG_DIR / server._load_logs_json / server.append_trust_log.
#   2. Shadow snapshot writes (always file-based).
#   3. /v1/metrics file-based health checks (guarded by
#      _is_file_trustlog_backend() in routes_system.py).
#
# Migration guidance:
#   New code SHOULD use app.state.trust_log_store (via
#   dependency_resolver.get_trust_log_store) rather than calling
#   these helpers directly.


def _load_logs_json(path: Optional[Path] = None) -> list:
    """
    tests 互換:
      - _load_logs_json() を引数なしで呼ばれても動く
      - LOG_DIR だけ patch されても追随（effective paths）
    """
    _trust_log_runtime.effective_log_paths = _effective_log_paths
    return _trust_log_runtime.load_logs_json(path)


# ★ スレッドセーフな Trust Log ランタイム
try:
    from veritas_os.logging.trust_log import trust_log_lock as _trust_log_lock
except ImportError:  # pragma: no cover - defensive fallback for isolated server tests
    _trust_log_lock = None


_trust_log_runtime = TrustLogRuntime(
    max_log_file_size=MAX_LOG_FILE_SIZE,
    effective_log_paths=_effective_log_paths,
    effective_shadow_dir=_effective_shadow_dir,
    has_atomic_io=_HAS_ATOMIC_IO,
    atomic_write_json=atomic_write_json,
    atomic_append_line=atomic_append_line,
    logger=logger,
    errstr=_errstr,
    trust_log_lock=_trust_log_lock,
    publish_event=_publish_event,
)


def _secure_chmod(path: Path) -> None:
    """Set restrictive 0o600 permissions on a sensitive file."""
    _trust_log_runtime.effective_log_paths = _effective_log_paths
    _trust_log_runtime.effective_shadow_dir = _effective_shadow_dir
    _trust_log_runtime.secure_chmod(path)


def _save_json(path: Path, items: list) -> None:
    _trust_log_runtime.effective_log_paths = _effective_log_paths
    _trust_log_runtime.save_json(path, items)


def append_trust_log(entry: Dict[str, Any]) -> None:
    """server 単体でも最低限 trust log が書けるフォールバック。"""
    _trust_log_runtime.effective_log_paths = _effective_log_paths
    _trust_log_runtime.append_trust_log(entry)


def write_shadow_decide(
    request_id: str,
    body: Dict[str, Any],
    chosen: Dict[str, Any],
    telos_score: float,
    fuji: Optional[Dict[str, Any]],
) -> None:
    _trust_log_runtime.effective_shadow_dir = _effective_shadow_dir
    _trust_log_runtime.write_shadow_decide(
        request_id,
        body,
        chosen,
        telos_score,
        fuji,
    )


# ==============================
# Route modules (APIRouter)
# ==============================
# All endpoint handlers have been extracted into focused route modules.
# Each router is included below with shared auth/rate-limit dependencies.
# server.py remains the single FastAPI app entry point and re-exports
# all attributes that tests monkeypatch.

from veritas_os.api.routes_decide import router as _decide_router  # noqa: E402
from veritas_os.api.routes_decide import (  # noqa: E402,F401 -- backward compat
    _call_fuji,
    decide,
    replay_endpoint,
    replay_decision_endpoint,
    fuji_validate,
)
from veritas_os.api.routes_memory import router as _memory_router  # noqa: E402
from veritas_os.api.routes_memory import (  # noqa: E402,F401 -- backward compat
    _store_put,
    _store_get,
    _store_search,
    _validate_memory_kinds,
    memory_put,
    memory_search,
    memory_get,
    memory_erase,
)
from veritas_os.api.routes_trust import router as _trust_router  # noqa: E402
from veritas_os.api.routes_trust import (  # noqa: E402,F401 -- backward compat
    _parse_risk_from_trust_entry,
    _prov_actor_for_entry,
    trust_logs,
    trust_log_by_request,
    trust_feedback,
    trustlog_verify,
    trustlog_export,
    trust_prov_export,
    trust_log_stats,
)
from veritas_os.api.routes_governance import router as _governance_router  # noqa: E402
from veritas_os.api.routes_governance import (  # noqa: E402,F401 -- backward compat
    require_governance_access,
    _governance_rbac_enabled,
    _resolve_governance_allowed_roles,
    _emit_governance_change_alert,
    governance_get,
    governance_put,
    governance_value_drift,
    governance_policy_history,
)
from veritas_os.api.routes_system import router as _system_router  # noqa: E402
from veritas_os.api.routes_system import public_router as _system_public_router  # noqa: E402
from veritas_os.api.routes_system import events_router as _events_router  # noqa: E402
from veritas_os.api.routes_system import (  # noqa: E402,F401 -- backward compat
    ComplianceConfigBody,
    SystemHaltRequest,
    SystemResumeRequest,
    _collect_recent_decide_files,
    root,
    health,
    status,
    metrics,
    events,
    trustlog_ws,
    compliance_get_config,
    compliance_put_config,
    report_eu_ai_act,
    report_governance,
    system_halt,
    system_resume,
    system_halt_status,
    compliance_deployment_readiness,
)

# Include routers with appropriate auth dependencies.
# Auth functions are defined above this point, so no circular import occurs.
_auth_deps = [Depends(require_api_key), Depends(enforce_rate_limit)]
_gov_deps = [Depends(require_api_key), Depends(require_governance_access)]

app.include_router(_system_public_router)  # health, status, root — no auth
app.include_router(_decide_router, dependencies=_auth_deps)
app.include_router(_memory_router, dependencies=_auth_deps)
app.include_router(_trust_router, dependencies=_auth_deps)
app.include_router(_governance_router, dependencies=_gov_deps)
app.include_router(_system_router, dependencies=[Depends(require_api_key)])
app.include_router(_events_router, dependencies=[Depends(require_api_key_header_or_query)])


# ==============================
# Module-level __getattr__ for dynamic attribute proxying
# ==============================
# Some mutable state lives in extracted modules (rate_limiting, middleware)
# but tests read/write them via ``server.<attr>``. We proxy these
# dynamically so test monkeypatching continues to work.

_PROXIED_RATE_ATTRS = {
    "_nonce_cleanup_timer", "_nonce_cleanup_timer_lock",
    "_rate_cleanup_timer", "_rate_cleanup_timer_lock",
    "_schedule_nonce_cleanup", "_schedule_rate_bucket_cleanup",
}

def __getattr__(name: str):
    if name in _PROXIED_RATE_ATTRS:
        return getattr(_rate_mod, name)
    raise AttributeError(f"module 'veritas_os.api.server' has no attribute {name!r}")
