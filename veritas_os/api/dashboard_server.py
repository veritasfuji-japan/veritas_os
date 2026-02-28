#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERITAS Dashboard Server - 認証機能付き完全版

HTTP Basic 認証によりダッシュボードと API を保護します。

環境変数:
    DASHBOARD_USERNAME: ダッシュボードのユーザー名（デフォルト: veritas）
    DASHBOARD_PASSWORD: ダッシュボードのパスワード（デフォルト: change_me_in_production）
    VERITAS_LOG_DIR: ログディレクトリのパス

Usage (直叩き):
    export DASHBOARD_USERNAME="your_username"
    export DASHBOARD_PASSWORD="your_secure_password"
    python dashboard_server.py

Usage (モジュールとして):
    python -m veritas_os.api.dashboard_server
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from veritas_os.api.constants import MAX_LOG_FILE_SIZE, SENSITIVE_SYSTEM_PATHS

logger = logging.getLogger(__name__)

app = FastAPI(title="VERITAS Dashboard", version="1.0.0")
security = HTTPBasic()

# ===== 認証設定 =====


def _resolve_dashboard_username() -> str:
    """Resolve dashboard username while rejecting blank values.

    Security note:
        Empty usernames make brute-force and misconfiguration detection harder,
        so blank values are normalized to a safe default with a warning.
    """
    username = os.getenv("DASHBOARD_USERNAME", "veritas").strip()
    if username:
        return username

    logger.warning(
        "DASHBOARD_USERNAME is blank; falling back to default 'veritas'."
    )
    return "veritas"


def _is_truthy_env(value: str) -> bool:
    """Return True when ``value`` is a truthy environment-style flag."""
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _validate_explicit_dashboard_password(password: str) -> str:
    """Validate explicit dashboard password and emit security warnings.

    Security policy:
        - Control characters are rejected to prevent malformed Basic-Auth
          headers and reduce log/header injection risk.
        - Short passwords are accepted for backward compatibility but a
          warning is emitted because weak credentials increase brute-force risk.
    """
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in password):
        raise RuntimeError(
            "DASHBOARD_PASSWORD contains control characters and is rejected."
        )

    if len(password) < 12:
        logger.warning(
            "DASHBOARD_PASSWORD is shorter than 12 characters. "
            "This increases brute-force risk in production."
        )

    return password


def _resolve_dashboard_password() -> tuple[str, bool]:
    """Resolve dashboard password with production-safe defaults.

    Returns:
        tuple[str, bool]:
            - password string.
            - True when password is auto-generated for this process.

    Raises:
        RuntimeError: When running in production without explicit password.
    """
    env_password = os.getenv("DASHBOARD_PASSWORD", "").strip()
    if env_password:
        return _validate_explicit_dashboard_password(env_password), False

    veritas_env = os.getenv("VERITAS_ENV", "").strip().lower()
    is_production = veritas_env in {"prod", "production"}
    allow_ephemeral = _is_truthy_env(
        os.getenv("VERITAS_ALLOW_EPHEMERAL_DASHBOARD_PASSWORD", "")
    )

    if is_production and not allow_ephemeral:
        raise RuntimeError(
            "DASHBOARD_PASSWORD is required in production "
            "(set VERITAS_ALLOW_EPHEMERAL_DASHBOARD_PASSWORD=1 to override)."
        )

    logger.warning(
        "DASHBOARD_PASSWORD is not set; using a shared ephemeral "
        "auto-generated password."
    )
    return _load_or_create_shared_ephemeral_password(), True


def _get_ephemeral_password_file_path() -> Path:
    """Return file path used to share ephemeral dashboard password.

    Security note:
        The file is process-external state that makes auto-generated
        credentials deterministic across multi-worker deployments.
    """
    configured_path = os.getenv("DASHBOARD_EPHEMERAL_PASSWORD_FILE", "").strip()
    if configured_path:
        return Path(configured_path)
    return Path(tempfile.gettempdir()) / "veritas_dashboard_ephemeral_password"


