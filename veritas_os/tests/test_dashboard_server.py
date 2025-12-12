# veritas_os/tests/test_dashboard_server.py
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veritas_os.api import dashboard_server


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
    # path フィールドに STATUS_JSON のパス文字列が入っていること
    assert body.get("path") == str(dashboard_server.STATUS_JSON)


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
    assert "detail" in body


# =====================================================================
# /download/report （Doctor HTML レポート）
# =====================================================================

def test_download_report_not_found(client: TestClient):
    # REPORT_HTML が存在しない場合は 404 JSON
    res = client.get("/download/report", auth=("testuser", "testpass"))
    assert res.status_code == 404
    body = res.json()
    assert body.get("error") == "report not found"
    assert body.get("path") == str(dashboard_server.REPORT_HTML)


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

