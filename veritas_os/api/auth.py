# veritas_os/api/auth.py
"""API Key, HMAC signature verification, AuthSecurityStore, and auth failure tracking."""
from __future__ import annotations

import hashlib
import hmac
import importlib
import logging
import os
import secrets
import threading
import time
from functools import lru_cache
from typing import Any, Dict, Optional, Protocol, Tuple

from fastapi import Header, HTTPException, Query, Request, Security, WebSocket
from fastapi.security.api_key import APIKeyHeader

from veritas_os.api.utils import _errstr, redact

logger = logging.getLogger(__name__)


# ==============================
# Auth failure tracking / metrics
# ==============================

_AUTH_REJECT_REASON_METRICS: Dict[str, int] = {}
_AUTH_REJECT_REASON_LOCK = threading.Lock()


def _record_auth_reject_reason(reason_code: str) -> None:
    """Track reject reason counters for operational audit metrics."""
    with _AUTH_REJECT_REASON_LOCK:
        _AUTH_REJECT_REASON_METRICS[reason_code] = _AUTH_REJECT_REASON_METRICS.get(reason_code, 0) + 1


def _snapshot_auth_reject_reason_metrics() -> Dict[str, int]:
    """Return thread-safe snapshot of auth reject reason counters."""
    with _AUTH_REJECT_REASON_LOCK:
        return dict(_AUTH_REJECT_REASON_METRICS)


# ==============================
# Auth failure rate limiting (IP-based)
# ==============================

_AUTH_FAIL_RATE_LIMIT = 10
_AUTH_FAIL_WINDOW = 60.0
_AUTH_FAIL_BUCKET_MAX = 10000
_auth_fail_bucket: Dict[str, Tuple[int, float]] = {}
_auth_fail_lock = threading.Lock()


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


# ==============================
# AuthSecurityStore protocol & implementations
# ==============================

class AuthSecurityStore(Protocol):
    """Shared store interface for auth security controls."""

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
    """Thread-safe in-memory implementation for auth security controls."""

    def register_nonce(self, nonce: str, ttl_sec: float) -> bool:
        # Import here to avoid circular dependency - these are managed in rate_limiting
        from veritas_os.api.rate_limiting import (
            _nonce_lock,
            _nonce_store,
            _cleanup_nonces_unsafe,
        )
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
        from veritas_os.api.rate_limiting import (
            _rate_lock,
            _rate_bucket,
            _cleanup_rate_bucket_unsafe,
        )
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
    """Create auth security store from environment configuration."""
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


def _get_effective_auth_store():
    """Return the auth store, checking server module for test monkeypatches."""
    try:
        from veritas_os.api import server as srv
        store = getattr(srv, "_AUTH_SECURITY_STORE", None)
        if store is not None and store is not _AUTH_SECURITY_STORE:
            return store
    except Exception:
        pass
    return _AUTH_SECURITY_STORE


def _auth_store_failure_mode() -> str:
    """Return auth store failure policy: ``open`` or ``closed``.

    Security hardening:
        Production profiles always resolve to ``closed`` even if operators
        misconfigure ``VERITAS_AUTH_STORE_FAILURE_MODE=open``. This prevents
        nonce/auth/rate-limit store outages from silently degrading security.
        Fail-open is also restricted to explicit local/test profiles so shared
        staging environments or unset deployment profiles cannot accidentally
        weaken auth protections.
    """
    profile = (os.getenv("VERITAS_ENV") or "").strip().lower()
    node_env = (os.getenv("NODE_ENV") or "").strip().lower()
    if profile in {"prod", "production"} or node_env == "production":
        return "closed"

    raw = (os.getenv("VERITAS_AUTH_STORE_FAILURE_MODE") or "closed").strip().lower()
    allow_fail_open = (
        (os.getenv("VERITAS_AUTH_ALLOW_FAIL_OPEN") or "")
        .strip()
        .lower() in {"1", "true", "yes", "on"}
    )
    if raw in {"open", "closed"}:
        if raw == "open":
            if not allow_fail_open:
                logger.warning(
                    "[security-warning] VERITAS_AUTH_STORE_FAILURE_MODE=open was ignored. "
                    "Set VERITAS_AUTH_ALLOW_FAIL_OPEN=true only for controlled non-production testing."
                )
                return "closed"
            if profile not in {"dev", "development", "local", "test"}:
                logger.warning(
                    "[security-warning] VERITAS_AUTH_STORE_FAILURE_MODE=open was ignored for "
                    "VERITAS_ENV=%s. Fail-open is restricted to explicit local/test profiles.",
                    profile or "unset",
                )
                return "closed"
            _warn_auth_store_fail_open_once()
        return raw
    return "closed"