def _load_or_create_shared_ephemeral_password() -> str:
    """Load or atomically create a shared ephemeral password.

    This prevents per-worker random password divergence when several server
    workers start simultaneously.
    """
    password_file = _get_ephemeral_password_file_path()
    password_file.parent.mkdir(parents=True, exist_ok=True)

    if password_file.exists():
        existing_password = password_file.read_text(encoding="utf-8").strip()
        if existing_password:
            return existing_password

    generated_password = secrets.token_urlsafe(24)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL

    try:
        fd = os.open(str(password_file), flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as password_handle:
            password_handle.write(generated_password)
        return generated_password
    except FileExistsError:
        raced_password = password_file.read_text(encoding="utf-8").strip()
        if raced_password:
            return raced_password
    except OSError as exc:
        logger.warning(
            "Failed to persist shared ephemeral dashboard password at %s: %s. "
            "Falling back to process-local password.",
            password_file,
            exc,
        )

    return generated_password


DASHBOARD_PASSWORD, _password_auto_generated = _resolve_dashboard_password()
DASHBOARD_USERNAME = _resolve_dashboard_username()


def _warn_if_ephemeral_password_with_multi_workers(
    is_auto_generated: bool,
) -> None:
    """Warn when ephemeral dashboard password is used with multiple workers.

    Security/operations note:
        Process-local random passwords make authentication non-deterministic in
        multi-worker deployments (e.g. ``uvicorn --workers 4``). Each worker
        may have a different password, causing intermittent authentication
        failures.
    """
    if not is_auto_generated:
        return

    worker_candidates = (
        os.getenv("UVICORN_WORKERS", ""),
        os.getenv("WEB_CONCURRENCY", ""),
    )
    for raw_workers in worker_candidates:
        try:
            workers = int(raw_workers.strip())
        except (ValueError, TypeError):
            continue
        if workers > 1:
            logger.warning(
                "Ephemeral DASHBOARD_PASSWORD with workers=%s may cause "
                "intermittent authentication failures. Configure an explicit "
                "DASHBOARD_PASSWORD for multi-worker deployments.",
                workers,
            )
            return


_warn_if_ephemeral_password_with_multi_workers(_password_auto_generated)


def _get_failed_auth_policy() -> tuple[int, int]:
    """Return failed-auth throttling policy.

    Returns:
        tuple[int, int]:
            - max failures allowed within a window.
            - lockout window in seconds.

    Security note:
        Invalid values are ignored with warnings to keep startup resilient and
        avoid accidental DoS from misconfiguration.
    """
    raw_max_failures = os.getenv("DASHBOARD_AUTH_MAX_FAILURES", "5").strip()
    raw_window_seconds = os.getenv("DASHBOARD_AUTH_WINDOW_SECONDS", "300").strip()

    max_failures = 5
    window_seconds = 300

    try:
        parsed_failures = int(raw_max_failures)
        if parsed_failures >= 1:
            max_failures = parsed_failures
        else:
            raise ValueError
    except (TypeError, ValueError):
        logger.warning(
            "Invalid DASHBOARD_AUTH_MAX_FAILURES=%r; using default %s.",
            raw_max_failures,
            max_failures,
        )

    try:
        parsed_window = int(raw_window_seconds)
        if parsed_window >= 1:
            window_seconds = parsed_window
        else:
            raise ValueError
    except (TypeError, ValueError):
        logger.warning(
            "Invalid DASHBOARD_AUTH_WINDOW_SECONDS=%r; using default %s.",
            raw_window_seconds,
            window_seconds,
        )

    return max_failures, window_seconds


def _get_failed_auth_tracking_capacity() -> int:
    """Return max number of tracked failed-auth identifiers.

    Security note:
        Failed-auth tracking keyed by ``client:username`` can be abused with
        many unique usernames to grow memory usage. A bounded capacity keeps
        lockout controls effective while reducing memory-exhaustion risk.
    """
    raw_capacity = os.getenv("DASHBOARD_AUTH_MAX_TRACKED_IDENTIFIERS", "10000")
    raw_capacity = raw_capacity.strip()
    default_capacity = 10_000
    min_capacity = 100
    max_capacity = 100_000

    try:
        parsed = int(raw_capacity)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid DASHBOARD_AUTH_MAX_TRACKED_IDENTIFIERS=%r; using default %s.",
            raw_capacity,
            default_capacity,
        )
        return default_capacity

    if parsed < min_capacity or parsed > max_capacity:
        logger.warning(
            "DASHBOARD_AUTH_MAX_TRACKED_IDENTIFIERS=%r is outside [%s, %s]; "
            "using default %s.",
            raw_capacity,
            min_capacity,
            max_capacity,
            default_capacity,
        )
        return default_capacity
    return parsed


_FAILED_AUTH_MAX_FAILURES, _FAILED_AUTH_WINDOW_SECONDS = _get_failed_auth_policy()
_FAILED_AUTH_MAX_TRACKED_IDENTIFIERS = _get_failed_auth_tracking_capacity()
_FAILED_AUTH_ATTEMPTS: dict[str, list[float]] = {}
_FAILED_AUTH_LOCK = threading.Lock()


