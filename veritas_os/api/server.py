# veritas_os/api/server.py
from __future__ import annotations

import asyncio
import hashlib
import hmac
import importlib
import json
import logging
import os
import queue
import re
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional, Tuple

# ---- ロガー設定（標準化: print → logging）----
logger = logging.getLogger(__name__)

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security.api_key import APIKeyHeader

# ---- API層（ここは基本 "安定" 前提）----
from veritas_os.api.schemas import DecideRequest, DecideResponse, FujiDecision
from veritas_os.api.governance import get_policy, update_policy
from veritas_os.api.constants import (
    DECISION_ALLOW,
    DECISION_REJECTED,
    MAX_LOG_FILE_SIZE,
    MAX_RAW_BODY_LENGTH,
    VALID_MEMORY_KINDS,
)  # noqa: F401

from veritas_os.logging.trust_log import (
    get_trust_log_page,
    get_trust_logs_by_request,
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
# - import時に “重い/脆い” モジュールを確定importしない
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


# place-holders that are always present (so monkeypatch.setattr won’t fail)
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


def get_cfg() -> Any:
    """
    cfg は “無い/壊れてる” 可能性があるので必ずフォールバックを返す。
    CORS設定など起動に関わるため、ここで絶対に例外を外へ出さない。
    """
    global _cfg_state
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

app = FastAPI(title="VERITAS Public API", version="1.0.3")

# ★ セキュリティ: allow_credentials は明示的なオリジンが設定されている場合のみ True
# 空の場合に True にすると、ブラウザの CORS チェックを意図せずバイパスするリスクがある
_cors_origins = getattr(cfg, "cors_allow_origins", [])
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=bool(_cors_origins),
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["X-API-Key", "X-Timestamp", "X-Nonce", "X-Signature", "Content-Type", "Authorization"],
)


# ★ C-3 修正: リクエストボディサイズ制限 (DoS対策)
# デフォルト: 10MB。環境変数で設定可能。
try:
    MAX_REQUEST_BODY_SIZE = int(os.getenv("VERITAS_MAX_REQUEST_BODY_SIZE", 10 * 1024 * 1024))
except ValueError:
    MAX_REQUEST_BODY_SIZE = 10 * 1024 * 1024
    logger.warning("Invalid VERITAS_MAX_REQUEST_BODY_SIZE, using default 10MB")


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


def require_api_key(x_api_key: Optional[str] = Security(api_key_scheme)):
    """
    テスト契約:
    - サーバ側の API Key が未設定なら 500
    - ヘッダが無い/不一致なら 401
    """
    expected = (_get_expected_api_key() or "").strip()
    if not expected:
        raise HTTPException(status_code=500, detail="Server API key not configured")
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    if not secrets.compare_digest(x_api_key.strip(), expected):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


