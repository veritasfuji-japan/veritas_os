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

import html as html_mod
import json
import logging
import os
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

logger = logging.getLogger(__name__)

app = FastAPI(title="VERITAS Dashboard", version="1.0.0")
security = HTTPBasic()

# ===== 認証設定 =====

DASHBOARD_USERNAME = os.getenv("DASHBOARD_USERNAME", "veritas")
_env_password = os.getenv("DASHBOARD_PASSWORD", "")
_password_auto_generated = False
if not _env_password:
    _env_password = secrets.token_urlsafe(24)
    _password_auto_generated = True
DASHBOARD_PASSWORD = _env_password


def verify_credentials(
    credentials: HTTPBasicCredentials = Depends(security),
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
    correct_username = secrets.compare_digest(
        credentials.username, DASHBOARD_USERNAME
    )
    correct_password = secrets.compare_digest(
        credentials.password, DASHBOARD_PASSWORD
    )

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# ===== パス設定 =====

from veritas_os.api.constants import MAX_LOG_FILE_SIZE, SENSITIVE_SYSTEM_PATHS

BASE_DIR = Path(__file__).resolve().parents[1]
default_log_dir = BASE_DIR / "scripts" / "logs"


def _validate_log_dir(log_dir_str: str, allowed_base: Path) -> Path:
    """
    Validate and sanitize the log directory path to prevent path traversal.

    Only allows paths that are under the allowed_base directory.
    This prevents path traversal attacks that could expose sensitive system files.

    Args:
        log_dir_str: String path from environment variable
        allowed_base: The allowed base directory for logs

    Returns:
        Validated Path object (always under allowed_base)

    Note:
        Falls back to allowed_base if the path is invalid or outside allowed_base.
    """
    try:
        resolved = Path(log_dir_str).expanduser().resolve()
        allowed_resolved = allowed_base.resolve()

        # Allow exact match with allowed_base
        if resolved == allowed_resolved:
            return resolved

        # Allow child paths of allowed_base (resolved path must have allowed_base as parent)
        # Check if allowed_resolved is a parent of resolved
        if allowed_resolved in resolved.parents:
            return resolved

        # Reject all paths outside allowed_base - this is the security fix
        # Previously, arbitrary paths were allowed if not in SENSITIVE_SYSTEM_PATHS
        logger.warning(
            "VERITAS_LOG_DIR '%s' is outside allowed base '%s', using default",
            resolved,
            allowed_resolved,
        )
        return allowed_base

    except (OSError, ValueError) as e:
        # Fall back to default on any path resolution error
        logger.warning("Invalid VERITAS_LOG_DIR, using default: %s", e)
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
    function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
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
    # XSS対策: ユーザー名をHTMLエスケープ
    html = html.replace("{{USERNAME}}", html_mod.escape(username))
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