def _collect_recent_failures(
    now: float,
    failure_timestamps: list[float],
    window_seconds: int,
) -> list[float]:
    """Return failure timestamps still inside the throttling window."""
    lower_bound = now - window_seconds
    return [timestamp for timestamp in failure_timestamps if timestamp >= lower_bound]


def _is_dashboard_auth_locked(identifier: str, now: float | None = None) -> bool:
    """Return ``True`` when failed auth attempts exceed the lock threshold."""
    current_time = now if now is not None else time.time()
    with _FAILED_AUTH_LOCK:
        history = _FAILED_AUTH_ATTEMPTS.get(identifier, [])
        recent = _collect_recent_failures(
            now=current_time,
            failure_timestamps=history,
            window_seconds=_FAILED_AUTH_WINDOW_SECONDS,
        )
        if recent:
            _FAILED_AUTH_ATTEMPTS[identifier] = recent
        else:
            _FAILED_AUTH_ATTEMPTS.pop(identifier, None)
        return len(recent) >= _FAILED_AUTH_MAX_FAILURES


def _record_failed_dashboard_auth(identifier: str, now: float | None = None) -> None:
    """Store a failed dashboard authentication attempt for throttling."""
    current_time = now if now is not None else time.time()
    with _FAILED_AUTH_LOCK:
        stale_keys = [
            key
            for key, timestamps in _FAILED_AUTH_ATTEMPTS.items()
            if not _collect_recent_failures(
                now=current_time,
                failure_timestamps=timestamps,
                window_seconds=_FAILED_AUTH_WINDOW_SECONDS,
            )
        ]
        for stale_key in stale_keys:
            _FAILED_AUTH_ATTEMPTS.pop(stale_key, None)

        while len(_FAILED_AUTH_ATTEMPTS) >= _FAILED_AUTH_MAX_TRACKED_IDENTIFIERS:
            oldest_key = min(
                _FAILED_AUTH_ATTEMPTS,
                key=lambda key: _FAILED_AUTH_ATTEMPTS[key][-1],
            )
            _FAILED_AUTH_ATTEMPTS.pop(oldest_key, None)

        history = _FAILED_AUTH_ATTEMPTS.get(identifier, [])
        recent = _collect_recent_failures(
            now=current_time,
            failure_timestamps=history,
            window_seconds=_FAILED_AUTH_WINDOW_SECONDS,
        )
        recent.append(current_time)
        _FAILED_AUTH_ATTEMPTS[identifier] = recent


def _clear_failed_dashboard_auth(identifier: str) -> None:
    """Clear failed-auth tracking for ``identifier`` after successful login."""
    with _FAILED_AUTH_LOCK:
        _FAILED_AUTH_ATTEMPTS.pop(identifier, None)


def _get_request_client_host(request: Request) -> str:
    """Return a stable client host string for auth throttling keys.

    When running behind some reverse proxies or in certain test scopes,
    ``request.client`` may be ``None``. In that case, this function attempts a
    conservative fallback using ``X-Forwarded-For`` and otherwise returns
    ``"unknown"``.
    """
    if request.client and request.client.host:
        return request.client.host

    forwarded_for = request.headers.get("x-forwarded-for", "")
    forwarded_host = forwarded_for.split(",", maxsplit=1)[0].strip()
    if forwarded_host:
        return forwarded_host

    return "unknown"