def require_api_key_header_or_query(
    x_api_key: Optional[str] = Security(api_key_scheme),
    api_key: Optional[str] = Query(default=None),
):
    """Authenticate by header (preferred) or query parameter for SSE clients."""
    expected = (_get_expected_api_key() or "").strip()
    if not expected:
        raise HTTPException(status_code=500, detail="Server API key not configured")

    candidate = (x_api_key or api_key or "").strip()
    if not candidate:
        raise HTTPException(status_code=401, detail="Missing API key")
    if not secrets.compare_digest(candidate, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


# ---- HMAC signature / replay (optional) ----
# ★ セキュリティ修正: スレッドセーフ化 (threading は L11 で import 済み)

_NONCE_TTL_SEC = 300
_NONCE_MAX = 5000  # 簡易上限
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


def _schedule_nonce_cleanup() -> None:
    """バックグラウンドでノンスストアを定期クリーンアップする"""
    global _nonce_cleanup_timer
    try:
        _cleanup_nonces()
    except Exception as e:
        logger.warning("nonce cleanup failed: %s", e)
    _nonce_cleanup_timer = threading.Timer(60.0, _schedule_nonce_cleanup)
    _nonce_cleanup_timer.daemon = True
    _nonce_cleanup_timer.start()


# 初回スケジュール
_schedule_nonce_cleanup()


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
    with _nonce_lock:
        _cleanup_nonces_unsafe()
        if nonce in _nonce_store:
            return False
        _nonce_store[nonce] = time.time() + _NONCE_TTL_SEC
        return True


async def verify_signature(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    x_timestamp: Optional[str] = Header(default=None, alias="X-Timestamp"),
    x_nonce: Optional[str] = Header(default=None, alias="X-Nonce"),
    x_signature: Optional[str] = Header(default=None, alias="X-Signature"),
):
    """
    HMAC 認証を使う場合のみ dependencies に入れて使う想定。
    （ISSUE-4上、未使用でも存在してOK）
    ★ セキュリティ修正: シークレットは関数経由で取得
    """
    api_secret = _get_api_secret()
    if not api_secret:
        raise HTTPException(status_code=500, detail="Server secret missing")
    if not (x_api_key and x_timestamp and x_nonce and x_signature):
        raise HTTPException(status_code=401, detail="Missing auth headers")
    try:
        ts = int(x_timestamp)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid timestamp") from None
    if abs(int(time.time()) - ts) > _NONCE_TTL_SEC:
        raise HTTPException(status_code=401, detail="Timestamp out of range")
    if not _check_and_register_nonce(x_nonce):
        raise HTTPException(status_code=401, detail="Replay detected")

    body_bytes = await request.body()
    try:
        body = body_bytes.decode("utf-8") if body_bytes else ""
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Request body is not valid UTF-8") from None
    payload = f"{ts}\n{x_nonce}\n{body}"
    mac = hmac.new(api_secret, payload.encode("utf-8"), hashlib.sha256).hexdigest().lower()
    if not hmac.compare_digest(mac, (x_signature or "").lower()):
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
        raise HTTPException(status_code=401, detail="Missing API key")

    key = x_api_key.strip()
    now = time.time()

    with _rate_lock:
        _cleanup_rate_bucket_unsafe()

        count, start = _rate_bucket.get(key, (0, now))

        if now - start > _RATE_WINDOW:
            _rate_bucket[key] = (1, now)
            return True

        if count + 1 > _RATE_LIMIT:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        _rate_bucket[key] = (count + 1, start)
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
    alternatives/options の壊れ入力を “list[dict]” に寄せる。
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
    response_model を “効かせつつ” server を落とさないための最終整形。
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
    # Build response content
    content: Dict[str, Any] = {
        "detail": exc.errors(),
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


@app.get("/")
def root():
    return {"ok": True, "service": "veritas-api", "server_time": utc_now_iso_z()}


@app.get("/health")
@app.get("/v1/health")
def health():
    return {"ok": True, "uptime": int(time.time() - START_TS)}


@app.get("/status")
@app.get("/v1/status")
@app.get("/api/status")
def status():
    expected = (_get_expected_api_key() or "").strip()
    result = {
        "ok": True,
        "version": "veritas-api 1.0.3",
        "uptime": int(time.time() - START_TS),
        "server_time": utc_now_iso_z(),
        "pipeline_ok": get_decision_pipeline() is not None,
        "api_key_configured": bool(expected),
    }
    # ★ M-13 修正: 内部エラー詳細はデバッグモード時のみ公開
    # 本番環境では実装の詳細が漏洩するのを防止
    if _is_debug_mode():
        result["cfg_error"] = _cfg_state.err
        result["pipeline_error"] = _pipeline_state.err
    else:
        result["cfg_error"] = bool(_cfg_state.err)
        result["pipeline_error"] = bool(_pipeline_state.err)
    return result


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


def _save_json(path: Path, items: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if _HAS_ATOMIC_IO:
        atomic_write_json(path, {"items": items}, indent=2)
    else:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"items": items}, f, ensure_ascii=False, indent=2)


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
            if _HAS_ATOMIC_IO:
                atomic_append_line(log_jsonl, json.dumps(entry, ensure_ascii=False))
            else:
                with open(log_jsonl, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
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
    except Exception as e:
        logger.warning("write shadow decide failed: %s", _errstr(e))


# ==============================
# main: /v1/decide
# ==============================

@app.post(
    "/v1/decide",
    response_model=DecideResponse,
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
async def decide(req: DecideRequest, request: Request):
    p = get_decision_pipeline()
    if p is None:
        _log_decide_failure("decision_pipeline unavailable", _pipeline_state.err)
        _publish_event("decide.completed", {"ok": False, "error": DECIDE_GENERIC_ERROR})
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": DECIDE_GENERIC_ERROR,
                "detail": DECIDE_GENERIC_ERROR,
                "trust_log": None,  # ★互換
            },
        )

    try:
        payload = await p.run_decide_pipeline(req=req, request=request)
    except Exception as e:
        _log_decide_failure("decision_pipeline execution failed", e)
        _publish_event("decide.completed", {"ok": False, "error": DECIDE_GENERIC_ERROR})
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": DECIDE_GENERIC_ERROR,
                "detail": DECIDE_GENERIC_ERROR,
                "trust_log": None,  # ★互換
            },
        )

    # ★ response_model を効かせつつ壊れpayloadでも落ちないように最終整形
    coerced = _coerce_decide_payload(payload, seed=getattr(req, "query", "") or "")
    # DecideResponse 側に “落ちない” バリデータがある前提で model_validate
    try:
        _publish_event(
            "decide.completed",
            {
                "ok": bool(coerced.get("ok", True)),
                "request_id": coerced.get("request_id"),
                "decision": coerced.get("decision"),
            },
        )
        fuji_payload = coerced.get("fuji") or {}
        if str(fuji_payload.get("status", "")).lower() in {"reject", "rejected", DECISION_REJECTED}:
            _publish_event(
                "fuji.rejected",
                {
                    "request_id": coerced.get("request_id"),
                    "status": fuji_payload.get("status"),
                    "reasons": fuji_payload.get("reasons", []),
                },
            )
        return DecideResponse.model_validate(coerced)
    except Exception as e:
        # 最後の保険：型検証で落ちても 503 ではなく JSON にして "落ちない" を優先
        # ok=False でクライアントが正常レスポンスと区別できるようにする
        # ★ セキュリティ修正: 内部エラー詳細はデバッグモード時のみ公開
        logger.error("DecideResponse validation failed: %s", _errstr(e))
        content = {
            **coerced,
            "ok": False,
            "warn": "response_model_validation_failed",
        }
        if _is_debug_mode():
            content["warn_detail"] = _errstr(e)
        _publish_event(
            "decide.completed",
            {"ok": False, "warn": "response_model_validation_failed", "request_id": coerced.get("request_id")},
        )
        return JSONResponse(
            status_code=200,
            content=content,
        )