@lru_cache(maxsize=1)
def _warn_auth_store_fail_open_once() -> None:
    """Warn once when auth store fallback mode is fail-open.

    Fail-open helps local debugging but weakens nonce and rate-limit protection
    during auth store outages.
    """
    logger.warning(
        "[security-warning] VERITAS_AUTH_STORE_FAILURE_MODE=open is enabled. "
        "Use closed in production to avoid auth bypass during store failures."
    )


def auth_store_health_snapshot() -> Dict[str, Any]:
    """Return auth store runtime health for monitoring and audit visibility.

    The snapshot intentionally exposes posture rather than secrets so `/health`
    can reveal when a distributed deployment silently fell back to the
    in-memory store, or when non-production testing is running in fail-open
    mode. This helps operators detect degraded security before an outage turns
    into an auth control gap.
    """
    requested_mode = (
        (os.getenv("VERITAS_AUTH_SECURITY_STORE") or "memory").strip().lower()
        or "memory"
    )
    failure_mode = _auth_store_failure_mode()
    effective_store = _get_effective_auth_store()
    effective_mode = "redis" if isinstance(effective_store, RedisAuthSecurityStore) else "memory"

    status = "ok"
    reasons = []

    if requested_mode == "redis" and effective_mode != "redis":
        status = "degraded"
        reasons.append("redis_store_unavailable")

    if failure_mode == "open":
        status = "degraded"
        reasons.append("fail_open_enabled")

    return {
        "status": status,
        "requested_mode": requested_mode,
        "effective_mode": effective_mode,
        "failure_mode": failure_mode,
        "distributed_safe": effective_mode == "redis",
        "reasons": reasons,
    }


