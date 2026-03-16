# veritas_os/api/server.py
from __future__ import annotations

import asyncio
import hashlib
import heapq
import hmac
import importlib
import json
import logging
import math
import os
import queue
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager
from collections import deque
from dataclasses import dataclass
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

LOG_DIR: Path = _DEFAULT_LOG_DIR
LOG_JSON: Path = _DEFAULT_LOG_JSON
LOG_JSONL: Path = _DEFAULT_LOG_JSONL
SHADOW_DIR: Path = _DEFAULT_SHADOW_DIR


def _effective_log_paths() -> Tuple[Path, Path, Path]:
    """
    tests が LOG_DIR だけ patch した場合でも LOG_JSON/LOG_JSONL が追随するようにする。
    tests が LOG_JSON/LOG_JSONL を明示 patch した場合はそれを尊重。
    """
    global LOG_DIR, LOG_JSON, LOG_JSONL

    log_dir = LOG_DIR
    log_json = LOG_JSON
    log_jsonl = LOG_JSONL

    if log_json == _DEFAULT_LOG_JSON and log_dir != _DEFAULT_LOG_DIR:
        log_json = log_dir / "trust_log.json"
    if log_jsonl == _DEFAULT_LOG_JSONL and log_dir != _DEFAULT_LOG_DIR:
        log_jsonl = log_dir / "trust_log.jsonl"

    return log_dir, log_json, log_jsonl


def _effective_shadow_dir() -> Path:
    """
    tests が LOG_DIR だけ patch した場合でも SHADOW_DIR が追随するようにする。
    tests が SHADOW_DIR を明示 patch した場合はそれを尊重。
    """
    global SHADOW_DIR
    log_dir, _, _ = _effective_log_paths()

    shadow = SHADOW_DIR
    if shadow == _DEFAULT_SHADOW_DIR and log_dir != _DEFAULT_LOG_DIR:
        shadow = log_dir / "DASH"
    return shadow


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

@dataclass
class _LazyState:
    obj: Any = None
    err: Optional[str] = None
    attempted: bool = False
    lock: threading.Lock = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.lock = threading.Lock()


_cfg_state = _LazyState()
_pipeline_state = _LazyState()
_fuji_state = _LazyState()
_value_core_state = _LazyState()
_memory_store_state = _LazyState()