def verify_credentials(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(security),  # noqa: B008
) -> str:
    """
    Verify HTTP Basic Auth credentials.

    Args:
        credentials: HTTP Basic Auth credentials

    Returns:
        Username if authenticated

    Raises:
        HTTPException: If authentication fails
    """
    client_host = _get_request_client_host(request)
    throttle_key = f"{client_host}:{credentials.username}"

    if _is_dashboard_auth_locked(throttle_key):
        logger.warning(
            "Dashboard auth temporarily locked due to repeated failures "
            "(client=%s username=%s).",
            client_host,
            credentials.username,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication failures. Try again later.",
            headers={"Retry-After": str(_FAILED_AUTH_WINDOW_SECONDS)},
        )

    correct_username = secrets.compare_digest(
        credentials.username, DASHBOARD_USERNAME
    )
    correct_password = secrets.compare_digest(
        credentials.password, DASHBOARD_PASSWORD
    )

    if not (correct_username and correct_password):
        _record_failed_dashboard_auth(throttle_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

    _clear_failed_dashboard_auth(throttle_key)
    return credentials.username


# ===== パス設定 =====

BASE_DIR = Path(__file__).resolve().parents[1]
default_log_dir = BASE_DIR / "scripts" / "logs"


def _is_sensitive_path(path: Path) -> bool:
    """Return True when ``path`` points to a known sensitive system location."""
    for sensitive in SENSITIVE_SYSTEM_PATHS:
        try:
            sensitive_path = Path(sensitive).expanduser().resolve()
            if path == sensitive_path or sensitive_path in path.parents:
                return True
        except (OSError, ValueError):
            continue
    return False


def _validate_log_dir(log_dir_str: str, allowed_base: Path) -> Path:
    """Validate log directory path against traversal and sensitive locations."""
    try:
        resolved = Path(log_dir_str).expanduser().resolve()
        allowed_resolved = allowed_base.resolve()

        if _is_sensitive_path(resolved):
            logger.warning(
                "VERITAS_LOG_DIR '%s' points to sensitive path, using default",
                resolved,
            )
            return allowed_base

        if resolved == allowed_resolved:
            return resolved

        if allowed_resolved in resolved.parents:
            return resolved

        logger.warning(
            "VERITAS_LOG_DIR '%s' is outside allowed base '%s', using default",
            resolved,
            allowed_resolved,
        )
        return allowed_base

    except (OSError, ValueError) as error:
        logger.warning("Invalid VERITAS_LOG_DIR, using default: %s", error)
        return allowed_base


_log_dir_env = os.getenv("VERITAS_LOG_DIR", str(default_log_dir))
LOG_DIR = _validate_log_dir(_log_dir_env, default_log_dir)
LOG_DIR.mkdir(parents=True, exist_ok=True)

REPORT_HTML = LOG_DIR / "doctor_dashboard.html"
STATUS_JSON = LOG_DIR / "drive_sync_status.json"


# ===== HTMLダッシュボード（認証必須） =====

@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(username: str = Depends(verify_credentials)) -> HTMLResponse:
    """
    Display VERITAS dashboard with Google Drive sync status.
    Requires HTTP Basic authentication.
    """
    html = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VERITAS Dashboard</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 100%);
  color: #e0e0e0;
  padding: 24px;
  min-height: 100vh;
}
.container { max-width: 1200px; margin: 0 auto; }
h1 {
  font-size: 2.5rem;
  margin-bottom: 8px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.subtitle { color: #999; margin-bottom: 32px; }
.card {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 24px;
  backdrop-filter: blur(10px);
}
.badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 0.875rem;
  font-weight: 600;
}
.badge.ok { background: #14532d; color: #d1fae5; }
.badge.ng { background: #7f1d1d; color: #fee2e2; }
.info-row { margin: 12px 0; display: flex; align-items: center; }
.info-label {
  min-width: 180px;
  color: #999;
  font-weight: 500;
}
.info-value {
  font-family: 'Monaco', 'Courier New', monospace;
  background: rgba(0, 0, 0, 0.3);
  padding: 4px 8px;
  border-radius: 4px;
}
.loading {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 3px solid rgba(255, 255, 255, 0.1);
  border-top-color: #667eea;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
footer {
  text-align: center;
  color: #666;
  margin-top: 48px;
  font-size: 0.875rem;
}
a.button-link {
  padding: 8px 16px;
  border-radius: 8px;
  text-decoration: none;
  display: inline-block;
  transition: all 0.2s;
}
a.button-link:hover {
  filter: brightness(1.1);
}
</style>
</head>
<body>
<div class="container">
  <h1>🧠 VERITAS Dashboard</h1>
  <div class="subtitle">Real-time monitoring &amp; system status</div>

  <div id="sync" class="card">
    <div class="loading"></div> Loading...
  </div>

  <div class="card">
    <h3 style="margin-bottom: 16px;">📄 Quick Links</h3>
    <div style="display: flex; gap: 12px; flex-wrap: wrap;">
      <a href="/download/report"
         class="button-link"
         style="background: rgba(102, 126, 234, 0.2); border: 1px solid #667eea; color: #667eea;">
        📥 Download Report
      </a>
      <a href="/api/status"
         target="_blank"
         class="button-link"
         style="background: rgba(118, 75, 162, 0.2); border: 1px solid #764ba2; color: #764ba2;">
        🔗 API Status
      </a>
    </div>
  </div>

  <footer>
    VERITAS OS v2.0 | Authenticated Session: <span id="user"></span>
  </footer>
</div>

<script>
async function loadStatus() {
  try {
    const response = await fetch('/api/status');
    if (response.status === 401) {
      document.getElementById('sync').innerHTML =
        '<h3>🔒 Authentication Required</h3><p>Please refresh and enter credentials.</p>';
      return;
    }

    if (!response.ok) {
      throw new Error('HTTP ' + response.status);
    }

    const data = await response.json();
    // XSS防止: テキストコンテンツはDOM APIで安全に挿入
    var escEl = document.createElement('div');
    function esc(s) { escEl.textContent = s; return escEl.innerHTML; }
    const statusBadge = data.ok
      ? '<span class="badge ok">✅ OK</span>'
      : '<span class="badge ng">❌ FAILED</span>';

    document.getElementById('sync').innerHTML =
      '<h3 style="margin-bottom: 16px;">☁️ Google Drive Sync Status ' + statusBadge + '</h3>' +
      '<div class="info-row">' +
        '<span class="info-label">Last Run (UTC):</span>' +
        '<span class="info-value">' + esc(data.ended_at_utc || 'N/A') + '</span>' +
      '</div>' +
      '<div class="info-row">' +
        '<span class="info-label">Duration:</span>' +
        '<span class="info-value">' + esc(String(data.duration_sec != null ? data.duration_sec : 0)) + 's</span>' +
      '</div>' +
      '<div class="info-row">' +
        '<span class="info-label">Destination:</span>' +
        '<span class="info-value">' + esc(data.dst || 'N/A') + '</span>' +
      '</div>' +
      '<div class="info-row">' +
        '<span class="info-label">Transferred Files:</span>' +
        '<span class="info-value">' + esc(String(data.transferred_files != null ? data.transferred_files : 0)) + '</span>' +
      '</div>';
  } catch (error) {
    console.error('Error loading status:', error);
    document.getElementById('sync').innerHTML =
      '<h3>⚠️ Status Unavailable</h3><p>Could not load sync status. Check if drive_sync_status.json exists.</p>';
  }
}

// Initial load
loadStatus();

// Auto-refresh every 10 seconds
setInterval(loadStatus, 10000);

// Display username (injected from server)
document.getElementById('user').textContent = '{{USERNAME}}';
</script>
</body>
</html>
"""
    # username を埋め込む（CSS/JS の { } を壊さないために単純置換）
    # XSS対策: JS 文字列コンテキスト向けに json.dumps でエスケープ
    html = html.replace("'{{USERNAME}}'", json.dumps(username))
    return HTMLResponse(html)


# ===== Drive Sync ステータス API（認証必須） =====

@app.get("/api/status", response_class=JSONResponse)
async def get_status(username: str = Depends(verify_credentials)) -> JSONResponse:
    """
    Get Google Drive sync status.
    Requires HTTP Basic authentication.

    Returns:
        JSON object with sync status
    """
    if STATUS_JSON.exists():
        try:
            if STATUS_JSON.stat().st_size > MAX_LOG_FILE_SIZE:
                return JSONResponse(
                    {"error": "status file too large"},
                    status_code=500,
                )
            data = json.loads(STATUS_JSON.read_text(encoding="utf-8"))
            # data はそのまま返す（ok, ended_at_utc, duration_sec などを想定）
            return JSONResponse(data)
        except json.JSONDecodeError:
            return JSONResponse(
                {"error": "invalid JSON"},
                status_code=500,
            )
    else:
        return JSONResponse(
            {"error": "status file not found"},
            status_code=404,
        )


# ===== HTMLレポートをダウンロード（認証必須） =====

@app.get("/download/report", response_class=FileResponse)
async def download_report(username: str = Depends(verify_credentials)):
    """
    Download the latest HTML report.
    Requires HTTP Basic authentication.
    """
    if REPORT_HTML.exists():
        return FileResponse(
            REPORT_HTML,
            filename="doctor_dashboard.html",
            media_type="text/html",
        )
    return JSONResponse(
        {"error": "report not found"},
        status_code=404,
    )


# ===== Health Check（認証不要） =====

@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint (no authentication required)."""
    return {"status": "ok", "service": "VERITAS Dashboard"}


if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("🔐 VERITAS Dashboard Server (Authenticated)")
    print("=" * 60)
    print(f"   Username: {DASHBOARD_USERNAME}")
    if _password_auto_generated:
        # ★ セキュリティ修正: 自動生成パスワードを stdout に出力しない
        # パスワードの具体的な値はログにも出力しない
        # NOTE: ログファイルのパーミッションが適切に制限されていることを確認してください
        print("   Password: (auto-generated, not shown)")
        print("   Set DASHBOARD_PASSWORD env var for persistent access.")
    else:
        print(f"   Password: {'*' * len(DASHBOARD_PASSWORD)}")
    print(f"   Log Directory: {LOG_DIR}")
    print("=" * 60)
    print("   Access: http://localhost:8000")
    print("   API:    http://localhost:8000/api/status")
    print("=" * 60)

    uvicorn.run(app, host=os.getenv("DASHBOARD_HOST", "127.0.0.1"), port=8000)
