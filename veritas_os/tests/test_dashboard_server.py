# veritas_os/tests/test_dashboard_server.py
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veritas_os.api import dashboard_server


# =====================================================================
# _validate_log_dir のテスト（パストラバーサル対策）
# =====================================================================


def test_validate_log_dir_allows_exact_base(tmp_path):
    """allowed_base と完全一致するパスは許可される。"""
    result = dashboard_server._validate_log_dir(str(tmp_path), tmp_path)
    assert result == tmp_path


def test_validate_log_dir_allows_child_path(tmp_path):
    """allowed_base の子ディレクトリは許可される。"""
    child = tmp_path / "subdir"
    result = dashboard_server._validate_log_dir(str(child), tmp_path)
    assert result == child


def test_validate_log_dir_rejects_outside_path(tmp_path):
    """allowed_base 外のパスは拒否され、デフォルトが返される。"""
    outside_path = "/tmp/outside_dir"
    result = dashboard_server._validate_log_dir(outside_path, tmp_path)
    # 外部パスは拒否されて allowed_base が返される
    assert result == tmp_path


def test_validate_log_dir_rejects_sensitive_paths(tmp_path):
    """センシティブなシステムパス（/root, ~/.ssh等）は拒否される。"""
    for sensitive in ["/root", "/etc/passwd", "/home/user/.ssh"]:
        result = dashboard_server._validate_log_dir(sensitive, tmp_path)
        assert result == tmp_path


def test_validate_log_dir_rejects_sensitive_paths_even_with_root_base(tmp_path):
    """allowed_base が広すぎる設定でもセンシティブパスは拒否される。"""
    result = dashboard_server._validate_log_dir("/etc", Path("/"))
    assert result == Path("/")


def test_validate_log_dir_handles_path_traversal_attempt(tmp_path):
    """'../' を使ったパストラバーサル攻撃は拒否される。"""
    traversal_path = str(tmp_path / ".." / ".." / "etc")
    result = dashboard_server._validate_log_dir(traversal_path, tmp_path)
    # 解決後のパスが allowed_base 外になるので拒否
    assert result == tmp_path


@pytest.fixture
def client(monkeypatch, tmp_path) -> TestClient:
    """
    認証情報とステータス/レポートパスをテスト用に差し替えた TestClient を返す。
    """
    # Basic 認証ユーザーをテスト用に固定
    monkeypatch.setattr(dashboard_server, "DASHBOARD_USERNAME", "testuser")
    monkeypatch.setattr(dashboard_server, "DASHBOARD_PASSWORD", "testpass")

    # ログ系のパスを一時ディレクトリに退避
    status_path: Path = tmp_path / "drive_sync_status.json"
    report_path: Path = tmp_path / "doctor_dashboard.html"

    monkeypatch.setattr(dashboard_server, "STATUS_JSON", status_path)
    monkeypatch.setattr(dashboard_server, "REPORT_HTML", report_path)

    return TestClient(dashboard_server.app)


# =====================================================================
# /health （認証不要）
# =====================================================================





def test_resolve_dashboard_username_uses_default_when_blank(monkeypatch):
    """Blank dashboard username should fall back to secure default."""
    monkeypatch.setenv("DASHBOARD_USERNAME", "   ")

    username = dashboard_server._resolve_dashboard_username()

    assert username == "veritas"


def test_resolve_dashboard_username_uses_explicit_value(monkeypatch):
    """Configured dashboard username should be used as-is."""
    monkeypatch.setenv("DASHBOARD_USERNAME", "ops-admin")

    username = dashboard_server._resolve_dashboard_username()

    assert username == "ops-admin"


def test_validate_explicit_dashboard_password_rejects_control_chars():
    """Control characters in password should be rejected for safety."""
    with pytest.raises(RuntimeError, match="control characters"):
        dashboard_server._validate_explicit_dashboard_password("bad\nsecret")


def test_validate_explicit_dashboard_password_warns_when_too_short(caplog):
    """Short explicit password should be accepted with security warning."""
    caplog.set_level("WARNING")

    password = dashboard_server._validate_explicit_dashboard_password("shortpwd")

    assert password == "shortpwd"
    assert "shorter than 12 characters" in caplog.text