# ==============================
# FUJI quick validate
# ==============================

def _call_fuji(fc: Any, action: str, context: dict) -> dict:
    """
    validate_action / validate の微妙なシグネチャ差を吸収する。
    """
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
                return fn(action, context)  # type: ignore
            except TypeError:
                return fn(action)  # type: ignore
    raise RuntimeError("fuji_core has neither validate_action nor validate")


@app.post(
    "/v1/fuji/validate",
    response_model=FujiDecision,
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
def fuji_validate(payload: dict):
    fc = get_fuji_core()
    if fc is None:
        logger.warning("fuji_validate: fuji_core unavailable: %s", _fuji_state.err)
        # Return 503 as JSONResponse to ensure proper format
        return JSONResponse(
            status_code=503,
            content={"detail": "fuji_core unavailable"}
        )

    # ★ セキュリティ修正: action フィールドのサイズ制限（DoS対策）
    action = str(payload.get("action", "") or "")[:10_000]
    context = payload.get("context") or {}

    try:
        result = _call_fuji(fc, action, context)
    except RuntimeError as e:
        # Check if this is the "neither validate_action nor validate" error
        # Note: Using string matching is fragile but matches test expectations
        err_msg = str(e)
        if "neither validate_action nor validate" in err_msg:
            # This specific error should return 500 as expected by test_fuji_validate_no_impl_raises_500
            logger.error("fuji_validate: %s", err_msg)
            return JSONResponse(
                status_code=500,
                content={"detail": err_msg}
            )
        # Other RuntimeErrors: return 200 with error structure
        # ★ セキュリティ修正: 内部エラー詳細をレスポンスに含めない
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
        # All other exceptions: return 200 with error structure
        # ★ セキュリティ修正: 内部エラー詳細をレスポンスに含めない
        logger.error("fuji_validate error: %s", _errstr(e))
        return JSONResponse(
            status_code=200,
            content={
                "status": "error",
                "reasons": ["Validation failed"],
                "violations": []
            }
        )

    coerced = _coerce_fuji_payload(result, action=action)
    if str(coerced.get("status", "")).lower() in {"reject", "rejected", DECISION_REJECTED}:
        _publish_event(
            "fuji.rejected",
            {"action": action, "status": coerced.get("status"), "reasons": coerced.get("reasons", [])},
        )
    try:
        return FujiDecision.model_validate(coerced)
    except Exception as e:
        # 最後の保険：落ちるより返す
        # ★ セキュリティ修正: 内部エラー詳細はデバッグモード時のみ公開
        logger.error("FujiDecision validation failed: %s", _errstr(e))
        content = {
            **coerced,
            "warn": "response_model_validation_failed",
        }
        if _is_debug_mode():
            content["warn_detail"] = _errstr(e)
        _publish_event(
            "decide.completed",
            {"ok": False, "warn": "response_model_validation_failed", "request_id": coerced.get("request_id")},
        )
        return JSONResponse(
            status_code=200,
            content=content,
        )


# ==============================
# Memory API
# ==============================

def _store_put(store: Any, user_id: str, key: str, value: dict) -> None:
    if not hasattr(store, "put"):
        raise RuntimeError("store.put not found")
    fn = store.put
    try:
        fn(user_id, key=key, value=value)
        return
    except TypeError:
        pass
    try:
        fn(user_id, key, value)
        return
    except TypeError:
        fn(key, value)  # type: ignore


def _store_get(store: Any, user_id: str, key: str) -> Any:
    if not hasattr(store, "get"):
        raise RuntimeError("store.get not found")
    fn = store.get
    try:
        return fn(user_id, key=key)
    except TypeError:
        try:
            return fn(user_id, key)
        except TypeError:
            return fn(key)  # type: ignore


def _store_search(store: Any, *, query: str, k: int, kinds: Any, min_sim: float, user_id: Optional[str]) -> Any:
    if not hasattr(store, "search"):
        raise RuntimeError("store.search not found")
    fn = store.search
    # prefer richest signature
    try:
        return fn(query=query, k=k, kinds=kinds, min_sim=min_sim, user_id=user_id)
    except TypeError:
        pass
    try:
        return fn(query=query, k=k, kinds=kinds, min_sim=min_sim)
    except TypeError:
        pass
    try:
        return fn(query=query, k=k)
    except TypeError:
        return fn(query)


@app.post("/v1/memory/put", dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)])
def memory_put(body: dict):
    store = get_memory_store()
    if store is None:
        logger.warning("memory_put: memory store unavailable: %s", _memory_store_state.err)
        return {"ok": False, "error": "memory store unavailable"}

    try:
        user_id = body.get("user_id", "anon")
        key = body.get("key") or f"memory_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        value = body.get("value") or {}

        # ★ セキュリティ修正: 入力サイズの制限（DoS対策）
        text = (body.get("text") or "").strip()
        if len(text) > 100_000:
            return {"ok": False, "error": "text too large (max 100000 chars)"}
        tags = body.get("tags") or []
        if len(tags) > 100:
            return {"ok": False, "error": "too many tags (max 100)"}
        meta = body.get("meta") or {}

        legacy_saved = False
        if value:
            try:
                _store_put(store, user_id, key, value)
                legacy_saved = True
            except Exception as e:
                logger.warning("[MemoryOS][legacy] Error: %s", e)

        kind = (body.get("kind") or "semantic").strip().lower()
        if kind not in VALID_MEMORY_KINDS:
            kind = "semantic"

        new_id = None
        if text:
            try:
                text_clean = redact(text)
                meta_for_store = dict(meta)
                meta_for_store.setdefault("user_id", user_id)
                meta_for_store.setdefault("kind", kind)

                if hasattr(store, "put"):
                    vector_item = {
                        "text": text_clean,
                        "tags": tags,
                        "meta": meta_for_store,
                    }
                    try:
                        new_id = store.put(kind, vector_item)
                    except TypeError:
                        if hasattr(store, "put_episode"):
                            new_id = store.put_episode(
                                text=text_clean,
                                tags=tags,
                                meta=meta_for_store,
                            )
                        else:
                            raise
                elif hasattr(store, "put_episode"):
                    new_id = store.put_episode(
                        text=text_clean,
                        tags=tags,
                        meta=meta_for_store,
                    )
                else:
                    episode_key = f"episode_{int(time.time())}"
                    _store_put(
                        store,
                        user_id,
                        episode_key,
                        {"text": text_clean, "tags": tags, "meta": meta_for_store},
                    )
                    new_id = episode_key
            except Exception as e:
                logger.warning("[MemoryOS][vector] Error: %s", e)

        return {
            "ok": True,
            "legacy": {"saved": legacy_saved, "key": key if legacy_saved else None},
            "vector": {
                "saved": bool(new_id),
                "id": new_id,
                "kind": kind if new_id else None,
                "tags": tags if new_id else None,
            },
            "size": len(str(value)) if value else len(text),
        }

    except Exception as e:
        logger.error("[MemoryOS] Error: %s", e)
        return {"ok": False, "error": "memory operation failed"}


