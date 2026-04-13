# veritas_os/api/rate_limiting.py
"""Rate bucket, nonce replay prevention, and scheduled cleanup."""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Dict, Optional, Tuple

from fastapi import Header, HTTPException

from veritas_os.api.auth import (
    _auth_store_increment_rate_limit,
    _record_auth_reject_reason,
)

logger = logging.getLogger(__name__)


def _env_int_safe(key: str, default: int) -> int:
    raw = os.getenv(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


# ---- rate limit（簡易）----
_RATE_LIMIT = 60
_RATE_WINDOW = 60.0
_RATE_BUCKET_MAX = 5000
_rate_bucket: Dict[str, Tuple[int, float]] = {}
_rate_lock = threading.Lock()


def _cleanup_rate_bucket_unsafe() -> None:
    """内部用: ロック取得済み前提のクリーンアップ"""
    now = time.time()
    expired_keys = [k for k, (_, start) in _rate_bucket.items() if now - start > (_RATE_WINDOW * 4)]
    for k in expired_keys:
        _rate_bucket.pop(k, None)
    if len(_rate_bucket) > _RATE_BUCKET_MAX:
        overflow = len(_rate_bucket) - _RATE_BUCKET_MAX
        for k in list(_rate_bucket.keys())[:overflow]:
            _rate_bucket.pop(k, None)


def _cleanup_rate_bucket() -> None:
    """★ スレッドセーフ版: ロックを取得してクリーンアップ"""
    with _rate_lock:
        _cleanup_rate_bucket_unsafe()


def enforce_rate_limit(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")):
    """テスト契約: X-API-Key が無いなら 401"""
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


# ---- Nonce store ----
_NONCE_TTL_SEC = _env_int_safe("VERITAS_NONCE_TTL_SEC", 300)
_NONCE_MAX = _env_int_safe("VERITAS_NONCE_MAX_SIZE", 5000)
_nonce_store: Dict[str, float] = {}
_nonce_lock = threading.Lock()


def _effective_nonce_max() -> int:
    """Resolve nonce-store capacity with safe lower-bound validation.

    The configured value can come from module defaults, environment variables,
    or test/runtime overrides via ``veritas_os.api.server``. Non-positive
    values would effectively disable nonce replay protection by pruning all
    entries during cleanup, so those values are rejected.
    """
    def _sanitize_nonce_max(value: object) -> int:
        if isinstance(value, int) and value > 0:
            return value
        return _NONCE_MAX if isinstance(_NONCE_MAX, int) and _NONCE_MAX > 0 else 5000

    try:
        from veritas_os.api import server as srv
        v = getattr(srv, "_NONCE_MAX", _NONCE_MAX)
        return _sanitize_nonce_max(v)
    except Exception:
        return _sanitize_nonce_max(_NONCE_MAX)


def _cleanup_nonces_unsafe() -> None:
    """内部用: ロック取得済み前提のクリーンアップ"""
    now = time.time()
    expired_keys = [k for k, until in _nonce_store.items() if now > until]
    for k in expired_keys:
        _nonce_store.pop(k, None)
    nonce_max = _effective_nonce_max()
    if len(_nonce_store) > nonce_max:
        overflow = len(_nonce_store) - nonce_max
        for k in list(_nonce_store.keys())[:overflow]:
            _nonce_store.pop(k, None)


def _cleanup_nonces() -> None:
    """★ スレッドセーフ版: ロックを取得してクリーンアップ"""
    with _nonce_lock:
        _cleanup_nonces_unsafe()


# ---- Nonce cleanup scheduler ----
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
_rate_cleanup_timer: threading.Timer | None = None
_rate_cleanup_timer_lock = threading.Lock()
_RATE_CLEANUP_INTERVAL = 120.0


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