def test_resolve_dashboard_password_requires_explicit_value_in_production(monkeypatch):
    """Production mode should fail fast without explicit dashboard password."""
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.delenv("VERITAS_ALLOW_EPHEMERAL_DASHBOARD_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="DASHBOARD_PASSWORD is required"):
        dashboard_server._resolve_dashboard_password()


def test_resolve_dashboard_password_allows_ephemeral_override(monkeypatch):
    """Ephemeral password may be enabled explicitly for exceptional operations."""
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.setenv("VERITAS_ALLOW_EPHEMERAL_DASHBOARD_PASSWORD", "1")

    password, auto_generated = dashboard_server._resolve_dashboard_password()

    assert isinstance(password, str)
    assert len(password) > 10
    assert auto_generated is True


def test_resolve_dashboard_password_uses_explicit_value(monkeypatch):
    """Explicit password should always take precedence over generated values."""
    monkeypatch.setenv("DASHBOARD_PASSWORD", "configured-secret")
    monkeypatch.setenv("VERITAS_ENV", "production")

    password, auto_generated = dashboard_server._resolve_dashboard_password()

    assert password == "configured-secret"
    assert auto_generated is False



def test_warn_if_ephemeral_password_with_multi_workers_logs_warning(
    monkeypatch, caplog
):
    """Auto-generated password + multi-worker env should emit warning."""
    monkeypatch.setenv("UVICORN_WORKERS", "3")
    caplog.set_level("WARNING")

    dashboard_server._warn_if_ephemeral_password_with_multi_workers(True)

    assert "intermittent authentication failures" in caplog.text


def test_warn_if_ephemeral_password_with_single_worker_no_warning(
    monkeypatch, caplog
):
    """Single-worker deployment should not emit multi-worker warning."""
    monkeypatch.setenv("UVICORN_WORKERS", "1")
    caplog.set_level("WARNING")

    dashboard_server._warn_if_ephemeral_password_with_multi_workers(True)

    assert "intermittent authentication failures" not in caplog.text


def test_failed_auth_policy_uses_defaults_when_invalid(monkeypatch, caplog):
    """Invalid policy env vars should fall back to safe defaults."""
    monkeypatch.setenv("DASHBOARD_AUTH_MAX_FAILURES", "zero")
    monkeypatch.setenv("DASHBOARD_AUTH_WINDOW_SECONDS", "")
    caplog.set_level("WARNING")

    max_failures, window_seconds = dashboard_server._get_failed_auth_policy()

    assert max_failures == 5
    assert window_seconds == 300
    assert "Invalid DASHBOARD_AUTH_MAX_FAILURES" in caplog.text
    assert "Invalid DASHBOARD_AUTH_WINDOW_SECONDS" in caplog.text


def test_failed_auth_tracking_capacity_uses_default_when_invalid(monkeypatch, caplog):
    """Invalid tracking capacity should fall back to secure default."""
    monkeypatch.setenv("DASHBOARD_AUTH_MAX_TRACKED_IDENTIFIERS", "invalid")
    caplog.set_level("WARNING")

    capacity = dashboard_server._get_failed_auth_tracking_capacity()

    assert capacity == 10_000
    assert "Invalid DASHBOARD_AUTH_MAX_TRACKED_IDENTIFIERS" in caplog.text


def test_failed_auth_tracking_capacity_uses_default_when_out_of_bounds(
    monkeypatch, caplog
):
    """Out-of-range capacity should be rejected to avoid bad configurations."""
    monkeypatch.setenv("DASHBOARD_AUTH_MAX_TRACKED_IDENTIFIERS", "99")
    caplog.set_level("WARNING")

    capacity = dashboard_server._get_failed_auth_tracking_capacity()

    assert capacity == 10_000
    assert "outside [100, 100000]" in caplog.text


def test_failed_auth_tracking_counts_within_window(monkeypatch):
    """Failed auth entries should expire after the configured time window."""
    monkeypatch.setattr(dashboard_server, "_FAILED_AUTH_MAX_FAILURES", 2)
    monkeypatch.setattr(dashboard_server, "_FAILED_AUTH_WINDOW_SECONDS", 10)
    monkeypatch.setattr(dashboard_server, "_FAILED_AUTH_ATTEMPTS", {})

    key = "127.0.0.1:testuser"
    dashboard_server._record_failed_dashboard_auth(key, now=100.0)
    dashboard_server._record_failed_dashboard_auth(key, now=109.0)

    assert dashboard_server._is_dashboard_auth_locked(key, now=109.5) is True
    assert dashboard_server._is_dashboard_auth_locked(key, now=111.0) is False


def test_record_failed_dashboard_auth_prunes_stale_and_limits_capacity(monkeypatch):
    """Failed-auth tracker should prune stale entries and enforce capacity cap."""
    monkeypatch.setattr(dashboard_server, "_FAILED_AUTH_WINDOW_SECONDS", 10)
    monkeypatch.setattr(dashboard_server, "_FAILED_AUTH_MAX_TRACKED_IDENTIFIERS", 2)
    monkeypatch.setattr(
        dashboard_server,
        "_FAILED_AUTH_ATTEMPTS",
        {
            "stale:user": [1.0],
            "old:user": [95.0],
            "new:user": [99.0],
        },
    )

    dashboard_server._record_failed_dashboard_auth("target:user", now=100.0)

    attempts = dashboard_server._FAILED_AUTH_ATTEMPTS
    assert "stale:user" not in attempts
    assert "old:user" not in attempts
    assert "new:user" in attempts
    assert "target:user" in attempts
    assert len(attempts) == 2


def test_verify_credentials_returns_429_after_repeated_failures(
    client: TestClient,
    monkeypatch,
):
    """Repeated failed auth attempts should trigger temporary lockout."""
    monkeypatch.setattr(dashboard_server, "_FAILED_AUTH_MAX_FAILURES", 2)
    monkeypatch.setattr(dashboard_server, "_FAILED_AUTH_WINDOW_SECONDS", 60)
    monkeypatch.setattr(dashboard_server, "_FAILED_AUTH_ATTEMPTS", {})

    first = client.get("/", auth=("testuser", "wrong-pass"))
    second = client.get("/", auth=("testuser", "wrong-pass"))
    locked = client.get("/", auth=("testuser", "wrong-pass"))

    assert first.status_code == 401
    assert second.status_code == 401
    assert locked.status_code == 429
    assert locked.headers.get("retry-after") == "60"


def test_verify_credentials_success_clears_failed_auth(client: TestClient, monkeypatch):
    """Successful login should clear lock history for the same identity."""
    monkeypatch.setattr(dashboard_server, "_FAILED_AUTH_MAX_FAILURES", 3)
    monkeypatch.setattr(dashboard_server, "_FAILED_AUTH_WINDOW_SECONDS", 60)
    monkeypatch.setattr(dashboard_server, "_FAILED_AUTH_ATTEMPTS", {})

    failed = client.get("/", auth=("testuser", "wrong-pass"))
    ok = client.get("/", auth=("testuser", "testpass"))
    failed_again = client.get("/", auth=("testuser", "wrong-pass"))

    assert failed.status_code == 401
    assert ok.status_code == 200
    assert failed_again.status_code == 401

def test_health_check_ok(client: TestClient):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body.get("status") == "ok"
    assert body.get("service") == "VERITAS Dashboard"


# =====================================================================
# "/" / "/dashboard" （認証必須）
# =====================================================================

def test_root_requires_auth(client: TestClient):
    res = client.get("/")
    assert res.status_code == 401
    # Basic 認証なので WWW-Authenticate ヘッダが返ってくるはず
    assert "basic" in res.headers.get("www-authenticate", "").lower()


def test_root_with_auth_embeds_username(client: TestClient):
    res = client.get("/", auth=("testuser", "testpass"))
    assert res.status_code == 200
    text = res.text
    # タイトルとユーザー名が HTML 内に埋め込まれていること
    assert "VERITAS Dashboard" in text
    assert "Authenticated Session" in text
    assert "testuser" in text  # {{USERNAME}} 置換が効いているかの確認


def test_dashboard_requires_auth(client: TestClient):
    res = client.get("/dashboard")
    assert res.status_code == 401
    assert "basic" in res.headers.get("www-authenticate", "").lower()


def test_dashboard_with_auth_ok(client: TestClient):
    res = client.get("/dashboard", auth=("testuser", "testpass"))
    assert res.status_code == 200
    assert "VERITAS Dashboard" in res.text


# =====================================================================
# /api/status （Drive Sync ステータス）
# =====================================================================

def test_status_requires_auth(client: TestClient):
    res = client.get("/api/status")
    assert res.status_code == 401
    assert "basic" in res.headers.get("www-authenticate", "").lower()


def test_status_not_found_when_file_missing(client: TestClient):
    # STATUS_JSON は fixture で tmp_path に差し替えてあるので、デフォルトでは存在しない
    res = client.get("/api/status", auth=("testuser", "testpass"))
    assert res.status_code == 404
    body = res.json()
    assert body.get("error") == "status file not found"
    # M-2: セキュリティ修正 - 内部パスをクライアントに露出させない
    assert "path" not in body


def test_status_ok_when_valid_json_exists(client: TestClient):
    # テスト用の status JSON を書き込む
    status_data = {
        "ok": True,
        "ended_at_utc": "2025-12-09T12:34:56Z",
        "duration_sec": 3.14,
        "dst": "gs://veritas-sync",
        "transferred_files": 42,
    }
    dashboard_server.STATUS_JSON.write_text(
        json.dumps(status_data), encoding="utf-8"
    )

    res = client.get("/api/status", auth=("testuser", "testpass"))
    assert res.status_code == 200
    body = res.json()
    # そのまま返ってくる想定
    assert body == status_data


def test_status_500_on_invalid_json(client: TestClient):
    # 壊れた JSON を書く
    dashboard_server.STATUS_JSON.write_text("{invalid json", encoding="utf-8")

    res = client.get("/api/status", auth=("testuser", "testpass"))
    assert res.status_code == 500
    body = res.json()
    assert body.get("error") == "invalid JSON"
    # JSONDecodeError の詳細はセキュリティ上クライアントに返さない
    assert "detail" not in body


# =====================================================================
# /download/report （Doctor HTML レポート）
# =====================================================================

def test_download_report_not_found(client: TestClient):
    # REPORT_HTML が存在しない場合は 404 JSON
    res = client.get("/download/report", auth=("testuser", "testpass"))
    assert res.status_code == 404
    body = res.json()
    assert body.get("error") == "report not found"
    # M-2: セキュリティ修正 - 内部パスをクライアントに露出させない
    assert "path" not in body


def test_download_report_ok(client: TestClient):
    # テスト用の HTML を書き込む
    dashboard_server.REPORT_HTML.write_text(
        "<html><body>doctor report</body></html>", encoding="utf-8"
    )

    res = client.get("/download/report", auth=("testuser", "testpass"))
    assert res.status_code == 200
    # FileResponse → text/html になっているはず
    assert "text/html" in res.headers.get("content-type", "").lower()
    assert "doctor report" in res.text