def _auth_store_register_nonce(nonce: str, ttl_sec: float) -> bool:
    """Register nonce with explicit fail-open/fail-closed fallback policy."""
    try:
        return _get_effective_auth_store().register_nonce(nonce=nonce, ttl_sec=ttl_sec)
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
        return _get_effective_auth_store().increment_auth_failure(
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
        return _get_effective_auth_store().increment_rate_limit(
            api_key=api_key,
            limit=limit,
            window_sec=window_sec,
        )
    except Exception as exc:
        mode = _auth_store_failure_mode()
        logger.warning("Auth rate-limit store error (%s), mode=%s", _errstr(exc), mode)
        _record_auth_reject_reason("auth_store_rate_limit_error")
        return mode == "closed"


# ==============================
# API Key resolution
# ==============================

# ★ 後方互換: テストがmonkeypatch.setattr(server, "API_KEY_DEFAULT", ...)を使用
API_KEY_DEFAULT = ""

api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

# 起動時に一度だけ警告を出力
if not os.getenv("VERITAS_API_KEY"):
    logger.warning("VERITAS_API_KEY 未設定（テストでは 500 を返す契約）")


def _resolve_expected_api_key_with_source() -> tuple[str, str]:
    """Resolve API key value and source name without exposing secrets."""
    env_key = (os.getenv("VERITAS_API_KEY") or "").strip()
    if env_key:
        return env_key, "env"

    # Check server module first (tests monkeypatch server.API_KEY_DEFAULT)
    try:
        from veritas_os.api import server as srv
        srv_default = getattr(srv, "API_KEY_DEFAULT", "")
        if isinstance(srv_default, str) and srv_default.strip():
            return srv_default.strip(), "api_key_default"
    except Exception:
        pass
    default_key = API_KEY_DEFAULT.strip()
    if default_key:
        return default_key, "api_key_default"

    # Late import to avoid circular dependency
    # Check srv.cfg first (tests monkeypatch server.cfg directly),
    # then fall back to srv.get_cfg() which returns _cfg_state.obj.
    from veritas_os.api import server as srv
    cfg = getattr(srv, "cfg", None) or srv.get_cfg()
    config_key = (getattr(cfg, "api_key", "") or "").strip()
    if config_key:
        return config_key, "config"
    return "", "missing"


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


def _get_expected_api_key() -> str:
    """★ セキュリティ修正: APIキーを毎回環境変数から取得。"""
    key, source = _resolve_expected_api_key_with_source()
    _log_api_key_source_once(source)
    return key


def _resolve_client_ip(
    request: Optional[Request],
    x_forwarded_for: Any,
) -> str:
    """Resolve client IP for auth-failure throttling."""
    forwarded_raw = x_forwarded_for if isinstance(x_forwarded_for, str) else ""
    forwarded = forwarded_raw.split(",", maxsplit=1)[0].strip()
    if forwarded:
        return forwarded

    if request is not None and request.client is not None and request.client.host:
        return request.client.host.strip() or "unknown"

    return "unknown"


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
    """テスト契約: サーバ側の API Key が未設定なら 500, ヘッダが無い/不一致なら 401"""
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
    """Derive a stable internal user identifier from the authenticated API key."""
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
    """Authenticate SSE requests with header-first policy."""
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
    """Return True only when dual opt-in flags enable SSE query auth."""
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
    """Authenticate WebSocket API key with header-first policy."""
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
    """Return True only when dual opt-in flags allow WebSocket query auth."""
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
_NONCE_MAX_LENGTH = _env_int_safe("VERITAS_NONCE_MAX_LENGTH", 256)

# 後方互換: テストが monkeypatch.setattr(server, "API_SECRET", ...) を使用
API_SECRET: bytes = b""
_DEFAULT_API_SECRET_PLACEHOLDER = "YOUR_VERITAS_API_SECRET_HERE"


def _is_placeholder_secret(secret: str) -> bool:
    """Return True when the secret matches the default placeholder string."""
    return secret.strip() == _DEFAULT_API_SECRET_PLACEHOLDER


def _get_api_secret() -> bytes:
    """★ セキュリティ修正: APIシークレットを毎回環境変数から取得。"""
    global API_SECRET
    # Check server module first (tests monkeypatch server.API_SECRET)
    try:
        from veritas_os.api import server as srv
        srv_secret = getattr(srv, "API_SECRET", b"")
        if srv_secret:
            return srv_secret
    except Exception:
        pass
    if API_SECRET:
        return API_SECRET
    env_secret = (os.getenv("VERITAS_API_SECRET") or "").strip()
    if not env_secret or _is_placeholder_secret(env_secret):
        if env_secret and _is_placeholder_secret(env_secret):
            logger.warning(
                "VERITAS_API_SECRET is set to the placeholder value. "
                "HMAC authentication is DISABLED. Set a secure secret in production!"
            )
        return b""
    if len(env_secret) < 32:
        logger.warning(
            "VERITAS_API_SECRET is shorter than 32 characters. "
            "Consider using a longer, more secure secret."
        )
    return env_secret.encode("utf-8")


def _check_and_register_nonce(nonce: str) -> bool:
    """Check and register a nonce for replay attack prevention."""
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
    """HMAC 認証を使う場合のみ dependencies に入れて使う想定。"""
    api_secret = _get_api_secret()
    if not api_secret:
        raise HTTPException(status_code=500, detail="Server secret missing")

    def _header_or_none(value: Any) -> Optional[str]:
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


def _check_multiworker_auth_store() -> None:
    """Warn when in-memory auth store is used in a multi-worker environment."""
    if isinstance(_get_effective_auth_store(), RedisAuthSecurityStore):
        return

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