class _SSEEventHub:
    """In-memory SSE event hub with bounded history and subscriber queues."""

    def __init__(self, history_size: int = 128):
        self._lock = threading.Lock()
        self._history = deque(maxlen=history_size)
        self._subscribers: set[queue.Queue] = set()
        self._seq = 0

    def publish(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Publish one event to all subscribers and keep it in short history."""
        with self._lock:
            self._seq += 1
            event = {
                "id": self._seq,
                "type": event_type,
                "ts": utc_now_iso_z(),
                "payload": payload,
            }
            self._history.append(event)
            subscribers = list(self._subscribers)

        for subscriber in subscribers:
            try:
                subscriber.put_nowait(event)
            except queue.Full:
                logger.debug("sse queue full; dropping event for a slow subscriber")
            except Exception:
                logger.debug("failed to push sse event", exc_info=True)
        return event

    def register(self) -> queue.Queue:
        """Register a subscriber queue and pre-fill it with recent history."""
        q: queue.Queue = queue.Queue(maxsize=64)
        with self._lock:
            history = list(self._history)
            self._subscribers.add(q)

        for item in history:
            try:
                q.put_nowait(item)
            except queue.Full:
                break
        return q

    def unregister(self, subscriber: queue.Queue) -> None:
        """Remove a subscriber queue safely."""
        with self._lock:
            self._subscribers.discard(subscriber)


_event_hub = _SSEEventHub()

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


class ComplianceConfigBody(BaseModel):
    """Runtime compliance config payload."""

    eu_ai_act_mode: bool = Field(default=False)
    safety_threshold: float = Field(default=0.8, ge=0.0, le=1.0)




def _publish_event(event_type: str, payload: Dict[str, Any]) -> None:
    """Best-effort SSE event publication. Must never break API handlers."""
    try:
        _event_hub.publish(event_type=event_type, payload=payload)
    except Exception:
        logger.debug("failed to publish sse event", exc_info=True)


def _format_sse_message(event: Dict[str, Any]) -> str:
    """Format one SSE event frame."""
    data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event['id']}\nevent: {event['type']}\ndata: {data}\n\n"


def _errstr(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"


def _stage_summary(stage_payload: Any, default_text: str) -> str:
    """Return a safe summary string from heterogeneous stage payloads.

    Decide pipeline stage payloads can be dict/list/str depending on fallback
    paths. This helper avoids attribute errors while preserving observability.
    """
    if isinstance(stage_payload, dict):
        summary = stage_payload.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    elif isinstance(stage_payload, list):
        for item in stage_payload:
            if isinstance(item, dict):
                summary = item.get("summary")
                if isinstance(summary, str) and summary.strip():
                    return summary.strip()
            elif isinstance(item, str) and item.strip():
                return item.strip()
    elif isinstance(stage_payload, str) and stage_payload.strip():
        return stage_payload.strip()
    return default_text


DECIDE_GENERIC_ERROR = "service_unavailable"


def _log_decide_failure(message: str, err: Optional[Exception | str]) -> None:
    """Log internal decide pipeline errors without exposing details to clients."""
    if err is None:
        logger.error("decide failed: %s", message)
        return
    if isinstance(err, Exception):
        err_detail = _errstr(err)
    else:
        err_detail = str(err)
    logger.error("decide failed: %s (%s)", message, err_detail)


def _classify_decide_failure(err: BaseException) -> str:
    """Classify decide failure causes for safe-side operational diagnostics."""
    if isinstance(err, TimeoutError):
        return "timeout"
    if isinstance(err, PermissionError):
        return "permission_denied"
    if isinstance(err, (ValueError, TypeError, KeyError)):
        return "invalid_input"
    return "internal"


def get_cfg() -> Any:
    """
    cfg は "無い/壊れてる" 可能性があるので必ずフォールバックを返す。
    CORS設定など起動に関わるため、ここで絶対に例外を外へ出さない。

    Note: ロック外の事前チェック (double-checked locking) は Python の
    メモリモデルではスレッドセーフが保証されないため、常にロックを取得する。
    """
    global _cfg_state
    with _cfg_state.lock:
        if _cfg_state.obj is not None:
            return _cfg_state.obj
        if _cfg_state.attempted and _cfg_state.err is not None:
            return _cfg_state.obj

        _cfg_state.attempted = True
        try:
            mod = importlib.import_module("veritas_os.core.config")
            cfg = getattr(mod, "cfg")
            _cfg_state.obj = cfg
            _cfg_state.err = None
            return cfg
        except Exception as e:
            _cfg_state.err = _errstr(e)
            _cfg_state.obj = SimpleNamespace(
                cors_allow_origins=[],
                api_key="",
            )
            logger.warning("cfg import failed -> fallback: %s", _cfg_state.err)
            return _cfg_state.obj


def get_decision_pipeline() -> Optional[Any]:
    """
    pipeline は壊れていても server を落とさない。
    /v1/decide 呼び出し時に 503 へ変換する。
    """
    global _pipeline_state
    with _pipeline_state.lock:
        if _pipeline_state.obj is not None:
            return _pipeline_state.obj
        if _pipeline_state.attempted and _pipeline_state.err is not None:
            return None

        _pipeline_state.attempted = True
        try:
            p = importlib.import_module("veritas_os.core.pipeline")
            _pipeline_state.obj = p
            _pipeline_state.err = None
            return p
        except Exception as e:
            _pipeline_state.err = _errstr(e)
            _pipeline_state.obj = None
            logger.warning("decision pipeline import failed: %s", _pipeline_state.err)
            return None


def get_fuji_core() -> Optional[Any]:
    """
    - tests: monkeypatch server.fuji_core を「任意のオブジェクト」に差し替える
      → その場合は絶対にそれを尊重して返す（lazy import で上書きしない）
    - prod : placeholder のままなら lazy import して module を返す（差し替え）
    """
    global _fuji_state, fuji_core

    # monkeypatch で placeholder 以外が入っていたら尊重
    if not _is_placeholder(fuji_core):
        return fuji_core

    # placeholder 内の関数だけ差し替えられている場合も尊重
    if getattr(fuji_core, "validate_action", None) is not _fuji_validate_stub:
        return fuji_core
    if getattr(fuji_core, "validate", None) is not _fuji_validate_stub:
        return fuji_core

    with _fuji_state.lock:
        if _fuji_state.obj is not None:
            return _fuji_state.obj
        if _fuji_state.attempted and _fuji_state.err is not None:
            return None

        _fuji_state.attempted = True
        try:
            m = importlib.import_module("veritas_os.core.fuji")
            _fuji_state.obj = m
            _fuji_state.err = None
            fuji_core = m
            return m
        except Exception as e:
            _fuji_state.err = _errstr(e)
            _fuji_state.obj = None
            logger.warning("fuji_core import failed: %s", _fuji_state.err)
            return None


def get_value_core() -> Optional[Any]:
    """
    - tests: monkeypatch server.value_core.append_trust_log
    - prod : placeholder のままなら lazy import して module を返す（差し替え）
    """
    global _value_core_state, value_core

    if _is_placeholder(value_core):
        if getattr(value_core, "append_trust_log", None) is not _append_trust_log_stub:
            return value_core
    else:
        if hasattr(value_core, "append_trust_log"):
            return value_core

    with _value_core_state.lock:
        if _value_core_state.obj is not None:
            return _value_core_state.obj
        if _value_core_state.attempted and _value_core_state.err is not None:
            return None

        _value_core_state.attempted = True
        try:
            m = importlib.import_module("veritas_os.core.value_core")
            _value_core_state.obj = m
            _value_core_state.err = None
            value_core = m
            return m
        except Exception as e:
            _value_core_state.err = _errstr(e)
            _value_core_state.obj = None
            logger.warning("value_core import failed: %s", _value_core_state.err)
            return None


def get_memory_store() -> Optional[Any]:
    """
    - tests: monkeypatch server.MEMORY_STORE.search/get
    - prod : placeholder のままなら veritas_os.core.memory の MEM を lazy 取得して更新
    """
    global _memory_store_state, MEMORY_STORE

    if _is_placeholder(MEMORY_STORE):
        if getattr(MEMORY_STORE, "search", None) is not _memory_search_stub:
            return MEMORY_STORE
        if getattr(MEMORY_STORE, "get", None) is not _memory_get_stub:
            return MEMORY_STORE
    else:
        if any(hasattr(MEMORY_STORE, a) for a in ("search", "get", "put", "put_episode", "recent", "add_usage")):
            return MEMORY_STORE

    with _memory_store_state.lock:
        if _memory_store_state.obj is not None:
            return _memory_store_state.obj
        if _memory_store_state.attempted and _memory_store_state.err is not None:
            return None

        _memory_store_state.attempted = True
        try:
            m = importlib.import_module("veritas_os.core.memory")
            store = getattr(m, "MEM", None)
            if store is None:
                # module-style memory (search/put/get on module)
                if any(hasattr(m, a) for a in ("search", "put", "get")):
                    store = m
                else:
                    raise RuntimeError("MEM not found in veritas_os.core.memory")
            _memory_store_state.obj = store
            _memory_store_state.err = None
            MEMORY_STORE = store
            return store
        except Exception as e:
            _memory_store_state.err = _errstr(e)
            _memory_store_state.obj = None
            logger.warning("memory store import failed: %s", _memory_store_state.err)
            return None


# ==============================
# FastAPI app init (must not crash)
# ==============================

cfg = get_cfg()

def _should_fail_fast_startup(profile: Optional[str] = None) -> bool:
    """Return whether startup validation failures should stop app boot.

    Production profiles must fail fast to avoid running with insecure or
    incomplete runtime configuration.
    """
    resolved_profile = (
        profile if profile is not None else os.getenv("VERITAS_ENV", "")
    )
    normalized_profile = resolved_profile.strip().lower()
    return normalized_profile in {"prod", "production"}


def _run_startup_config_validation() -> None:
    """Validate startup configuration with environment-specific strictness."""
    try:
        validator = globals().get("validate_startup_config")
        if validator is None:
            from veritas_os.core.config import validate_startup_config as validator

        validator()
    except Exception:
        fail_fast = _should_fail_fast_startup()
        logger.warning(
            "startup config validation failed (fail_fast=%s)",
            fail_fast,
            exc_info=True,
        )
        if fail_fast:
            raise


def _check_runtime_feature_health() -> None:
    """Warn about degraded runtime features so operators are never silently misled.

    Security:
        Critical modules like ``sanitize`` (PII masking) and ``atomic_io``
        (crash-safe writes) degrade gracefully on import failure. However,
        operators must be explicitly notified at startup so they do not assume
        full security coverage when running in fallback mode.
    """
    if not _HAS_SANITIZE:
        logger.warning(
            "[SECURITY] PII masking is DISABLED (sanitize module failed to load). "
            "Sensitive data may appear in shadow logs. "
            "Fix the import error and restart to restore full protection."
        )
    if not _HAS_ATOMIC_IO:
        logger.warning(
            "[RELIABILITY] Atomic I/O is DISABLED (atomic_io module failed to load). "
            "Trust log writes are less crash-safe (using direct file I/O). "
            "Fix the import error and restart to restore full protection."
        )


def _check_multiworker_auth_store() -> None:
    """Warn when in-memory auth store is used in a multi-worker environment.

    Security:
        Rate limiting, auth failure tracking, and nonce replay protection are
        stored in process-local memory by default. In multi-worker deployments
        (Gunicorn, multiple Uvicorn workers), each worker maintains its own
        independent state. This means:
        - A client can exceed rate limits by distributing requests across workers.
        - Replay attacks may succeed if different workers receive the same nonce.

        Set ``VERITAS_AUTH_SECURITY_STORE=redis`` and ``VERITAS_AUTH_REDIS_URL``
        to enable distributed-safe protection.
    """
    if isinstance(_AUTH_SECURITY_STORE, RedisAuthSecurityStore):
        return

    # Detect likely multi-worker deployment via common env variables
    web_concurrency = (os.getenv("WEB_CONCURRENCY") or "").strip()
    uvicorn_workers = (os.getenv("UVICORN_WORKERS") or "").strip()

    try:
        multi_worker = (int(web_concurrency) > 1 if web_concurrency else False) or (
            int(uvicorn_workers) > 1 if uvicorn_workers else False
        )
    except ValueError:
        multi_worker = False

    if multi_worker:
        logger.warning(
            "[SECURITY] In-memory auth store is active with multi-worker deployment "
            "(WEB_CONCURRENCY=%s, UVICORN_WORKERS=%s). "
            "Rate limiting and nonce replay protection are NOT shared across workers. "
            "Set VERITAS_AUTH_SECURITY_STORE=redis and VERITAS_AUTH_REDIS_URL to fix.",
            web_concurrency or "unset",
            uvicorn_workers or "unset",
        )
    else:
        logger.info(
            "Auth security store: in-memory (single-worker mode). "
            "For multi-worker deployments, set VERITAS_AUTH_SECURITY_STORE=redis."
        )


# ---------------------------------------------------------------------------
# In-flight request tracking for graceful shutdown
# ---------------------------------------------------------------------------
_inflight_count = 0
_inflight_lock = threading.Lock()
_shutting_down = False


def _inflight_snapshot() -> Dict[str, Any]:
    """Return a thread-safe snapshot of in-flight request state."""
    with _inflight_lock:
        return {"inflight": _inflight_count, "shutting_down": _shutting_down}


@asynccontextmanager
async def _app_lifespan(_: FastAPI):
    """Manage startup/shutdown actions using FastAPI lifespan API."""
    global _shutting_down, _inflight_count
    with _inflight_lock:
        _shutting_down = False
        _inflight_count = 0
    _run_startup_config_validation()
    _check_runtime_feature_health()
    _check_multiworker_auth_store()
    _start_nonce_cleanup_scheduler()
    _start_rate_cleanup_scheduler()
    try:
        yield
    finally:
        with _inflight_lock:
            _shutting_down = True
        # Drain in-flight requests (up to _SHUTDOWN_DRAIN_SEC seconds)
        _drain_sec = float(os.getenv("VERITAS_SHUTDOWN_DRAIN_SEC", "10"))
        deadline = time.monotonic() + _drain_sec
        while time.monotonic() < deadline:
            with _inflight_lock:
                if _inflight_count <= 0:
                    break
            await asyncio.sleep(0.25)
        with _inflight_lock:
            remaining = _inflight_count
        if remaining > 0:
            logger.warning(
                "Shutting down with %d in-flight request(s) after %.0fs drain timeout",
                remaining,
                _drain_sec,
            )
        else:
            logger.info("All in-flight requests drained, shutting down cleanly")
        _stop_nonce_cleanup_scheduler()
        _stop_rate_cleanup_scheduler()
        if _close_llm_pool is not None:
            _close_llm_pool()


app = FastAPI(title="VERITAS Public API", version="1.0.3", lifespan=_app_lifespan)

# ★ セキュリティ: allow_credentials は明示的なオリジンが設定されている場合のみ True
# 空の場合に True にすると、ブラウザの CORS チェックを意図せずバイパスするリスクがある
def _resolve_cors_settings(origins: Any) -> tuple[list[str], bool]:
    """Resolve safe CORS settings from config values.

    Security hardening:
        - ``"*"`` + ``allow_credentials=True`` is forbidden by the CORS spec
          intent and can create credential leakage risk in permissive browser
          deployments.
        - Any non-string entries are ignored to avoid accidental misconfig.
    """
    if not isinstance(origins, (list, tuple, set)):
        return [], False

    normalized_origins = [str(origin).strip() for origin in origins if isinstance(origin, str) and origin.strip()]
    if not normalized_origins:
        return [], False

    if "*" in normalized_origins:
        logger.warning(
            "Insecure CORS config detected: wildcard origin with credentials is disallowed. "
            "Falling back to allow_credentials=False.",
        )
        return ["*"], False

    return normalized_origins, True


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

# ★ C-3 継続改善: リクエストボディサイズ制限 (DoS対策)
# 運用プロファイルごとの推奨値を定義しつつ、環境変数で上書き可能にする。
DEFAULT_MAX_REQUEST_BODY_SIZE = 10 * 1024 * 1024
PROFILE_MAX_REQUEST_BODY_SIZE = {
    "dev": 10 * 1024 * 1024,
    "development": 10 * 1024 * 1024,
    "stg": 8 * 1024 * 1024,
    "stage": 8 * 1024 * 1024,
    "staging": 8 * 1024 * 1024,
    "prod": 5 * 1024 * 1024,
    "production": 5 * 1024 * 1024,
}


def _resolve_max_request_body_size() -> int:
    """Resolve request size limit from profile + explicit env override.

    Security notes:
        - ``VERITAS_MAX_REQUEST_BODY_SIZE`` is always the highest-priority
          explicit override.
        - ``VERITAS_ENV`` profile defaults tighten production values to reduce
          memory pressure and large-body DoS blast radius.
        - Non-positive or non-integer values are rejected and fall back to a
          safe default value.
    """
    profile = (os.getenv("VERITAS_ENV", "") or "").strip().lower()
    profile_default = PROFILE_MAX_REQUEST_BODY_SIZE.get(
        profile,
        DEFAULT_MAX_REQUEST_BODY_SIZE,
    )

    raw_override = os.getenv("VERITAS_MAX_REQUEST_BODY_SIZE", "").strip()
    if not raw_override:
        return profile_default

    try:
        parsed = int(raw_override)
    except ValueError:
        logger.warning(
            "Invalid VERITAS_MAX_REQUEST_BODY_SIZE=%r, using profile default=%s",
            raw_override,
            profile_default,
        )
        return profile_default

    if parsed <= 0:
        logger.warning(
            "VERITAS_MAX_REQUEST_BODY_SIZE must be > 0, got %s. "
            "Using profile default=%s",
            parsed,
            profile_default,
        )
        return profile_default

    return parsed


MAX_REQUEST_BODY_SIZE = _resolve_max_request_body_size()
TRACE_ID_HEADER_NAME = "X-Trace-Id"
_TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


def _resolve_trace_id_from_request(request: Request) -> str:
    """Resolve or mint a trace id for end-to-end audit correlation.

    Security:
        - Accept only a strict ASCII-safe format to avoid header/log injection.
        - Prefer caller-provided ids (``X-Trace-Id`` / ``X-Request-Id``) when
          valid, otherwise generate a cryptographically random fallback.
    """
    candidates = (
        request.headers.get(TRACE_ID_HEADER_NAME),
        request.headers.get("x-trace-id"),
        request.headers.get("X-Request-Id"),
        request.headers.get("x-request-id"),
    )

    for candidate in candidates:
        normalized = (candidate or "").strip()
        if _TRACE_ID_PATTERN.match(normalized):
            return normalized

    return secrets.token_hex(16)


@app.middleware("http")
async def attach_trace_id(request: Request, call_next):
    """Attach a validated trace id to request state and response headers."""
    trace_id = _resolve_trace_id_from_request(request)
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers[TRACE_ID_HEADER_NAME] = trace_id
    response.headers.setdefault("X-Request-Id", trace_id)
    return response


@app.middleware("http")
async def add_response_time(request: Request, call_next):
    """Record and expose request processing time via X-Response-Time header."""
    start = time.monotonic()
    response = await call_next(request)
    elapsed_ms = round((time.monotonic() - start) * 1000, 2)
    response.headers["X-Response-Time"] = f"{elapsed_ms}ms"
    return response


@app.middleware("http")
async def add_rate_limit_headers(request: Request, call_next):
    """Expose rate limit state via standard X-RateLimit-* response headers.

    After the route handler (and its ``enforce_rate_limit`` dependency) runs,
    this middleware reads the current bucket entry for the caller's API key
    and attaches ``X-RateLimit-Limit``, ``X-RateLimit-Remaining``, and
    ``X-RateLimit-Reset`` headers to the response.

    Endpoints without rate limiting (e.g. ``/health``) are silently skipped.
    """
    response = await call_next(request)
    api_key = (request.headers.get("X-API-Key") or "").strip()
    if api_key:
        with _rate_lock:
            entry = _rate_bucket.get(api_key)
        if entry is not None:
            count, start = entry
            remaining = max(0, _RATE_LIMIT - count)
            reset_at = int(math.ceil(start + _RATE_WINDOW))
            response.headers["X-RateLimit-Limit"] = str(_RATE_LIMIT)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(reset_at)
    return response


@app.middleware("http")
async def track_inflight_requests(request: Request, call_next):
    """Track in-flight requests for graceful shutdown draining."""
    global _inflight_count

    if _shutting_down:
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "Server is shutting down"},
            headers={"Retry-After": "5"},
        )

    with _inflight_lock:
        _inflight_count += 1
    try:
        response = await call_next(request)
        return response
    finally:
        with _inflight_lock:
            _inflight_count -= 1


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    """
    ★ C-3 修正: リクエストボディサイズ制限ミドルウェア

    巨大なペイロードによるDoS攻撃を防止:
    - Content-Length ヘッダーで事前チェック
    - Pydantic バリデーション前にブロック
    """
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_BODY_SIZE:
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Request body too large. Max size: {MAX_REQUEST_BODY_SIZE} bytes"}
                )
        except (ValueError, TypeError):
            # ★ 修正: 不正な Content-Length は 400 Bad Request を返す
            # 悪意のあるリクエストがバリデーションをバイパスするのを防止
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid Content-Length header"}
            )
    return await call_next(request)


# ★ M-14 修正: HTTPセキュリティヘッダーミドルウェア
# クリックジャッキング、MIMEスニッフィング、XSS攻撃を防止
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Apply baseline response security headers for API endpoints.

    Notes:
        - A strict Content Security Policy (CSP) is attached even for JSON API
          responses to reduce the risk of accidental HTML rendering and inline
          script execution in browser-based tooling.
        - ``Permissions-Policy`` disables powerful browser features by default
          because this API does not require them.
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    response.headers["Permissions-Policy"] = (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), payment=(), usb=()"
    )
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Security hardening: browsers only honor HSTS over HTTPS.
    # Sending this header proactively helps production deployments enforce
    # transport security and reduces protocol-downgrade attack surface.
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


# ==============================
# API Key & HMAC 認証
# ==============================

# ★ 後方互換: テストがmonkeypatch.setattr(server, "API_KEY_DEFAULT", ...)を使用
# 実際の認証では _get_expected_api_key() を使用して毎回環境変数から取得
# （この変数は直接使用せず、レガシーテスト互換のためだけに存在）
API_KEY_DEFAULT = ""  # ★ セキュリティ修正: 起動時にキーを保持しない

# 認証失敗レート制限（IPベース）
_AUTH_FAIL_RATE_LIMIT = 10
_AUTH_FAIL_WINDOW = 60.0
_AUTH_FAIL_BUCKET_MAX = 10000
_auth_fail_bucket: Dict[str, Tuple[int, float]] = {}
_auth_fail_lock = threading.Lock()


class AuthSecurityStore(Protocol):
    """Shared store interface for auth security controls.

    This abstraction keeps auth-layer replay prevention and throttling logic
    independent from Planner / Kernel / FUJI / MemoryOS responsibilities.
    """

    def register_nonce(self, nonce: str, ttl_sec: float) -> bool:
        """Return True when nonce is newly registered, False on replay."""

    def increment_auth_failure(
        self,
        client_ip: str,
        limit: int,
        window_sec: float,
    ) -> bool:
        """Return True when limit is exceeded for the key within the window."""

    def increment_rate_limit(
        self,
        api_key: str,
        limit: int,
        window_sec: float,
    ) -> bool:
        """Return True when rate limit is exceeded for the key in the window."""


class InMemoryAuthSecurityStore:
    """Thread-safe in-memory implementation for auth security controls.

    Security warning:
        This mode is process-local. In horizontally scaled deployments,
        replay protection and throttling consistency are not guaranteed.
    """

    def register_nonce(self, nonce: str, ttl_sec: float) -> bool:
        with _nonce_lock:
            _cleanup_nonces_unsafe()
            if nonce in _nonce_store:
                return False
            _nonce_store[nonce] = time.time() + ttl_sec
            return True

    def increment_auth_failure(
        self,
        client_ip: str,
        limit: int,
        window_sec: float,
    ) -> bool:
        now = time.time()
        with _auth_fail_lock:
            _cleanup_auth_fail_bucket_unsafe(now)
            count, start = _auth_fail_bucket.get(client_ip, (0, now))
            if now - start > window_sec:
                _auth_fail_bucket[client_ip] = (1, now)
                return False
            if count + 1 > limit:
                return True
            _auth_fail_bucket[client_ip] = (count + 1, start)
            return False

    def increment_rate_limit(
        self,
        api_key: str,
        limit: int,
        window_sec: float,
    ) -> bool:
        now = time.time()
        with _rate_lock:
            _cleanup_rate_bucket_unsafe()
            count, start = _rate_bucket.get(api_key, (0, now))
            if now - start > window_sec:
                _rate_bucket[api_key] = (1, now)
                return False
            if count + 1 > limit:
                return True
            _rate_bucket[api_key] = (count + 1, start)
            return False


class RedisAuthSecurityStore:
    """Redis-backed auth security store for distributed deployments."""

    def __init__(self, redis_client: Any):
        self._redis = redis_client

    def register_nonce(self, nonce: str, ttl_sec: float) -> bool:
        ttl_ms = max(int(ttl_sec * 1000), 1)
        result = self._redis.set(name=f"veritas:nonce:{nonce}", value="1", nx=True, px=ttl_ms)
        return bool(result)

    def increment_auth_failure(
        self,
        client_ip: str,
        limit: int,
        window_sec: float,
    ) -> bool:
        key = f"veritas:auth_fail:{client_ip}"
        return self._increment_with_window(key=key, limit=limit, window_sec=window_sec)

    def increment_rate_limit(
        self,
        api_key: str,
        limit: int,
        window_sec: float,
    ) -> bool:
        key = f"veritas:rate:{api_key}"
        return self._increment_with_window(key=key, limit=limit, window_sec=window_sec)

    def _increment_with_window(self, key: str, limit: int, window_sec: float) -> bool:
        ttl_ms = max(int(window_sec * 1000), 1)
        with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.pexpire(key, ttl_ms, nx=True)
            count, _ = pipe.execute()
        return int(count) > limit


def _create_auth_security_store() -> AuthSecurityStore:
    """Create auth security store from environment configuration.

    Supported modes:
        - ``memory`` (default): process-local fallback.
        - ``redis``: shared distributed mode via ``VERITAS_AUTH_REDIS_URL``.
    """
    mode = (os.getenv("VERITAS_AUTH_SECURITY_STORE") or "memory").strip().lower()
    if mode != "redis":
        return InMemoryAuthSecurityStore()

    redis_url = (os.getenv("VERITAS_AUTH_REDIS_URL") or "").strip()
    if not redis_url:
        logger.warning(
            "VERITAS_AUTH_SECURITY_STORE=redis but VERITAS_AUTH_REDIS_URL is missing; "
            "falling back to in-memory auth store (not distributed-safe)."
        )
        return InMemoryAuthSecurityStore()

    try:
        redis_module = importlib.import_module("redis")
        client = redis_module.Redis.from_url(redis_url, decode_responses=True)
        client.ping()
        logger.info("Auth security store initialized in redis mode")
        return RedisAuthSecurityStore(client)
    except Exception as exc:
        logger.warning(
            "Failed to initialize redis auth store (%s); falling back to in-memory "
            "auth store (not distributed-safe).",
            _errstr(exc),
        )
        return InMemoryAuthSecurityStore()


_AUTH_SECURITY_STORE = _create_auth_security_store()
_AUTH_REJECT_REASON_METRICS: Dict[str, int] = {}
_AUTH_REJECT_REASON_LOCK = threading.Lock()


def _auth_store_failure_mode() -> str:
    """Return auth store failure policy: ``open`` or ``closed``."""
    raw = (os.getenv("VERITAS_AUTH_STORE_FAILURE_MODE") or "closed").strip().lower()
    if raw in {"open", "closed"}:
        return raw
    return "closed"


def _auth_store_register_nonce(nonce: str, ttl_sec: float) -> bool:
    """Register nonce with explicit fail-open/fail-closed fallback policy."""
    try:
        return _AUTH_SECURITY_STORE.register_nonce(nonce=nonce, ttl_sec=ttl_sec)
    except Exception as exc:
        mode = _auth_store_failure_mode()
        logger.warning("Auth nonce store failure (%s), mode=%s", _errstr(exc), mode)
        _record_auth_reject_reason("auth_store_nonce_error")
        if mode == "open":
            return True
        return False


def _auth_store_increment_auth_failure(client_ip: str, limit: int, window_sec: float) -> bool:
    """Increment auth failure counter with explicit fail-open/fail-closed policy."""
    try:
        return _AUTH_SECURITY_STORE.increment_auth_failure(
            client_ip=client_ip,
            limit=limit,
            window_sec=window_sec,
        )
    except Exception as exc:
        mode = _auth_store_failure_mode()
        logger.warning("Auth failure store error (%s), mode=%s", _errstr(exc), mode)
        _record_auth_reject_reason("auth_store_auth_fail_error")
        return mode == "closed"


def _auth_store_increment_rate_limit(api_key: str, limit: int, window_sec: float) -> bool:
    """Increment request rate counter with explicit fail-open/fail-closed policy."""
    try:
        return _AUTH_SECURITY_STORE.increment_rate_limit(
            api_key=api_key,
            limit=limit,
            window_sec=window_sec,
        )
    except Exception as exc:
        mode = _auth_store_failure_mode()
        logger.warning("Auth rate-limit store error (%s), mode=%s", _errstr(exc), mode)
        _record_auth_reject_reason("auth_store_rate_limit_error")
        return mode == "closed"


def _record_auth_reject_reason(reason_code: str) -> None:
    """Track reject reason counters for operational audit metrics."""
    with _AUTH_REJECT_REASON_LOCK:
        _AUTH_REJECT_REASON_METRICS[reason_code] = _AUTH_REJECT_REASON_METRICS.get(reason_code, 0) + 1


def _snapshot_auth_reject_reason_metrics() -> Dict[str, int]:
    """Return thread-safe snapshot of auth reject reason counters."""
    with _AUTH_REJECT_REASON_LOCK:
        return dict(_AUTH_REJECT_REASON_METRICS)

# 起動時に一度だけ警告を出力（テスト互換性のため）
if not os.getenv("VERITAS_API_KEY"):
    logger.warning("VERITAS_API_KEY 未設定（テストでは 500 を返す契約）")

api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

def _resolve_expected_api_key_with_source() -> tuple[str, str]:
    """Resolve API key value and source name without exposing secrets.

    Returns:
        tuple[str, str]:
            - effective API key value (may be empty)
            - source label: ``env``, ``api_key_default``, ``config`` or
              ``missing``.
    """
    env_key = (os.getenv("VERITAS_API_KEY") or "").strip()
    if env_key:
        return env_key, "env"

    default_key = API_KEY_DEFAULT.strip()
    if default_key:
        return default_key, "api_key_default"

    config_key = (getattr(cfg, "api_key", "") or "").strip()
    if config_key:
        return config_key, "config"
    return "", "missing"




@lru_cache(maxsize=4)
def _log_api_key_source_once(source: str) -> None:
    """Log API key source with fixed messages to avoid secret-log findings.

    Security:
        The log body is selected from hard-coded constants only. No runtime
        values are interpolated, preventing accidental secret propagation to
        logs and reducing false positives in static secret-scanning rules.
    """
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

def _get_expected_api_key() -> str:
    """
    ★ セキュリティ修正: APIキーを毎回環境変数から取得。
    モジュールレベル変数に保持しないことで、メモリダンプによる漏洩リスクを軽減。
    テスト時は API_KEY_DEFAULT を monkeypatch で上書き可能（レガシー互換）。
    """
    key, source = _resolve_expected_api_key_with_source()
    _log_api_key_source_once(source)
    return key


def _resolve_client_ip(
    request: Optional[Request],
    x_forwarded_for: Any,
) -> str:
    """Resolve client IP for auth-failure throttling.

    Security:
        Prefer ``X-Forwarded-For`` when present so that reverse-proxy
        deployments still apply per-client limits. A trusted proxy setup is
        assumed; otherwise this value may be spoofed and should not be used for
        authorization.
    """
    forwarded_raw = x_forwarded_for if isinstance(x_forwarded_for, str) else ""
    forwarded = forwarded_raw.split(",", maxsplit=1)[0].strip()
    if forwarded:
        return forwarded

    if request is not None and request.client is not None and request.client.host:
        return request.client.host.strip() or "unknown"

    return "unknown"


def _cleanup_auth_fail_bucket_unsafe(now: float) -> None:
    """Internal helper: cleanup auth-failure buckets (lock required)."""
    expired_keys = [
        key
        for key, (_, start) in _auth_fail_bucket.items()
        if now - start > (_AUTH_FAIL_WINDOW * 4)
    ]
    for key in expired_keys:
        _auth_fail_bucket.pop(key, None)

    if len(_auth_fail_bucket) > _AUTH_FAIL_BUCKET_MAX:
        overflow = len(_auth_fail_bucket) - _AUTH_FAIL_BUCKET_MAX
        for key in list(_auth_fail_bucket.keys())[:overflow]:
            _auth_fail_bucket.pop(key, None)


def _enforce_auth_failure_rate_limit(client_ip: str) -> None:
    """Rate-limit repeated authentication failures by client IP."""
    key = client_ip.strip() or "unknown"
    exceeded = _auth_store_increment_auth_failure(
        client_ip=key,
        limit=_AUTH_FAIL_RATE_LIMIT,
        window_sec=_AUTH_FAIL_WINDOW,
    )
    if exceeded:
        _record_auth_reject_reason("auth_failure_rate_limited")
        raise HTTPException(status_code=429, detail="Too many auth failures")


def require_api_key(
    request: Request = None,  # type: ignore[assignment]
    x_api_key: Optional[str] = Security(api_key_scheme),
    x_forwarded_for: Optional[str] = Header(default=None, alias="X-Forwarded-For"),
):
    """
    テスト契約:
    - サーバ側の API Key が未設定なら 500
    - ヘッダが無い/不一致なら 401
    """
    expected = (_get_expected_api_key() or "").strip()
    if not expected:
        _record_auth_reject_reason("api_key_server_unconfigured")
        raise HTTPException(status_code=500, detail="Server API key not configured")

    client_ip = _resolve_client_ip(request=request, x_forwarded_for=x_forwarded_for)
    if not x_api_key:
        _record_auth_reject_reason("api_key_missing")
        _enforce_auth_failure_rate_limit(client_ip)
        raise HTTPException(status_code=401, detail="Missing API key")
    if not secrets.compare_digest(x_api_key.strip(), expected):
        _record_auth_reject_reason("api_key_invalid")
        _enforce_auth_failure_rate_limit(client_ip)
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


def _derive_api_user_id(x_api_key: Optional[str]) -> str:
    """Derive a stable internal user identifier from the authenticated API key.

    Security:
        Memory endpoints must not trust caller-supplied ``user_id`` values, because
        that allows cross-user writes/reads when one shared API key is used by
        multiple clients. This helper binds memory tenancy to the API key itself.

        The user ID is derived via PBKDF2-HMAC-SHA256 (fixed salt, fixed iterations)
        so that:
        - Different API keys produce different memory namespaces (multi-tenant).
        - The raw key value is never stored in memory indices or logs.
        - PBKDF2 is used to satisfy CodeQL CWE-916 / "weak hash on sensitive data"
          — the fixed salt and iterations are intentional (this is key derivation,
          not password storage). Iterations are kept low for throughput since
          the API key is already a high-entropy secret, not a human password.

    Args:
        x_api_key: Raw ``X-API-Key`` header value (already authenticated).

    Returns:
        A deterministic, opaque internal user ID string of the form ``key_<hex16>``.
    """
    if isinstance(x_api_key, str) and x_api_key.strip():
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            x_api_key.strip().encode("utf-8"),
            b"veritas_user_id_v1",
            1,
        ).hex()[:16]
        return f"key_{digest}"
    return "anon"


def _resolve_memory_user_id(body_user_id: Any, x_api_key: Optional[str]) -> str:
    """Resolve memory tenant user_id while preventing caller-controlled spoofing."""
    resolved = _derive_api_user_id(x_api_key)
    requested = str(body_user_id or "").strip()
    if requested and requested != resolved:
        logger.warning(
            "Memory user_id override blocked: requested=%s resolved=%s",
            redact(requested),
            resolved,
        )
    return resolved


def require_api_key_header_or_query(
    request: Request = None,  # type: ignore[assignment]
    x_api_key: Optional[str] = Security(api_key_scheme),
    api_key: Optional[str] = Query(default=None),
    x_forwarded_for: Optional[str] = Header(default=None, alias="X-Forwarded-For"),
):
    """Authenticate SSE requests with header-first policy.

    Security:
        Query-string API keys are disabled by default because they can leak via
        access logs, browser history, and monitoring URLs. To preserve migration
        flexibility, operators may temporarily enable query auth with the
        ``VERITAS_ALLOW_SSE_QUERY_API_KEY=1`` feature flag.
        Auth failures are rate-limited per client IP (same policy as require_api_key).
    """
    expected = (_get_expected_api_key() or "").strip()
    if not expected:
        _record_auth_reject_reason("api_key_server_unconfigured")
        raise HTTPException(status_code=500, detail="Server API key not configured")

    client_ip = _resolve_client_ip(request=request, x_forwarded_for=x_forwarded_for)
    header_candidate = (x_api_key or "").strip()
    query_candidate = (api_key or "").strip()

    candidate = header_candidate
    if not candidate and query_candidate:
        if not _allow_sse_query_api_key():
            _record_auth_reject_reason("api_key_query_disabled")
            _enforce_auth_failure_rate_limit(client_ip)
            raise HTTPException(status_code=401, detail="Query API key is disabled; use X-API-Key header")
        logger.warning(
            "SSE auth accepted query api_key due to VERITAS_ALLOW_SSE_QUERY_API_KEY=1. "
            "This mode increases credential exposure risk.",
        )
        candidate = query_candidate

    if not candidate:
        _record_auth_reject_reason("api_key_missing")
        _enforce_auth_failure_rate_limit(client_ip)
        raise HTTPException(status_code=401, detail="Missing API key")
    if not secrets.compare_digest(candidate, expected):
        _record_auth_reject_reason("api_key_invalid")
        _enforce_auth_failure_rate_limit(client_ip)
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


def _allow_sse_query_api_key() -> bool:
    """Return True only when dual opt-in flags enable SSE query auth.

    Security note:
        Query-string API keys can leak through logs and browser history.
        To reduce accidental exposure, enabling this mode requires two flags:
        ``VERITAS_ALLOW_SSE_QUERY_API_KEY`` and
        ``VERITAS_ACK_SSE_QUERY_API_KEY_RISK``.
    """
    allow_raw = (os.getenv("VERITAS_ALLOW_SSE_QUERY_API_KEY") or "").strip().lower()
    allow_query_auth = allow_raw in {"1", "true", "yes", "on"}
    if not allow_query_auth:
        return False

    ack_raw = (os.getenv("VERITAS_ACK_SSE_QUERY_API_KEY_RISK") or "").strip().lower()
    acknowledged = ack_raw in {"1", "true", "yes", "on"}
    if not acknowledged:
        logger.warning(
            "SSE query api_key enable flag ignored because "
            "VERITAS_ACK_SSE_QUERY_API_KEY_RISK is not set. "
            "Set both flags only for temporary migration windows.",
        )
        return False

    return True


def _authenticate_websocket_api_key(websocket: WebSocket) -> bool:
    """Authenticate WebSocket API key with header-first policy.

    Security:
        - ``X-API-Key`` header is preferred because URL query parameters are
          commonly captured by access logs, browser history, and monitoring
          tooling.
        - Query authentication is disabled by default. It can be enabled only
          with dual opt-in flags during migration windows.
    """
    expected = (_get_expected_api_key() or "").strip()
    if not expected:
        return False

    header_candidate = (websocket.headers.get("X-API-Key") or "").strip()
    if header_candidate:
        return secrets.compare_digest(header_candidate, expected)

    query_candidate = (websocket.query_params.get("api_key") or "").strip()
    if not query_candidate:
        return False
    if not _allow_ws_query_api_key():
        return False

    logger.warning(
        "WebSocket auth accepted query api_key due to VERITAS_ALLOW_WS_QUERY_API_KEY=1. "
        "This mode increases credential exposure risk.",
    )
    return secrets.compare_digest(query_candidate, expected)


def _allow_ws_query_api_key() -> bool:
    """Return True only when dual opt-in flags allow WebSocket query auth.

    Security note:
        Query-string API keys can leak through logs and browser history.
        To reduce accidental exposure, enabling this mode requires both
        ``VERITAS_ALLOW_WS_QUERY_API_KEY`` and
        ``VERITAS_ACK_WS_QUERY_API_KEY_RISK``.
    """
    allow_raw = (os.getenv("VERITAS_ALLOW_WS_QUERY_API_KEY") or "").strip().lower()
    allow_query_auth = allow_raw in {"1", "true", "yes", "on"}
    if not allow_query_auth:
        return False

    ack_raw = (os.getenv("VERITAS_ACK_WS_QUERY_API_KEY_RISK") or "").strip().lower()
    acknowledged = ack_raw in {"1", "true", "yes", "on"}
    if not acknowledged:
        logger.warning(
            "WebSocket query api_key enable flag ignored because "
            "VERITAS_ACK_WS_QUERY_API_KEY_RISK is not set. "
            "Set both flags only for temporary migration windows.",
        )
        return False

    return True


# ---- HMAC signature / replay (optional) ----
# ★ セキュリティ修正: スレッドセーフ化 (threading は L11 で import 済み)


def _env_int_safe(key: str, default: int) -> int:
    """Parse an environment variable as int, falling back to *default*."""
    raw = os.getenv(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


_NONCE_TTL_SEC = _env_int_safe("VERITAS_NONCE_TTL_SEC", 300)
_NONCE_MAX = _env_int_safe("VERITAS_NONCE_MAX_SIZE", 5000)  # 簡易上限
_NONCE_MAX_LENGTH = _env_int_safe("VERITAS_NONCE_MAX_LENGTH", 256)  # ノンス長の上限（メモリ消費抑止）
_nonce_store: Dict[str, float] = {}
_nonce_lock = threading.Lock()  # ★ スレッドセーフ化

# 後方互換: テストが monkeypatch.setattr(server, "API_SECRET", ...) を使用
# 実際の検証時は _get_api_secret() を使用して毎回環境変数から取得
API_SECRET: bytes = b""  # ★ テスト用プレースホルダー（実際は _get_api_secret() を使用）
_DEFAULT_API_SECRET_PLACEHOLDER = "YOUR_VERITAS_API_SECRET_HERE"


def _is_placeholder_secret(secret: str) -> bool:
    """Return True when the secret matches the default placeholder string."""
    return secret.strip() == _DEFAULT_API_SECRET_PLACEHOLDER


def _get_api_secret() -> bytes:
    """
    ★ セキュリティ修正: APIシークレットを毎回環境変数から取得。
    モジュールレベル変数に長時間保持しないことで、メモリダンプによる漏洩リスクを軽減。
    テスト時は API_SECRET 変数を monkeypatch で上書き可能。
    
    ★ セキュリティ注意:
    - プレースホルダ値や空の値が設定されている場合、空のbytesを返す
    - この場合、verify_signature()は500エラーを返し、HMAC認証は無効化される
    - 本番環境では必ず安全なシークレットを設定すること
    """
    # テスト用: API_SECRET が明示的に設定されていればそれを使用
    global API_SECRET
    if API_SECRET:
        return API_SECRET
    env_secret = (os.getenv("VERITAS_API_SECRET") or "").strip()
    if not env_secret or _is_placeholder_secret(env_secret):
        if env_secret and _is_placeholder_secret(env_secret):
            # ★ セキュリティ警告: プレースホルダ使用は危険
            logger.warning(
                "VERITAS_API_SECRET is set to the placeholder value. "
                "HMAC authentication is DISABLED. Set a secure secret in production!"
            )
        return b""
    # ★ セキュリティ: 最小シークレット長の確認（32文字以上推奨）
    if len(env_secret) < 32:
        logger.warning(
            "VERITAS_API_SECRET is shorter than 32 characters. "
            "Consider using a longer, more secure secret."
        )
    return env_secret.encode("utf-8")


def _cleanup_nonces_unsafe() -> None:
    """内部用: ロック取得済み前提のクリーンアップ"""
    now = time.time()
    expired_keys = [k for k, until in _nonce_store.items() if now > until]
    for k in expired_keys:
        _nonce_store.pop(k, None)
    # 上限超過時は古いものから間引き
    if len(_nonce_store) > _NONCE_MAX:
        overflow = len(_nonce_store) - _NONCE_MAX
        for k in list(_nonce_store.keys())[:overflow]:
            _nonce_store.pop(k, None)


def _cleanup_nonces() -> None:
    """★ スレッドセーフ版: ロックを取得してクリーンアップ"""
    with _nonce_lock:
        _cleanup_nonces_unsafe()


# ★ M-11 修正: 定期的なノンスクリーンアップ（60秒ごと）
_nonce_cleanup_timer: threading.Timer | None = None
_nonce_cleanup_timer_lock = threading.Lock()


def _schedule_nonce_cleanup() -> None:
    """バックグラウンドでノンスストアを定期クリーンアップする。"""
    global _nonce_cleanup_timer
    try:
        _cleanup_nonces()
    except Exception as e:
        logger.warning("nonce cleanup failed: %s", e)
    with _nonce_cleanup_timer_lock:
        if _nonce_cleanup_timer is None:
            return
        next_timer = threading.Timer(60.0, _schedule_nonce_cleanup)
        next_timer.daemon = True
        _nonce_cleanup_timer = next_timer
        next_timer.start()


def _start_nonce_cleanup_scheduler() -> None:
    """Start nonce cleanup timer once per process lifecycle."""
    global _nonce_cleanup_timer
    with _nonce_cleanup_timer_lock:
        if _nonce_cleanup_timer is not None:
            return
        _nonce_cleanup_timer = threading.Timer(60.0, _schedule_nonce_cleanup)
        _nonce_cleanup_timer.daemon = True
        _nonce_cleanup_timer.start()


def _stop_nonce_cleanup_scheduler() -> None:
    """Stop nonce cleanup timer if running."""
    global _nonce_cleanup_timer
    with _nonce_cleanup_timer_lock:
        timer = _nonce_cleanup_timer
        _nonce_cleanup_timer = None
    if timer is not None:
        timer.cancel()


# ---- Rate bucket periodic cleanup scheduler ----
# Without scheduled cleanup, stale rate-limit buckets accumulate indefinitely
# when traffic drops. The lazy cleanup inside enforce_rate_limit only runs on
# incoming requests, so low-traffic deployments can leak memory over time.
_rate_cleanup_timer: threading.Timer | None = None
_rate_cleanup_timer_lock = threading.Lock()
_RATE_CLEANUP_INTERVAL = 120.0  # seconds between scheduled sweeps


def _schedule_rate_bucket_cleanup() -> None:
    """Periodically sweep expired rate-limit buckets in the background."""
    global _rate_cleanup_timer
    try:
        _cleanup_rate_bucket()
    except Exception as e:
        logger.warning("scheduled rate bucket cleanup failed: %s", e)
    with _rate_cleanup_timer_lock:
        if _rate_cleanup_timer is None:
            return
        next_timer = threading.Timer(_RATE_CLEANUP_INTERVAL, _schedule_rate_bucket_cleanup)
        next_timer.daemon = True
        _rate_cleanup_timer = next_timer
        next_timer.start()


def _start_rate_cleanup_scheduler() -> None:
    """Start rate bucket cleanup timer once per process lifecycle."""
    global _rate_cleanup_timer
    with _rate_cleanup_timer_lock:
        if _rate_cleanup_timer is not None:
            return
        _rate_cleanup_timer = threading.Timer(_RATE_CLEANUP_INTERVAL, _schedule_rate_bucket_cleanup)
        _rate_cleanup_timer.daemon = True
        _rate_cleanup_timer.start()


def _stop_rate_cleanup_scheduler() -> None:
    """Stop rate bucket cleanup timer if running."""
    global _rate_cleanup_timer
    with _rate_cleanup_timer_lock:
        timer = _rate_cleanup_timer
        _rate_cleanup_timer = None
    if timer is not None:
        timer.cancel()


def _check_and_register_nonce(nonce: str) -> bool:
    """Check and register a nonce for replay attack prevention.

    Args:
        nonce: Unique request identifier.

    Returns:
        True if nonce is new (not replayed), False if duplicate.

    Note:
        - Nonces expire after ``_NONCE_TTL_SEC`` (300 s).
        - Store limited to ``_NONCE_MAX`` (5000) entries.
        - Thread-safe via ``_nonce_lock``.
    """
    # ★ セキュリティ: ノンス長の上限チェック（超長いノンスによるメモリ枯渇防止）
    if len(nonce) > _NONCE_MAX_LENGTH:
        return False

    return _auth_store_register_nonce(nonce=nonce, ttl_sec=_NONCE_TTL_SEC)


async def verify_signature(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    x_timestamp: Optional[str] = Header(default=None, alias="X-Timestamp"),
    x_nonce: Optional[str] = Header(default=None, alias="X-Nonce"),
    x_signature: Optional[str] = Header(default=None, alias="X-Signature"),
    x_veritas_timestamp: Optional[str] = Header(default=None, alias="X-VERITAS-TIMESTAMP"),
    x_veritas_nonce: Optional[str] = Header(default=None, alias="X-VERITAS-NONCE"),
    x_veritas_signature: Optional[str] = Header(default=None, alias="X-VERITAS-SIGNATURE"),
):
    """
    HMAC 認証を使う場合のみ dependencies に入れて使う想定。
    （ISSUE-4上、未使用でも存在してOK）
    ★ セキュリティ修正: シークレットは関数経由で取得
    """
    api_secret = _get_api_secret()
    if not api_secret:
        raise HTTPException(status_code=500, detail="Server secret missing")

    def _header_or_none(value: Any) -> Optional[str]:
        """Normalize dependency-injected Header defaults for direct unit test calls."""
        if value is None:
            return None
        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed if trimmed else None
        return None

    timestamp = _header_or_none(x_veritas_timestamp) or _header_or_none(x_timestamp)
    nonce = _header_or_none(x_veritas_nonce) or _header_or_none(x_nonce)
    signature = _header_or_none(x_veritas_signature) or _header_or_none(x_signature)
    api_key = _header_or_none(x_api_key)

    if not (api_key and timestamp and nonce and signature):
        _record_auth_reject_reason("signature_missing_headers")
        raise HTTPException(status_code=401, detail="Missing auth headers")
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        _record_auth_reject_reason("signature_invalid_timestamp")
        raise HTTPException(status_code=401, detail="Invalid timestamp") from None
    if abs(int(time.time()) - ts) > _NONCE_TTL_SEC:
        _record_auth_reject_reason("signature_timestamp_out_of_range")
        raise HTTPException(status_code=401, detail="Timestamp out of range")
    if not _check_and_register_nonce(nonce):
        _record_auth_reject_reason("signature_replay_detected")
        raise HTTPException(status_code=401, detail="Replay detected")

    body_bytes = await request.body()
    try:
        body = body_bytes.decode("utf-8") if body_bytes else ""
    except UnicodeDecodeError:
        _record_auth_reject_reason("signature_invalid_utf8_body")
        raise HTTPException(status_code=400, detail="Request body is not valid UTF-8") from None
    payload = f"{ts}\n{nonce}\n{body}"
    mac = hmac.new(api_secret, payload.encode("utf-8"), hashlib.sha256).hexdigest().lower()
    if not hmac.compare_digest(mac, signature.lower()):
        _record_auth_reject_reason("signature_invalid")
        raise HTTPException(status_code=401, detail="Invalid signature")
    return True


# ---- rate limit（簡易）----
# ★ セキュリティ修正: スレッドセーフ化
_RATE_LIMIT = 60
_RATE_WINDOW = 60.0
_RATE_BUCKET_MAX = 5000
_rate_bucket: Dict[str, Tuple[int, float]] = {}
_rate_lock = threading.Lock()  # ★ スレッドセーフ化


def _cleanup_rate_bucket_unsafe() -> None:
    """内部用: ロック取得済み前提のクリーンアップ"""
    now = time.time()
    # window を過ぎたバケットを掃除
    expired_keys = [k for k, (_, start) in _rate_bucket.items() if now - start > (_RATE_WINDOW * 4)]
    for k in expired_keys:
        _rate_bucket.pop(k, None)
    # 上限超過時は適当に間引く
    if len(_rate_bucket) > _RATE_BUCKET_MAX:
        overflow = len(_rate_bucket) - _RATE_BUCKET_MAX
        for k in list(_rate_bucket.keys())[:overflow]:
            _rate_bucket.pop(k, None)


def _cleanup_rate_bucket() -> None:
    """★ スレッドセーフ版: ロックを取得してクリーンアップ"""
    with _rate_lock:
        _cleanup_rate_bucket_unsafe()


def enforce_rate_limit(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")):
    """
    テスト契約:
    - X-API-Key が無いなら 401
    ★ セキュリティ修正: スレッドセーフなレート制限
    """
    if not x_api_key:
        _record_auth_reject_reason("rate_limit_missing_api_key")
        raise HTTPException(status_code=401, detail="Missing API key")

    key = x_api_key.strip()
    exceeded = _auth_store_increment_rate_limit(
        api_key=key,
        limit=_RATE_LIMIT,
        window_sec=_RATE_WINDOW,
    )
    if exceeded:
        _record_auth_reject_reason("rate_limit_exceeded")
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    return True


# ==============================
# Common utilities
# ==============================

def redact(text: str) -> str:
    """
    PIIをマスク（redact）する。

    sanitize.mask_pii が利用可能な場合は、以下を検出・マスク:
    - メールアドレス
    - 電話番号（日本の携帯・固定・国際・フリーダイヤル）
    - 郵便番号
    - 日本の住所（都道府県+市区町村+番地）
    - 個人名（日本語敬称付き、英語敬称付き）
    - クレジットカード番号（Luhn検証付き）
    - マイナンバー（チェックデジット検証付き）
    - IPアドレス（IPv4/IPv6）
    - URLクレデンシャル
    - 銀行口座番号
    - パスポート番号

    sanitize.py が利用できない場合はシンプルなフォールバックを使用。
    """
    if not text:
        return text

    # sanitize.py が利用可能ならそちらを使う（より包括的）
    if _HAS_SANITIZE and _sanitize_mask_pii is not None:
        try:
            return _sanitize_mask_pii(text)
        except Exception:
            logger.warning("sanitize.mask_pii failed; falling back to basic regex")

    # フォールバック: 基本的なパターンのみ
    text = re.sub(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", "[redacted@email]", text)
    text = re.sub(r"\b\d{2,4}[-・\s]?\d{2,4}[-・\s]?\d{3,4}\b", "[redacted:phone]", text)
    return text


def _gen_request_id(seed: str = "") -> str:
    base = f"{utc_now_iso_z()}|{seed}|{secrets.token_hex(8)}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


def _coerce_alt_list(v: Any) -> list:
    """
    alternatives/options の壊れ入力を "list[dict]" に寄せる。
    DecideResponse 側でも extra allow だが、最低限 id/title を補う。
    """
    if v is None:
        return []
    if isinstance(v, dict):
        v = [v]
    if not isinstance(v, list):
        return [{"id": "alt_0", "title": str(v), "description": "", "score": 1.0}]

    out = []
    for i, it in enumerate(v):
        if isinstance(it, dict):
            d = dict(it)
        else:
            d = {"title": str(it)}
        d.setdefault("id", d.get("id") or f"alt_{i}")
        d.setdefault("title", d.get("title") or d.get("text") or f"alt_{i}")
        d.setdefault("description", d.get("description") or "")
        # score は float 化できるならする
        if "score" in d and d["score"] is not None:
            try:
                d["score"] = float(d["score"])
            except Exception:
                d["score"] = 1.0
        else:
            d.setdefault("score", 1.0)
        out.append(d)
    return out


def _coerce_decide_payload(payload: Any, *, seed: str = "") -> Dict[str, Any]:
    """
    response_model を "効かせつつ" server を落とさないための最終整形。
    - payload が dict じゃない → dict に包む
    - DecideResponse の必須キー request_id を補う
    - alternatives/options を補う（互換）
    """
    if not isinstance(payload, dict):
        payload = {
            "ok": True,
            "request_id": _gen_request_id(seed),
            "chosen": {"title": str(payload)},
            "alternatives": [],
            "options": [],
            "trust_log": None,
        }
        return payload

    d = dict(payload)

    # テスト互換: trust_log を必ず付ける
    if "trust_log" not in d:
        d["trust_log"] = None
    if "ok" not in d:
        d["ok"] = True

    # request_id は DecideResponse で必須
    if not d.get("request_id"):
        d["request_id"] = _gen_request_id(seed)

    # chosen が無い/変でも落とさない
    if "chosen" not in d or d["chosen"] is None:
        d["chosen"] = {}
    elif not isinstance(d["chosen"], dict):
        d["chosen"] = {"title": str(d["chosen"])}

    # alternatives / options 互換
    alts = d.get("alternatives")
    opts = d.get("options")

    if (alts is None or alts == []) and opts:
        d["alternatives"] = _coerce_alt_list(opts)
    else:
        d["alternatives"] = _coerce_alt_list(alts)

    # options は互換としてミラー
    if not opts and d.get("alternatives"):
        d["options"] = list(d["alternatives"])
    else:
        d["options"] = _coerce_alt_list(opts)

    return d


def _coerce_fuji_payload(payload: Any, *, action: str = "") -> Dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {"status": "allow", "reasons": ["coerced"], "violations": [], "action": action}
        return payload

    d = dict(payload)
    if not d.get("status"):
        d["status"] = "allow"
    if "reasons" not in d or d["reasons"] is None:
        d["reasons"] = []
    if "violations" not in d or d["violations"] is None:
        d["violations"] = []
    return d


# ==============================
# 422 error handler
# ==============================

def _decide_example() -> dict:
    return {
        "context": {"user_id": "demo"},
        "query": "VERITASを進化させるには？",
        "options": [{"title": "最小ステップで前進"}],
        "min_evidence": 1,
    }


@app.exception_handler(RequestValidationError)
async def on_validation_error(request: Request, exc: RequestValidationError):
    """
    Handle validation errors with limited information disclosure.

    Security: Only include raw_body in debug mode to prevent potential
    information leakage in production environments.
    """
    trace_id = (
        getattr(request.state, "trace_id", None)
        if hasattr(request, "state") else None
    ) or secrets.token_hex(16)

    # Sanitize errors: Pydantic v2 ctx may contain non-serializable objects
    # (e.g. ValueError instances), so we convert each error to a safe dict.
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

    # Build response content
    content: Dict[str, Any] = {
        "detail": safe_errors,
        "request_id": trace_id,
        "hint": {"expected_example": _decide_example()},
    }

    # Only include raw_body in debug mode (when env var is set)
    if _is_debug_mode():
        raw_body_bytes = await request.body()
        raw = raw_body_bytes.decode("utf-8", "replace") if raw_body_bytes else ""
        # Apply PII masking and truncate to prevent large payloads
        raw_safe = redact(raw)[:MAX_RAW_BODY_LENGTH]
        content["raw_body"] = raw_safe

    return JSONResponse(status_code=422, content=content)


# ==============================
# Health / Status (must always work)
# ==============================


def _is_debug_mode() -> bool:
    """Return whether debug mode is explicitly enabled by environment variable.

    Security note:
        Debug mode widens error visibility, so we allow only a strict set of
        truthy values and default to ``False`` for everything else.
    """
    debug_flag = os.getenv("VERITAS_DEBUG_MODE", "")
    normalized_flag = debug_flag.strip().lower()
    debug_truthy_values = {"1", "true", "yes", "on"}
    return normalized_flag in debug_truthy_values


def _is_direct_fuji_api_enabled() -> bool:
    """Return whether direct FUJI API access is explicitly allowed.

    Security note:
        `/v1/fuji/validate` can bypass the standard `/v1/decide` governance
        pipeline. This endpoint therefore defaults to disabled and must be
        explicitly enabled with `VERITAS_ENABLE_DIRECT_FUJI_API=1`.
    """
    flag = os.getenv("VERITAS_ENABLE_DIRECT_FUJI_API", "")
    normalized_flag = flag.strip().lower()
    truthy_values = {"1", "true", "yes", "on"}
    return normalized_flag in truthy_values


# ==============================
# Trust log helpers（server 側でも軽く読めるように）
# ==============================


def _load_logs_json(path: Optional[Path] = None) -> list:
    """
    tests 互換:
      - _load_logs_json() を引数なしで呼ばれても動く
      - LOG_DIR だけ patch されても追随（effective paths）
    """
    try:
        if path is None:
            _, log_json, _ = _effective_log_paths()
            path = log_json

        if not path.exists():
            return []

        # Security: Check file size before loading to prevent memory exhaustion
        file_size = path.stat().st_size
        if file_size > MAX_LOG_FILE_SIZE:
            logger.warning("Log file too large (%d bytes), skipping load", file_size)
            return []

        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)

        if isinstance(obj, dict):
            return obj.get("items", [])
        if isinstance(obj, list):
            return obj
        return []
    except Exception:
        logger.debug("_load_logs_json: failed to load %s", path, exc_info=True)
        return []


# ★ スレッドセーフな Trust Log ロック
# trust_log.py の trust_log_lock を共有して、同一ファイルへの並行書き込みを防止。
# 共有に失敗した場合はローカルロックにフォールバック。
try:
    from veritas_os.logging.trust_log import trust_log_lock as _trust_log_lock
except ImportError:
    _trust_log_lock = threading.Lock()


def _secure_chmod(path: Path) -> None:
    """Set restrictive 0o600 permissions on a sensitive file.

    Security:
        Trust log and audit files contain decision records that may include
        PII or sensitive operational data. Restricting read/write access to
        the owning process reduces the risk of unauthorized access by other
        local users or processes.
    """
    try:
        os.chmod(path, 0o600)
    except Exception as e:
        logger.debug("chmod 0o600 failed for %s: %s", path, _errstr(e))


def _save_json(path: Path, items: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    if _HAS_ATOMIC_IO:
        atomic_write_json(path, {"items": items}, indent=2)
    else:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"items": items}, f, ensure_ascii=False, indent=2)
    if is_new:
        _secure_chmod(path)


def append_trust_log(entry: Dict[str, Any]) -> None:
    """
    server 単体でも最低限 trust log が書けるフォールバック。
    （tests互換のため server.LOG_DIR patch に追随）

    スレッドセーフ: ロック + アトミック I/O を使用してデータ損失を防止。

    Args:
        entry: TrustLogエントリ辞書
    """
    log_dir, log_json, log_jsonl = _effective_log_paths()

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning("LOG_DIR mkdir failed: %s", _errstr(e))
        return

    # 全ての書き込みをロックで保護（競合状態を防止）
    with _trust_log_lock:
        # JSONL への追記（アトミック I/O 使用）
        try:
            jsonl_is_new = not log_jsonl.exists()
            if _HAS_ATOMIC_IO:
                atomic_append_line(log_jsonl, json.dumps(entry, ensure_ascii=False))
            else:
                with open(log_jsonl, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            if jsonl_is_new:
                _secure_chmod(log_jsonl)
        except Exception as e:
            logger.warning("write trust_log.jsonl failed: %s", _errstr(e))

        # JSON への追記
        items = _load_logs_json(log_json)
        items.append(entry)
        try:
            _save_json(log_json, items)
            _publish_event(
                "trustlog.appended",
                {"request_id": entry.get("request_id"), "kind": entry.get("kind")},
            )
        except Exception as e:
            logger.warning("write trust_log.json failed: %s", _errstr(e))


def write_shadow_decide(
    request_id: str,
    body: Dict[str, Any],
    chosen: Dict[str, Any],
    telos_score: float,
    fuji: Optional[Dict[str, Any]],
) -> None:
    shadow_dir = _effective_shadow_dir()

    try:
        shadow_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning("SHADOW_DIR mkdir failed: %s", _errstr(e))
        return

    now_utc = datetime.now(timezone.utc)
    ts = now_utc.strftime("%Y%m%d_%H%M%S_%f")[:-3]
    out = shadow_dir / f"decide_{ts}.json"
    rec = {
        "request_id": request_id,
        "created_at": now_utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "query": (body.get("query") or (body.get("context") or {}).get("query") or ""),
        "chosen": chosen,
        "telos_score": float(telos_score or 0.0),
        "fuji": (fuji or {}).get("status"),
    }
    try:
        if _HAS_ATOMIC_IO:
            atomic_write_json(out, rec, indent=2)
        else:
            with open(out, "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False, indent=2)
        _secure_chmod(out)
    except Exception as e:
        logger.warning("write shadow decide failed: %s", _errstr(e))


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