@app.post("/v1/memory/search", dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)])
def memory_search(payload: dict):
    store = get_memory_store()
    if store is None:
        logger.warning("memory_search: memory store unavailable: %s", _memory_store_state.err)
        return {"ok": False, "error": "memory store unavailable", "hits": [], "count": 0}

    try:
        # ★ セキュリティ修正: query フィールドのサイズ制限（DoS対策）
        q = str(payload.get("query", ""))[:10_000]
        kinds = payload.get("kinds")
        try:
            k = max(1, min(int(payload.get("k", 8)), 100))
        except (ValueError, TypeError):
            k = 8
        try:
            min_sim = max(0.0, min(float(payload.get("min_sim", 0.25)), 1.0))
        except (ValueError, TypeError):
            min_sim = 0.25
        user_id = payload.get("user_id")

        # ★ セキュリティ修正: user_id 必須化（未指定時は全ユーザーのメモリが返る問題を修正）
        if not user_id:
            return {"ok": False, "error": "user_id is required", "hits": [], "count": 0}

        raw_hits = _store_search(store, query=q, k=k, kinds=kinds, min_sim=min_sim, user_id=user_id)

        # ★ Bug fix: MemoryStore.search() returns Dict[str, List[Dict]], not a flat list.
        # Flatten the dict-of-lists into a single list before filtering.
        if isinstance(raw_hits, dict):
            flat_hits: list = []
            for kind_hits in raw_hits.values():
                if isinstance(kind_hits, list):
                    flat_hits.extend(kind_hits)
            raw_hits = flat_hits
        elif not isinstance(raw_hits, list):
            raw_hits = list(raw_hits) if raw_hits else []

        norm_hits = []
        for h in (raw_hits or []):
            if isinstance(h, dict):
                meta = h.get("meta") or {}
                # ★ セキュリティ修正: 常に user_id でフィルタリング
                if meta.get("user_id") == user_id:
                    norm_hits.append(h)
            else:
                # ★ セキュリティ修正: non-dict ヒット（生ID文字列等）は user_id を
                # 検証できないため、情報漏洩防止のためスキップする
                continue

        return {"ok": True, "hits": norm_hits, "count": len(norm_hits)}

    except Exception as e:
        logger.error("[MemoryOS][search] Error: %s", e)
        return {"ok": False, "error": "memory search failed", "hits": [], "count": 0}


