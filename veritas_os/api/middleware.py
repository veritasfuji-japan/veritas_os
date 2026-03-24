# veritas_os/api/middleware.py
"""HTTP middleware: trace ID, response time, security headers, body size limit."""
from __future__ import annotations

import math
import os
import re
import secrets
import threading
import time
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from veritas_os.api.rate_limiting import _rate_lock, _rate_bucket, _RATE_LIMIT, _RATE_WINDOW

import logging
logger = logging.getLogger(__name__)

# When rate limiting is handled by Redis, the in-process _rate_bucket is never
# updated so X-RateLimit-* headers would be stale/misleading.  Detect once at
# import time so we can skip those headers in redis mode.
_AUTH_STORE_MODE = (os.getenv("VERITAS_AUTH_SECURITY_STORE") or "memory").strip().lower() or "memory"

# ★ C-3 継続改善: リクエストボディサイズ制限 (DoS対策)
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
    """Resolve request size limit from profile + explicit env override."""
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
    """Resolve or mint a trace id for end-to-end audit correlation."""
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


# ---------------------------------------------------------------------------
# In-flight request tracking for graceful shutdown
# ---------------------------------------------------------------------------
_inflight_count = 0
_inflight_lock = threading.Lock()
_shutting_down = False


def _inflight_snapshot() -> dict:
    """Return a thread-safe snapshot of in-flight request state."""
    with _inflight_lock:
        return {"inflight": _inflight_count, "shutting_down": _shutting_down}


# ---------------------------------------------------------------------------
# Middleware functions (to be registered on the FastAPI app by server.py)
# ---------------------------------------------------------------------------

async def attach_trace_id(request: Request, call_next):
    """Attach a validated trace id to request state and response headers."""
    trace_id = _resolve_trace_id_from_request(request)
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers[TRACE_ID_HEADER_NAME] = trace_id
    response.headers.setdefault("X-Request-Id", trace_id)
    return response


async def add_response_time(request: Request, call_next):
    """Record and expose request processing time via X-Response-Time header."""
    start = time.monotonic()
    response = await call_next(request)
    elapsed_ms = round((time.monotonic() - start) * 1000, 2)
    response.headers["X-Response-Time"] = f"{elapsed_ms}ms"
    return response


async def add_rate_limit_headers(request: Request, call_next):
    """Expose rate limit state via standard X-RateLimit-* response headers.

    When ``VERITAS_AUTH_SECURITY_STORE=redis`` the in-process ``_rate_bucket``
    is never updated, so we skip emitting headers to avoid misleading clients.
    """
    response = await call_next(request)
    if _AUTH_STORE_MODE != "memory":
        return response
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


async def track_inflight_requests(request: Request, call_next):
    """Track in-flight requests for graceful shutdown draining.

    Note: reads ``_shutting_down`` from the ``server`` module so that tests
    which set ``server._shutting_down`` directly still take effect. The lifespan
    also writes to the server module attribute.
    """
    global _inflight_count
    # Read from server module — tests set server._shutting_down directly
    from veritas_os.api import server as _srv
    shutting_down = getattr(_srv, "_shutting_down", _shutting_down)

    if shutting_down:
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


async def limit_body_size(request: Request, call_next):
    """★ C-3 修正: リクエストボディサイズ制限ミドルウェア

    Content-Length ヘッダーと実際のボディストリームの両方を制限する。
    chunked transfer encoding によるバイパスを防止する。
    """
    # Read from server module to support test monkeypatching
    from veritas_os.api import server as _srv
    effective_limit = getattr(_srv, "MAX_REQUEST_BODY_SIZE", MAX_REQUEST_BODY_SIZE)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > effective_limit:
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Request body too large. Max size: {effective_limit} bytes"}
                )
        except (ValueError, TypeError):
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid Content-Length header"}
            )

    # ★ chunked transfer encoding 対策: ストリーミング読み取りで制限値到達時に打ち切る
    if request.method in ("POST", "PUT", "PATCH"):
        received = 0
        chunks: list[bytes] = []
        async for chunk in request.stream():
            received += len(chunk)
            if received > effective_limit:
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Request body too large. Max size: {effective_limit} bytes"}
                )
            chunks.append(chunk)
        # Store the fully read body so downstream can access it via request.body()
        request._body = b"".join(chunks)

    return await call_next(request)


async def add_security_headers(request: Request, call_next):
    """Apply baseline response security headers for API endpoints."""
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
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    response.headers["Cache-Control"] = "no-store"
    return response