@app.post("/v1/memory/get", dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)])
def memory_get(body: dict):
    store = get_memory_store()
    if store is None:
        # Do not expose internal error details to clients
        return {"ok": False, "error": "memory store unavailable", "value": None}

    try:
        uid = body.get("user_id")
        key = body.get("key")
        if not uid or not key:
            return {"ok": False, "error": "user_id and key are required", "value": None}
        # ★ セキュリティ修正: user_id/key フィールドのサイズ制限（DoS対策）
        uid = str(uid)[:500]
        key = str(key)[:500]
        value = _store_get(store, uid, key)
        return {"ok": True, "value": value}
    except Exception as e:
        logger.error("memory_get failed: %s", e)
        return {"ok": False, "error": "memory retrieval failed", "value": None}


# ==============================
# metrics for Doctor
# ==============================

@app.get("/v1/metrics", dependencies=[Depends(require_api_key)])
def metrics():
    shadow_dir = _effective_shadow_dir()
    _, _, log_jsonl = _effective_log_paths()

    files = sorted(shadow_dir.glob("decide_*.json"))
    last_at = None
    if files:
        try:
            with open(files[-1], encoding="utf-8") as f:
                last_at = json.load(f).get("created_at")
        except Exception:
            pass

    lines = 0
    try:
        if log_jsonl.exists():
            with open(log_jsonl, encoding="utf-8") as f:
                for _ in f:
                    lines += 1
    except Exception as e:
        logger.warning("read trust_log.jsonl failed: %s", _errstr(e))

    result = {
        "decide_files": len(files),
        "trust_jsonl_lines": lines,
        "last_decide_at": last_at,
        "server_time": utc_now_iso_z(),
        "pipeline_ok": get_decision_pipeline() is not None,
    }
    # ★ M-13 修正: 内部エラー詳細はデバッグモード時のみ公開
    if _is_debug_mode():
        result["pipeline_error"] = _pipeline_state.err
        result["cfg_error"] = _cfg_state.err
    else:
        result["pipeline_error"] = bool(_pipeline_state.err)
        result["cfg_error"] = bool(_cfg_state.err)
    return result


@app.get("/v1/events", dependencies=[Depends(require_api_key_header_or_query)])
async def events(request: Request, heartbeat_sec: int = Query(default=15, ge=5, le=60)):
    """Server-Sent Events stream for near-real-time UI updates."""
    subscriber = _event_hub.register()

    async def _stream():
        # ★ 修正: blocking な subscriber.get() を asyncio.to_thread 経由で実行し、
        # イベントループのスレッドプールを枯渇させないようにする。
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.to_thread(subscriber.get, timeout=heartbeat_sec)
                    yield _format_sse_message(item)
                except queue.Empty:
                    yield f": heartbeat {utc_now_iso_z()}\n\n"
        finally:
            _event_hub.unregister(subscriber)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(_stream(), media_type="text/event-stream", headers=headers)


# ==============================
# Trust Feedback
# ==============================

@app.get("/v1/trust/logs", dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)])
def trust_logs(cursor: Optional[str] = None, limit: int = 50):
    """TrustLog をページング取得する。"""
    return get_trust_log_page(cursor=cursor, limit=limit)


@app.get("/v1/trust/{request_id}", dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)])
def trust_log_by_request(request_id: str):
    """request_id 単位で TrustLog を取得する。"""
    return get_trust_logs_by_request(request_id=request_id)


@app.post("/v1/trust/feedback", dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)])
def trust_feedback(body: dict):
    """
    人間からのフィードバックを trust_log に記録する簡易API。

    Notes:
        score は 0.0〜1.0 に正規化してから保存する。
        数値変換に失敗した場合は既定値 0.5 を採用する。
    """
    vc = get_value_core()
    if vc is None:
        logger.warning("trust_feedback: value_core unavailable: %s", _value_core_state.err)
        return {"status": "error", "detail": "value_core unavailable"}

    try:
        uid = str(body.get("user_id") or "anon")[:500]
        raw_score = body.get("score", 0.5)
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            score = 0.5
        score = max(0.0, min(1.0, score))
        # ★ セキュリティ修正: note/source フィールドのサイズ制限（DoS対策）
        note = str(body.get("note") or "")[:10_000]
        source = str(body.get("source") or "manual")[:200]
        extra = {"api": "/v1/trust/feedback"}

        if hasattr(vc, "append_trust_log"):
            vc.append_trust_log(
                user_id=uid,
                score=score,
                note=note,
                source=source,
                extra=extra,
            )
            _publish_event(
                "trustlog.appended",
                {"kind": "feedback", "user_id": uid, "source": source},
            )
            return {"status": "ok", "user_id": uid}

        return {"status": "error", "detail": "value_core.append_trust_log not found"}

    except Exception as e:
        # Log the detailed error server-side, but do not expose it to the client.
        logger.error("[Trust] feedback failed: %s", e)
        return {"status": "error", "detail": "internal error in trust_feedback"}


# ==============================
# Governance Policy API
# ==============================

@app.get("/v1/governance/policy", dependencies=[Depends(require_api_key)])
def governance_get():
    """Return the current governance policy."""
    try:
        policy = get_policy()
        return {"ok": True, "policy": policy}
    except Exception as e:
        logger.error("governance_get failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to load governance policy"},
        )


@app.put("/v1/governance/policy", dependencies=[Depends(require_api_key)])
def governance_put(body: dict):
    """Update the governance policy (partial merge)."""
    try:
        updated = update_policy(body)
        _publish_event(
            "governance.updated",
            {"updated_by": updated.get("updated_by", "api")},
        )
        return {"ok": True, "policy": updated}
    except Exception as e:
        logger.error("governance_put failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to update governance policy"},
        )
