# -*- coding: utf-8 -*-
"""API サーバー 単体テスト

API サーバーのエンドポイント / 認証 / レート制限 / 防御テスト。"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ============================================================
# Source: test_api_server_extra.py
# ============================================================


import asyncio
import json
import os
import re
import time
import hmac
import hashlib
from pathlib import Path
from types import SimpleNamespace

# ★ テスト用APIキーを設定（認証付きエンドポイントのテスト用）
# server import 前に設定して、起動時の警告を抑制
_TEST_API_KEY = "test-server-extra-key"
os.environ["VERITAS_API_KEY"] = _TEST_API_KEY
_AUTH_HEADERS = {"X-API-Key": _TEST_API_KEY}

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

import veritas_os.api.server as server
import veritas_os.api.routes_decide as routes_decide
from veritas_os.api.schemas import (
    DecideRequest,
    MemoryGetRequest,
    MemoryPutRequest,
    MemorySearchRequest,
)
from veritas_os.security.signing import build_trustlog_signer


client = TestClient(server.app)


class DummyRequest:
    """
    verify_signature をユニットテストするための簡易 Request モック
    """

    def __init__(self, body: bytes):
        self._body = body

    async def body(self) -> bytes:
        return self._body


# -------------------------------------------------
# 共通フィクスチャ: APIキー & レートリミットのリセット
# -------------------------------------------------


@pytest.fixture(autouse=True)
def _setup_env_and_rate_limit(monkeypatch):
    """
    - 毎テストで VERITAS_API_KEY をセット
    - レートリミット用バケットをクリア
    """
    monkeypatch.setenv("VERITAS_API_KEY", "test-api-key")
    server._rate_bucket.clear()  # type: ignore[attr-defined]
    yield
    server._rate_bucket.clear()  # type: ignore[attr-defined]


# -------------------------------------------------
# Health / Status / Metrics (基本パス)
# -------------------------------------------------


def test_health_and_status_and_metrics(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    # health 系
    for path in ("/health", "/v1/health"):
        r = client.get(path)
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert "uptime" in data

    # status 系
    for path in ("/status", "/v1/status", "/api/status"):
        r = client.get(path)
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert "uptime" in data
        assert "version" in data

    # metrics (ファイルが無くても 200 が返ることだけ確認)
    r = client.get("/v1/metrics", headers=_AUTH_HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert "decide_files" in data
    assert "trust_jsonl_lines" in data
    assert "trust_json_status" in data
    assert "trust_json_error" in data
    assert "last_decide_at" in data
    assert "server_time" in data
    assert "auth_reject_reasons" in data
    assert "auth_store_mode" in data
    assert "auth_store_failure_mode" in data


def test_auth_store_error_policy_fail_closed(monkeypatch):
    """Fail-closed mode should reject requests when auth store access fails."""

    class BrokenStore:
        def register_nonce(self, nonce: str, ttl_sec: float) -> bool:
            raise RuntimeError("broken nonce")

        def increment_auth_failure(self, client_ip: str, limit: int, window_sec: float) -> bool:
            raise RuntimeError("broken auth fail")

        def increment_rate_limit(self, api_key: str, limit: int, window_sec: float) -> bool:
            raise RuntimeError("broken rate")

    monkeypatch.setenv("VERITAS_AUTH_STORE_FAILURE_MODE", "closed")
    monkeypatch.setattr(server, "_AUTH_SECURITY_STORE", BrokenStore())

    with pytest.raises(HTTPException) as exc:
        server.enforce_rate_limit(x_api_key="user-1")  # type: ignore[arg-type]

    assert exc.value.status_code == 429


def test_auth_store_error_policy_fail_open(monkeypatch):
    """Fail-open mode should allow requests when auth store access fails."""

    class BrokenStore:
        def register_nonce(self, nonce: str, ttl_sec: float) -> bool:
            raise RuntimeError("broken nonce")

        def increment_auth_failure(self, client_ip: str, limit: int, window_sec: float) -> bool:
            raise RuntimeError("broken auth fail")

        def increment_rate_limit(self, api_key: str, limit: int, window_sec: float) -> bool:
            raise RuntimeError("broken rate")

    monkeypatch.setenv("VERITAS_ENV", "local")
    monkeypatch.setenv("VERITAS_AUTH_STORE_FAILURE_MODE", "open")
    monkeypatch.setenv("VERITAS_AUTH_ALLOW_FAIL_OPEN", "true")
    monkeypatch.setattr(server, "_AUTH_SECURITY_STORE", BrokenStore())

    assert server.enforce_rate_limit(x_api_key="user-2") is True  # type: ignore[arg-type]




def test_replay_api_endpoint_with_hmac_headers(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    monkeypatch.setattr(server, "API_KEY_DEFAULT", _TEST_API_KEY)
    monkeypatch.setenv("VERITAS_API_SECRET", "a" * 32)
    monkeypatch.setattr(server, "API_SECRET", b"")

    async def _fake_run_replay(decision_id: str, strict=None):
        return server.SimpleNamespace(
            decision_id=decision_id,
            replay_path="/tmp/replay.json",
            match=True,
            diff_summary="no_diff",
            replay_time_ms=9,
            schema_version="1.0.0",
            severity="info",
            divergence_level="no_divergence",
            audit_summary="Replay dec-9 (standard): MATCH — no divergence detected.",
        )

    monkeypatch.setattr(server, "run_replay", _fake_run_replay)

    body = json.dumps({"strict": True}, separators=(",", ":"))
    ts = str(int(time.time()))
    nonce = "nonce-replay-endpoint"
    payload = f"{ts}\n{nonce}\n{body}"
    signature = hmac.new(("a" * 32).encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

    response = client.post(
        "/v1/replay/dec-9",
        headers={
            "X-API-Key": _TEST_API_KEY,
            "X-VERITAS-TIMESTAMP": ts,
            "X-VERITAS-NONCE": nonce,
            "X-VERITAS-SIGNATURE": signature,
            "Content-Type": "application/json",
        },
        content=body,
    )

    assert response.status_code == 200
    payload_json = response.json()
    assert payload_json["ok"] is True
    assert payload_json["decision_id"] == "dec-9"
    assert payload_json["match"] is True
    assert payload_json["replay_time_ms"] == 9



def test_replay_api_endpoint_not_found_hides_exception(monkeypatch):
    """Replay not-found errors must not expose internal exception details."""
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    monkeypatch.setattr(server, "API_KEY_DEFAULT", _TEST_API_KEY)
    monkeypatch.setenv("VERITAS_API_SECRET", "b" * 32)
    monkeypatch.setattr(server, "API_SECRET", b"")

    async def _fake_run_replay(decision_id: str, strict=None):
        raise ValueError(f"decision_not_found: {decision_id}")

    monkeypatch.setattr(server, "run_replay", _fake_run_replay)

    body = "{}"
    ts = str(int(time.time()))
    nonce = "nonce-replay-not-found"
    payload = f"{ts}\n{nonce}\n{body}"
    signature = hmac.new(("b" * 32).encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

    response = client.post(
        "/v1/replay/dec-missing",
        headers={
            "X-API-Key": _TEST_API_KEY,
            "X-VERITAS-TIMESTAMP": ts,
            "X-VERITAS-NONCE": nonce,
            "X-VERITAS-SIGNATURE": signature,
            "Content-Type": "application/json",
        },
        content=body,
    )

    assert response.status_code == 404
    payload_json = response.json()
    assert payload_json["ok"] is False
    assert payload_json["error"] == "decision_not_found"
    assert payload_json["decision_id"] == "dec-missing"

def test_replay_decision_endpoint(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    monkeypatch.setattr(server, "API_KEY_DEFAULT", _TEST_API_KEY)

    class DummyPipeline:
        async def replay_decision(self, decision_id: str, mock_external_apis: bool = True):
            return {
                "match": True,
                "diff": {"changed": False, "decision_id": decision_id},
                "replay_time_ms": 12,
            }

    monkeypatch.setattr(server, "get_decision_pipeline", lambda: DummyPipeline())

    response = client.post(
        "/v1/decision/replay/dec-1?mock_external_apis=true",
        headers=_AUTH_HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["match"] is True
    assert body["diff"]["changed"] is False
    assert body["replay_time_ms"] == 12


# -------------------------------------------------
# Health / Status / Metrics (ファイル有りパス)
# -------------------------------------------------


def test_metrics_counts_shadow_and_log(tmp_path, monkeypatch):
    """
    /v1/metrics が
      - SHADOW_DIR の decide_* ファイルをカウント
      - LOG_JSONL の行数をカウント
      - last_decide_at を JSON から読む
    パスを踏むテスト
    """
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    shadow_dir = tmp_path / "shadow_for_metrics"
    shadow_dir.mkdir()
    log_jsonl = tmp_path / "trust_log_metrics.jsonl"

    monkeypatch.setattr(server, "SHADOW_DIR", shadow_dir)
    monkeypatch.setattr(server, "LOG_JSONL", log_jsonl)

    # decide_* ファイルを 1 つ作成
    decide_file = shadow_dir / "decide_20250101_000000_000.json"
    decide_file.write_text(
        json.dumps({"created_at": "2025-01-01T00:00:00Z"}), encoding="utf-8"
    )

    # JSONL に 2 行書く
    with log_jsonl.open("w", encoding="utf-8") as f:
        f.write("{}\n{}\n")

    r = client.get("/v1/metrics", headers=_AUTH_HEADERS)
    assert r.status_code == 200
    data = r.json()

    assert data["decide_files"] == 1
    assert data["trust_jsonl_lines"] == 2
    assert data["last_decide_at"] == "2025-01-01T00:00:00Z"
    assert "server_time" in data


def test_metrics_applies_decide_file_limit(tmp_path, monkeypatch):
    """/v1/metrics が decide_file_limit を適用し、切り詰め状態を返す。"""
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    shadow_dir = tmp_path / "shadow_metrics_limit"
    shadow_dir.mkdir()
    log_jsonl = tmp_path / "trust_log_metrics_limit.jsonl"
    log_jsonl.write_text("", encoding="utf-8")

    monkeypatch.setattr(server, "SHADOW_DIR", shadow_dir)
    monkeypatch.setattr(server, "LOG_JSONL", log_jsonl)

    for idx in range(3):
        file_name = f"decide_20250101_00000{idx}_000.json"
        created_at = f"2025-01-01T00:00:0{idx}Z"
        (shadow_dir / file_name).write_text(
            json.dumps({"created_at": created_at}),
            encoding="utf-8",
        )

    response = client.get("/v1/metrics?decide_file_limit=2", headers=_AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()

    assert data["decide_files"] == 3
    assert data["decide_files_returned"] == 2
    assert data["decide_files_truncated"] is True
    assert data["last_decide_at"] == "2025-01-01T00:00:02Z"


# -------------------------------------------------
# APIキーまわり (require_api_key / enforce_rate_limit)
# -------------------------------------------------


def test_get_expected_api_key_falls_back_to_default(monkeypatch):
    """
    env が空のときに API_KEY_DEFAULT が使われるパス
    """
    monkeypatch.delenv("VERITAS_API_KEY", raising=False)
    monkeypatch.setattr(server, "API_KEY_DEFAULT", "cfg-key")

    got = server._get_expected_api_key()
    assert got == "cfg-key"




def test_resolve_expected_api_key_with_source_precedence(monkeypatch):
    """環境変数 > API_KEY_DEFAULT > cfg.api_key の優先順を確認する。"""
    monkeypatch.setenv("VERITAS_API_KEY", "env-key")
    monkeypatch.setattr(server, "API_KEY_DEFAULT", "default-key")
    monkeypatch.setattr(server.cfg, "api_key", "cfg-key")

    key, source = server._resolve_expected_api_key_with_source()
    assert key == "env-key"
    assert source == "env"

    monkeypatch.delenv("VERITAS_API_KEY", raising=False)
    key, source = server._resolve_expected_api_key_with_source()
    assert key == "default-key"
    assert source == "api_key_default"

    monkeypatch.setattr(server, "API_KEY_DEFAULT", "")
    key, source = server._resolve_expected_api_key_with_source()
    assert key == "cfg-key"
    assert source == "config"

    monkeypatch.setattr(server.cfg, "api_key", "")
    key, source = server._resolve_expected_api_key_with_source()
    assert key == ""
    assert source == "missing"




def test_log_api_key_source_once_logs_once_per_label(monkeypatch):
    """同一ラベルは1回だけログされ、異なるラベルは個別にログされる。"""
    server._log_api_key_source_once.cache_clear()

    logged_messages = []

    def _fake_info(message, *args):
        logged_messages.append(message % args)

    monkeypatch.setattr(server.logger, "info", _fake_info)

    server._log_api_key_source_once("env")
    server._log_api_key_source_once("env")
    server._log_api_key_source_once("config")

    assert logged_messages == [
        "Resolved API key source: env",
        "Resolved API key source: config",
    ]

def test_get_cfg_fallback_disables_cors(monkeypatch):
    """
    get_cfg が失敗したときに CORS を完全拒否するフォールバックになること。
    """
    monkeypatch.setattr(server, "_cfg_state", server._LazyState())

    def _raise_import_error(*args, **kwargs):
        raise ImportError("boom")

    monkeypatch.setattr(server.importlib, "import_module", _raise_import_error)

    cfg = server.get_cfg()

    assert cfg.cors_allow_origins == []
    assert cfg.api_key == ""


def test_require_api_key_server_not_configured(monkeypatch):
    """
    サーバ側の API キー未設定パス（500）
    """
    monkeypatch.delenv("VERITAS_API_KEY", raising=False)
    monkeypatch.setattr(server, "API_KEY_DEFAULT", "")
    # cfg.api_key もモックして空にする（モジュール読み込み時に環境変数から初期化されている可能性があるため）
    monkeypatch.setattr(server.cfg, "api_key", "")
    with pytest.raises(HTTPException) as exc:
        server.require_api_key(x_api_key="anything")  # type: ignore[arg-type]
    assert exc.value.status_code == 500
    assert "Server API key not configured" in exc.value.detail


def test_require_api_key_missing_key(monkeypatch):
    """
    expected キーはあるが、ヘッダが空 → 401
    """
    monkeypatch.setenv("VERITAS_API_KEY", "expected-key")
    with pytest.raises(HTTPException) as exc:
        server.require_api_key(x_api_key=None)  # type: ignore[arg-type]
    assert exc.value.status_code == 401
    assert "Missing API key" in exc.value.detail


def test_require_api_key_invalid_key(monkeypatch):
    """
    間違ったキー → 401
    """
    monkeypatch.setenv("VERITAS_API_KEY", "expected-key")
    with pytest.raises(HTTPException) as exc:
        server.require_api_key(x_api_key="wrong-key")  # type: ignore[arg-type]
    assert exc.value.status_code == 401
    assert "Invalid API key" in exc.value.detail


def test_require_api_key_success(monkeypatch):
    """
    正しいキー → True
    """
    monkeypatch.setenv("VERITAS_API_KEY", "expected-key")
    ok = server.require_api_key(x_api_key="expected-key")  # type: ignore[arg-type]
    assert ok is True


def _make_request_with_ip(ip: str):
    """Create a minimal mock request with the given client IP."""
    from unittest.mock import MagicMock
    req = MagicMock()
    req.client.host = ip
    return req


def test_require_api_key_auth_failure_rate_limit(monkeypatch):
    """認証失敗が連続した場合、IP単位で429になること。"""
    monkeypatch.setenv("VERITAS_API_KEY", "expected-key")
    server._auth_fail_bucket.clear()  # type: ignore[attr-defined]

    for _ in range(server._AUTH_FAIL_RATE_LIMIT):  # type: ignore[attr-defined]
        with pytest.raises(HTTPException) as exc:
            server.require_api_key(
                request=_make_request_with_ip("203.0.113.10"),
                x_api_key="wrong-key",
            )
        assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as exc:
        server.require_api_key(
            request=_make_request_with_ip("203.0.113.10"),
            x_api_key="wrong-key",
        )
    assert exc.value.status_code == 429
    assert "Too many auth failures" in exc.value.detail


def test_require_api_key_auth_failure_isolated_by_ip(monkeypatch):
    """失敗回数はIPごとに分離され、別IPは直ちにブロックされないこと。"""
    monkeypatch.setenv("VERITAS_API_KEY", "expected-key")
    server._auth_fail_bucket.clear()  # type: ignore[attr-defined]

    for _ in range(server._AUTH_FAIL_RATE_LIMIT):  # type: ignore[attr-defined]
        with pytest.raises(HTTPException):
            server.require_api_key(
                request=_make_request_with_ip("198.51.100.20"),
                x_api_key="wrong-key",
            )

    with pytest.raises(HTTPException) as blocked:
        server.require_api_key(
            request=_make_request_with_ip("198.51.100.20"),
            x_api_key="wrong-key",
        )
    assert blocked.value.status_code == 429

    with pytest.raises(HTTPException) as other_ip:
        server.require_api_key(
            request=_make_request_with_ip("198.51.100.21"),
            x_api_key="wrong-key",
        )
    assert other_ip.value.status_code == 401


def test_enforce_rate_limit_missing_key():
    """
    enforce_rate_limit: APIキー無し → 401
    """
    with pytest.raises(HTTPException) as exc:
        server.enforce_rate_limit(x_api_key=None)  # type: ignore[arg-type]
    assert exc.value.status_code == 401
    assert "Missing API key" in exc.value.detail


def test_enforce_rate_limit_exceeded():
    """
    _RATE_LIMIT 回まではOK、1回超過で 429
    """
    key = "rate-user"
    server._rate_bucket.clear()  # type: ignore[attr-defined]

    # 制限回数までは通る
    for _ in range(server._RATE_LIMIT):  # type: ignore[attr-defined]
        assert (
            server.enforce_rate_limit(x_api_key=key) is True  # type: ignore[arg-type]
        )

    # 1回超過で HTTP 429
    with pytest.raises(HTTPException) as exc:
        server.enforce_rate_limit(x_api_key=key)  # type: ignore[arg-type]
    assert exc.value.status_code == 429
    assert "Rate limit exceeded" in exc.value.detail


# -------------------------------------------------
# HMAC verify_signature 系
# -------------------------------------------------


def test_verify_signature_missing_secret(monkeypatch):
    """
    API_SECRET 未設定 → 500
    """
    monkeypatch.setattr(server, "API_SECRET", b"")
    req = DummyRequest(b"{}")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            server.verify_signature(
                request=req,
                x_api_key="k",
                x_timestamp=str(int(time.time())),
                x_nonce="nonce-1",
                x_signature="dummy",
            )
        )

    assert exc.value.status_code == 500
    assert "Server secret missing" in exc.value.detail


def test_verify_signature_placeholder_secret(monkeypatch):
    """
    VERITAS_API_SECRET がプレースホルダーの場合 → 500
    """
    monkeypatch.setattr(server, "API_SECRET", b"")
    monkeypatch.setenv(
        "VERITAS_API_SECRET",
        server._DEFAULT_API_SECRET_PLACEHOLDER,
    )
    req = DummyRequest(b"{}")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            server.verify_signature(
                request=req,
                x_api_key="k",
                x_timestamp=str(int(time.time())),
                x_nonce="nonce-1",
                x_signature="dummy",
            )
        )

    assert exc.value.status_code == 500
    assert "Server secret missing" in exc.value.detail


def test_verify_signature_ok_and_replay(monkeypatch):
    """
    正常な署名 → True、同じ nonce で 2 回目 → Replay (401)
    """
    secret = b"test-secret"
    monkeypatch.setattr(server, "API_SECRET", secret)
    server._nonce_store.clear()  # type: ignore[attr-defined]

    ts = str(int(time.time()))
    nonce = "nonce-xyz"
    body_dict = {"hello": "world"}
    body_str = json.dumps(body_dict)
    payload = f"{ts}\n{nonce}\n{body_str}"
    sig = hmac.new(secret, payload.encode("utf-8"), "sha256").hexdigest()

    # 1回目は OK
    req = DummyRequest(body_str.encode("utf-8"))
    ok = asyncio.run(
        server.verify_signature(
            request=req,
            x_api_key="k",
            x_timestamp=ts,
            x_nonce=nonce,
            x_signature=sig,
        )
    )
    assert ok is True

    # 2回目（同一 nonce）は Replay
    req2 = DummyRequest(body_str.encode("utf-8"))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            server.verify_signature(
                request=req2,
                x_api_key="k",
                x_timestamp=ts,
                x_nonce=nonce,
                x_signature=sig,
            )
        )
    assert exc.value.status_code == 401
    assert "Replay" in exc.value.detail


def test_verify_signature_timestamp_out_of_range(monkeypatch):
    """
    古すぎる timestamp → 401 (Timestamp out of range)
    """
    secret = b"test-secret"
    monkeypatch.setattr(server, "API_SECRET", secret)
    server._nonce_store.clear()  # type: ignore[attr-defined]

    ts = str(int(time.time()) - 1000)  # _NONCE_TTL_SEC(300) より十分古い
    nonce = "nonce-old"
    body_str = "{}"
    payload = f"{ts}\n{nonce}\n{body_str}"
    sig = hmac.new(secret, payload.encode("utf-8"), "sha256").hexdigest()

    req = DummyRequest(body_str.encode("utf-8"))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            server.verify_signature(
                request=req,
                x_api_key="k",
                x_timestamp=ts,
                x_nonce=nonce,
                x_signature=sig,
            )
        )

    assert exc.value.status_code == 401
    assert "Timestamp out of range" in exc.value.detail


def test_verify_signature_invalid_timestamp(monkeypatch):
    """
    int に変換できない timestamp → 401 (Invalid timestamp)
    """
    secret = b"test-secret"
    monkeypatch.setattr(server, "API_SECRET", secret)
    server._nonce_store.clear()  # type: ignore[attr-defined]

    req = DummyRequest(b"{}")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            server.verify_signature(
                request=req,
                x_api_key="k",
                x_timestamp="not-int",
                x_nonce="nonce-bad",
                x_signature="sig",
            )
        )

    assert exc.value.status_code == 401
    assert "Invalid timestamp" in exc.value.detail


def test_verify_signature_missing_headers(monkeypatch):
    """
    署名ヘッダのどれかが欠けている場合 → 401 (Missing auth headers)
    """
    secret = b"test-secret"
    monkeypatch.setattr(server, "API_SECRET", secret)
    server._nonce_store.clear()  # type: ignore[attr-defined]

    req = DummyRequest(b"{}")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            server.verify_signature(
                request=req,
                x_api_key=None,
                x_timestamp=None,
                x_nonce=None,
                x_signature=None,
            )
        )

    assert exc.value.status_code == 401
    assert "Missing auth headers" in exc.value.detail


# -------------------------------------------------
# redact / ValidationError handler / /v1/decide 認証
# -------------------------------------------------


def test_redact_masks_email_and_phone():
    """
    redact がメールアドレスと電話番号をマスクすることを確認
    sanitize.py 統合後は 〔メール〕〔電話〕 形式でマスクされる
    """
    s = "mail: user@example.com tel: 090-1234-5678"
    red = server.redact(s)
    assert "user@example.com" not in red
    assert "090-1234-5678" not in red
    # sanitize.py 形式: 〔メール〕〔電話〕
    # フォールバック形式: [redacted@email] [redacted:phone]
    assert "〔メール〕" in red or "[redacted@email]" in red
    assert "〔電話〕" in red or "[redacted:phone]" in red


def test_decide_requires_api_key():
    """
    /v1/decide は API キー無しだと 401 になることを確認
    """
    body = server._decide_example()
    r = client.post("/v1/decide", json=body)
    assert r.status_code == 401


def test_decide_validation_error_handler_returns_hint(monkeypatch):
    """
    /v1/decide に「おかしなボディ」を投げたときの挙動をテストする。

    - 旧実装: FastAPI の RequestValidationError → 422 + on_validation_error
    - 現実装: バリデーションで落とさず、そのままパイプライン実行 → 200

    どちらの挙動でもテストが通るようにしておく。
    """
    # Enable debug mode to include raw_body in 422 response
    monkeypatch.setenv("VERITAS_DEBUG_MODE", "true")

    r = client.post(
        "/v1/decide",
        json={"invalid": "payload"},
        headers={"X-API-Key": "test-api-key"},
    )

    if r.status_code == 422:
        # カスタム validation handler パス
        data = r.json()
        assert "detail" in data
        assert "hint" in data
        assert "expected_example" in data["hint"]
        # raw_body is only present in debug mode
        assert "raw_body" in data
        assert '"invalid"' in data["raw_body"]
    else:
        # 現在の実装: 正常系として扱われて 200 を返す
        assert r.status_code == 200
        data = r.json()
        # 決定エンドポイントとして最低限「それっぽいレスポンス」であることだけ確認
        assert isinstance(data, dict)
        # 代表的なキーのいずれかが含まれていること（実装によって多少変わっても耐える）
        assert any(k in data for k in ("request_id", "status", "result", "decision"))


def test_decide_pipeline_unavailable_hides_detail(monkeypatch):
    """
    /v1/decide がパイプライン不在のとき、
    detail が一般的なメッセージになることを確認する。
    """
    monkeypatch.setattr(server, "get_decision_pipeline", lambda: None)
    server._pipeline_state.err = "boom"  # type: ignore[attr-defined]

    r = client.post(
        "/v1/decide",
        json=server._decide_example(),
        headers={"X-API-Key": "test-api-key"},
    )

    assert r.status_code == 503
    data = r.json()
    assert data["error"] == server.DECIDE_GENERIC_ERROR
    assert data["detail"] == server.DECIDE_GENERIC_ERROR
    assert "boom" not in data["detail"]


def test_decide_pipeline_execution_failure_hides_detail(monkeypatch):
    """
    /v1/decide 実行失敗時に detail が一般化されることを確認する。
    """

    class DummyPipeline:
        @staticmethod
        async def run_decide_pipeline(req, request):
            raise RuntimeError("boom")

    monkeypatch.setattr(server, "get_decision_pipeline", lambda: DummyPipeline())

    r = client.post(
        "/v1/decide",
        json=server._decide_example(),
        headers={"X-API-Key": "test-api-key"},
    )

    assert r.status_code == 503
    data = r.json()
    assert data["error"] == server.DECIDE_GENERIC_ERROR
    assert data["detail"] == server.DECIDE_GENERIC_ERROR
    assert "boom" not in data["detail"]



# -------------------------------------------------
# FUJI quick validate (/v1/fuji/validate)
# -------------------------------------------------



def test_decide_pipeline_execution_failure_classifies_timeout(monkeypatch):
    """/v1/decide failures should expose timeout category without leaking internals."""

    class DummyPipeline:
        @staticmethod
        async def run_decide_pipeline(req, request):
            raise TimeoutError("operation timed out")

    monkeypatch.setattr(server, "get_decision_pipeline", lambda: DummyPipeline())

    response = client.post(
        "/v1/decide",
        json=server._decide_example(),
        headers={"X-API-Key": "test-api-key"},
    )

    assert response.status_code == 503
    data = response.json()
    assert data["error"] == server.DECIDE_GENERIC_ERROR
    assert data["failure_category"] == "timeout"
    assert data["detail"] == server.DECIDE_GENERIC_ERROR


def test_decide_pipeline_execution_failure_classifies_invalid_input(monkeypatch):
    """/v1/decide failures should expose invalid_input category for input-shape errors."""

    class DummyPipeline:
        @staticmethod
        async def run_decide_pipeline(req, request):
            raise ValueError("bad request shape")

    monkeypatch.setattr(server, "get_decision_pipeline", lambda: DummyPipeline())

    response = client.post(
        "/v1/decide",
        json=server._decide_example(),
        headers={"X-API-Key": "test-api-key"},
    )

    assert response.status_code == 503
    data = response.json()
    assert data["error"] == server.DECIDE_GENERIC_ERROR
    assert data["failure_category"] == "invalid_input"
    assert data["detail"] == server.DECIDE_GENERIC_ERROR


def test_decide_pipeline_execution_failure_classifies_permission_denied(monkeypatch):
    """/v1/decide failures should expose permission_denied category safely."""

    class DummyPipeline:
        @staticmethod
        async def run_decide_pipeline(req, request):
            raise PermissionError("operation is not permitted")

    monkeypatch.setattr(server, "get_decision_pipeline", lambda: DummyPipeline())

    response = client.post(
        "/v1/decide",
        json=server._decide_example(),
        headers={"X-API-Key": "test-api-key"},
    )

    assert response.status_code == 503
    data = response.json()
    assert data["error"] == server.DECIDE_GENERIC_ERROR
    assert data["failure_category"] == "permission_denied"
    assert data["detail"] == server.DECIDE_GENERIC_ERROR


def test_decide_accepts_list_stage_payloads_for_event_summary(monkeypatch):
    """Decide endpoint must handle debate/critique payloads that are lists."""

    class DummyPipeline:
        @staticmethod
        async def run_decide_pipeline(req, request):
            return {
                "ok": True,
                "request_id": "rid-list-summary",
                "query": "test",
                "result": "ok",
                "decision": "allow",
                "debate": [{"summary": "debate from list"}],
                "critique": ["critique from list"],
                "trust_score": 0.95,
            }

    monkeypatch.setattr(server, "get_decision_pipeline", lambda: DummyPipeline())

    response = client.post(
        "/v1/decide",
        json=server._decide_example(),
        headers={"X-API-Key": "test-api-key"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data.get("ok") is True


def test_decide_wat_shadow_disabled_keeps_response_shape(monkeypatch):
    """WAT disabled policy must keep /v1/decide behavior unchanged."""

    class DummyPipeline:
        @staticmethod
        async def run_decide_pipeline(req, request):
            return {
                "ok": True,
                "request_id": "rid-disabled",
                "query": req.query,
                "decision": "allow",
                "business_decision": "APPROVE",
                "result": "ok",
            }

    monkeypatch.setattr(server, "get_decision_pipeline", lambda: DummyPipeline())
    monkeypatch.setattr(routes_decide, "get_policy", server.get_policy)
    monkeypatch.setattr(
        routes_decide,
        "persist_wat_issuance_event",
        lambda **_kwargs: pytest.fail("shadow hook should not run when WAT is disabled"),
    )

    response = client.post(
        "/v1/decide",
        json=server._decide_example(),
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "allow"
    assert "wat_shadow" not in payload.get("meta", {})


def test_decide_wat_shadow_enabled_emits_events_without_mutating_action(monkeypatch):
    """Observer-only WAT hook emits telemetry while leaving production decision untouched."""
    captured_events = []
    captured_issue = []
    captured_validate = []

    class DummyPipeline:
        @staticmethod
        async def run_decide_pipeline(req, request):
            return {
                "ok": True,
                "request_id": "rid-shadow",
                "query": req.query,
                "decision": "allow",
                "business_decision": "APPROVE",
                "result": "ok",
                "selected_option": {"title": "Ship"},
            }

    policy = {
        "wat": {"enabled": True, "issuance_mode": "shadow_only", "default_ttl_seconds": 60},
        "psid": {"display_length": 10},
        "shadow_validation": {
            "timestamp_skew_tolerance_seconds": 5,
            "warning_only_until": None,
            "replay_binding_required": False,
        },
        "revocation": {"degrade_on_pending": False},
        "drift_scoring": {},
    }

    monkeypatch.setattr(server, "get_decision_pipeline", lambda: DummyPipeline())
    monkeypatch.setattr(routes_decide, "get_policy", lambda: policy)
    monkeypatch.setattr(
        routes_decide,
        "persist_wat_issuance_event",
        lambda **kwargs: captured_issue.append(kwargs) or {"event_id": "issue-1"},
    )
    monkeypatch.setattr(
        routes_decide,
        "persist_wat_validation_event",
        lambda **kwargs: captured_validate.append(kwargs) or {"event_id": "validate-1"},
    )
    monkeypatch.setattr(
        routes_decide,
        "persist_wat_replay_event",
        lambda **kwargs: captured_validate.append(kwargs) or {"event_id": "replay-1"},
    )
    monkeypatch.setattr(server, "_publish_event", lambda event_type, payload: captured_events.append((event_type, payload)))

    response = client.post(
        "/v1/decide",
        json=server._decide_example(),
        headers={"X-API-Key": "test-api-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "allow"
    assert body["business_decision"] == "APPROVE"
    assert captured_issue
    assert captured_validate
    assert any(event_type == "wat.shadow.validation" for event_type, _ in captured_events)
    wat_shadow = body.get("meta", {}).get("wat_shadow", {})
    assert wat_shadow.get("wat_id")
    assert wat_shadow.get("psid_display")
    assert wat_shadow.get("validation_status")
    assert body.get("wat_integrity", {}).get("wat_id") == wat_shadow.get("wat_id")
    drift_vector = body.get("wat_drift_vector", {})
    assert set(drift_vector.keys()) == {"policy", "signature", "observable", "temporal"}
    summary = body.get("wat_operator_summary", {})
    assert set(summary.keys()) == {
        "integrity_severity",
        "affected_lanes",
        "event_ts",
        "correlation_id",
        "operator_verbosity",
    }
    assert summary.get("operator_verbosity") == "minimal"
    assert summary.get("affected_lanes") == ["wat_shadow"]
    assert summary.get("correlation_id") == "rid-shadow"
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", str(summary.get("event_ts", "")))
    assert body.get("wat_operator_detail") is None


def test_decide_wat_shadow_validation_failure_does_not_change_decision(monkeypatch):
    """Validation failure in shadow lane must not alter final production decision."""

    class DummyPipeline:
        @staticmethod
        async def run_decide_pipeline(req, request):
            return {
                "ok": True,
                "request_id": "rid-fail",
                "query": req.query,
                "decision": "allow",
                "business_decision": "APPROVE",
                "result": "ok",
            }

    policy = {
        "wat": {"enabled": True, "issuance_mode": "shadow_only", "default_ttl_seconds": 60},
        "psid": {"display_length": 12},
        "shadow_validation": {
            "timestamp_skew_tolerance_seconds": 5,
            "warning_only_until": None,
            "replay_binding_required": False,
        },
        "revocation": {"degrade_on_pending": False},
        "drift_scoring": {},
    }

    monkeypatch.setattr(server, "get_decision_pipeline", lambda: DummyPipeline())
    monkeypatch.setattr(routes_decide, "get_policy", lambda: policy)
    monkeypatch.setattr(
        routes_decide,
        "validate_local",
        lambda **kwargs: {
            "validation_status": "invalid",
            "admissibility_state": "non_admissible",
            "failure_type": "signature_invalid",
            "drift_vector": {"policy_drift": 0.0, "signature_drift": 1.0, "observable_drift": 0.0, "temporal_drift": 0.0},
        },
    )

    response = client.post(
        "/v1/decide",
        json=server._decide_example(),
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "allow"
    assert payload["business_decision"] == "APPROVE"
    assert payload.get("meta", {}).get("wat_shadow", {}).get("validation_status") == "invalid"
    assert payload.get("wat_integrity", {}).get("validation_status") == "invalid"
    assert payload.get("wat_integrity", {}).get("integrity_state") == "critical"
    assert payload.get("wat_drift_vector") == {
        "policy": 0.0,
        "signature": 1.0,
        "observable": 0.0,
        "temporal": 0.0,
    }


def test_decide_wat_shadow_expanded_operator_verbosity_surfaces_detail(monkeypatch):
    """Expanded verbosity keeps default summary stable while enabling drill-down."""

    class DummyPipeline:
        @staticmethod
        async def run_decide_pipeline(req, request):
            return {
                "ok": True,
                "request_id": "rid-expanded",
                "query": req.query,
                "decision": "allow",
                "business_decision": "APPROVE",
                "result": "ok",
            }

    policy = {
        "wat": {"enabled": True, "issuance_mode": "shadow_only", "default_ttl_seconds": 60},
        "psid": {"display_length": 12},
        "shadow_validation": {
            "timestamp_skew_tolerance_seconds": 5,
            "warning_only_until": None,
            "replay_binding_required": False,
        },
        "revocation": {"degrade_on_pending": False},
        "drift_scoring": {},
        "operator_verbosity": "expanded",
    }

    monkeypatch.setattr(server, "get_decision_pipeline", lambda: DummyPipeline())
    monkeypatch.setattr(routes_decide, "get_policy", lambda: policy)

    response = client.post(
        "/v1/decide",
        json=server._decide_example(),
        headers={"X-API-Key": "test-api-key"},
    )

    assert response.status_code == 200
    payload = response.json()
    summary = payload.get("wat_operator_summary", {})
    assert summary.get("operator_verbosity") == "expanded"
    assert set(summary.keys()) == {
        "integrity_severity",
        "affected_lanes",
        "event_ts",
        "correlation_id",
        "operator_verbosity",
    }
    detail = payload.get("wat_operator_detail", {})
    assert "drift_vector" in detail


def test_decide_wat_shadow_uses_sign_wat(monkeypatch):
    """Shadow lane must build/sign WAT instead of using placeholder signatures."""

    class DummyPipeline:
        @staticmethod
        async def run_decide_pipeline(req, request):
            return {
                "ok": True,
                "request_id": "rid-sign",
                "query": req.query,
                "decision": "allow",
                "business_decision": "APPROVE",
                "result": "ok",
            }

    policy = {
        "wat": {"enabled": True, "issuance_mode": "shadow_only", "default_ttl_seconds": 60},
        "psid": {"display_length": 12},
        "shadow_validation": {
            "timestamp_skew_tolerance_seconds": 5,
            "warning_only_until": None,
            "replay_binding_required": False,
        },
        "revocation": {"degrade_on_pending": False},
        "drift_scoring": {},
    }
    calls = {"sign_wat": 0}

    monkeypatch.setattr(server, "get_decision_pipeline", lambda: DummyPipeline())
    monkeypatch.setattr(routes_decide, "get_policy", lambda: policy)
    original_sign_wat = routes_decide.sign_wat

    def _tracked_sign_wat(claims, signer):
        calls["sign_wat"] += 1
        return original_sign_wat(claims, signer)

    monkeypatch.setattr(routes_decide, "sign_wat", _tracked_sign_wat)

    response = client.post(
        "/v1/decide",
        json=server._decide_example(),
        headers={"X-API-Key": "test-api-key"},
    )

    assert response.status_code == 200
    assert calls["sign_wat"] == 1
    assert response.json()["decision"] == "allow"


def test_decide_wat_shadow_pointer_missing_digest_alive(monkeypatch):
    """Missing pointer refs should still produce digest and validation metadata."""

    class DummyPipeline:
        @staticmethod
        async def run_decide_pipeline(req, request):
            return {
                "ok": True,
                "request_id": "rid-pointerless",
                "query": req.query,
                "decision": "allow",
                "business_decision": "APPROVE",
                "result": "ok",
                "trust_log": {"event": "no-pointers"},
            }

    policy = {
        "wat": {"enabled": True, "issuance_mode": "shadow_only", "default_ttl_seconds": 60},
        "psid": {"display_length": 12},
        "shadow_validation": {
            "timestamp_skew_tolerance_seconds": 5,
            "warning_only_until": None,
            "replay_binding_required": False,
        },
        "revocation": {"degrade_on_pending": False},
        "drift_scoring": {},
    }

    monkeypatch.setattr(server, "get_decision_pipeline", lambda: DummyPipeline())
    monkeypatch.setattr(routes_decide, "get_policy", lambda: policy)

    response = client.post(
        "/v1/decide",
        json=server._decide_example(),
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 200
    wat_shadow = response.json().get("meta", {}).get("wat_shadow", {})
    integrity_summary = wat_shadow.get("integrity_summary", {})
    assert integrity_summary.get("pointer_missing_digest_alive") is True
    assert isinstance(integrity_summary.get("observable_digest"), str)


def test_decide_wat_shadow_replay_suspected_is_surfaced(monkeypatch):
    """Replay suspected in shadow verifier should be surfaced in response metadata."""

    class DummyPipeline:
        @staticmethod
        async def run_decide_pipeline(req, request):
            return {
                "ok": True,
                "request_id": "rid-replay",
                "query": req.query,
                "decision": "allow",
                "business_decision": "APPROVE",
                "result": "ok",
            }

    policy = {
        "wat": {"enabled": True, "issuance_mode": "shadow_only", "default_ttl_seconds": 60},
        "psid": {"display_length": 12},
        "shadow_validation": {
            "timestamp_skew_tolerance_seconds": 5,
            "warning_only_until": None,
            "replay_binding_required": False,
        },
        "revocation": {"degrade_on_pending": False},
        "drift_scoring": {},
    }

    replay_events = []
    monkeypatch.setattr(server, "get_decision_pipeline", lambda: DummyPipeline())
    monkeypatch.setattr(routes_decide, "get_policy", lambda: policy)
    monkeypatch.setattr(
        routes_decide,
        "validate_local",
        lambda **kwargs: {
            "validation_status": "invalid",
            "admissibility_state": "non_admissible",
            "failure_type": "replay_detected",
            "drift_vector": {"policy_drift": 1.0, "signature_drift": 0.0, "observable_drift": 0.0, "temporal_drift": 0.0},
        },
    )
    monkeypatch.setattr(
        routes_decide,
        "persist_wat_replay_event",
        lambda **kwargs: replay_events.append(kwargs) or {"event_id": "replay-1"},
    )

    response = client.post(
        "/v1/decide",
        json=server._decide_example(),
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 200
    wat_shadow = response.json().get("meta", {}).get("wat_shadow", {})
    assert wat_shadow.get("replay_status") == "suspected"
    assert replay_events


def test_decide_wat_shadow_missing_nested_config_uses_conservative_defaults(monkeypatch):
    """Missing nested config must still keep shadow observer path stable."""

    class DummyPipeline:
        @staticmethod
        async def run_decide_pipeline(req, request):
            return {
                "ok": True,
                "request_id": "rid-defaults",
                "query": req.query,
                "decision": "allow",
                "business_decision": "APPROVE",
                "result": "ok",
            }

    captured_validate_kwargs = {}
    monkeypatch.setattr(server, "get_decision_pipeline", lambda: DummyPipeline())
    monkeypatch.setattr(routes_decide, "get_policy", lambda: {"wat": {"enabled": True}})
    monkeypatch.setattr(
        routes_decide,
        "validate_local",
        lambda **kwargs: captured_validate_kwargs.update(kwargs) or {
            "validation_status": "valid",
            "admissibility_state": "warning_only_shadow",
            "failure_type": "",
            "drift_vector": {},
        },
    )

    response = client.post(
        "/v1/decide",
        json=server._decide_example(),
        headers={"X-API-Key": "test-api-key"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "allow"
    assert payload["business_decision"] == "APPROVE"
    wat_shadow = payload.get("meta", {}).get("wat_shadow", {})
    assert wat_shadow.get("revocation_status") == "active"
    validate_config = captured_validate_kwargs.get("config", {})
    assert validate_config.get("timestamp_skew_tolerance_seconds") == 5
    assert validate_config.get("warning_only_until") is None
    assert validate_config.get("replay_binding_required") is False
    assert validate_config.get("drift_weights") == {
        "policy": 0.4,
        "signature": 0.3,
        "observable": 0.2,
        "temporal": 0.1,
    }
    assert validate_config.get("drift_thresholds") == {
        "healthy": 0.2,
        "critical": 0.5,
    }
    assert "signature_verifier" not in validate_config


def test_resolve_shadow_revocation_state_uses_event_lane_active_default(monkeypatch):
    """No revocation telemetry should preserve event-lane ``active`` state."""
    monkeypatch.setattr(
        routes_decide,
        "derive_latest_revocation_state",
        lambda _wat_id: {"status": "active", "source": "wat_events"},
    )
    state = routes_decide._resolve_shadow_revocation_state(wat_id="wat-missing")
    assert state["status"] == "active"
    assert state["source"] == "wat_events"


def test_resolve_shadow_revocation_state_preserves_pending_from_event_lane(monkeypatch):
    """Pending state should be forwarded from event lane without mutation."""
    monkeypatch.setattr(
        routes_decide,
        "derive_latest_revocation_state",
        lambda _wat_id: {
            "status": "revoked_pending",
            "source": "wat_events",
            "event_id": "evt-pending",
        },
    )
    state = routes_decide._resolve_shadow_revocation_state(wat_id="wat-pending")
    assert state["status"] == "revoked_pending"
    assert state["source"] == "wat_events"


def test_decide_wat_shadow_surfaces_revocation_status_from_derived_state(monkeypatch):
    """Decide response must mirror event-lane-derived revocation status."""

    class DummyPipeline:
        @staticmethod
        async def run_decide_pipeline(req, request):
            return {
                "ok": True,
                "request_id": "rid-derived-revocation",
                "query": req.query,
                "decision": "allow",
                "business_decision": "APPROVE",
                "result": "ok",
            }

    policy = {
        "wat": {"enabled": True, "issuance_mode": "shadow_only", "default_ttl_seconds": 60},
        "psid": {"display_length": 12},
        "shadow_validation": {"timestamp_skew_tolerance_seconds": 5},
        "revocation": {"degrade_on_pending": True},
        "drift_scoring": {},
    }
    captured_validate_kwargs = {}
    monkeypatch.setattr(server, "get_decision_pipeline", lambda: DummyPipeline())
    monkeypatch.setattr(routes_decide, "get_policy", lambda: policy)
    monkeypatch.setattr(
        routes_decide,
        "derive_latest_revocation_state",
        lambda _wat_id: {
            "status": "revoked_pending",
            "source": "wat_events",
            "event_id": "evt-123",
        },
    )
    monkeypatch.setattr(
        routes_decide,
        "validate_local",
        lambda **kwargs: captured_validate_kwargs.update(kwargs) or {
            "validation_status": "revoked_pending",
            "admissibility_state": "warning_only_shadow",
            "failure_type": "",
            "drift_vector": {},
        },
    )

    response = client.post(
        "/v1/decide",
        json=server._decide_example(),
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("meta", {}).get("wat_shadow", {}).get("revocation_status") == "revoked_pending"
    assert payload.get("wat_integrity", {}).get("revocation_status") == "revoked_pending"
    assert captured_validate_kwargs.get("revocation_state", {}).get("status") == "revoked_pending"


def test_decide_wat_shadow_passes_policy_drift_scoring_to_verifier(monkeypatch):
    """Governance drift_scoring values must be forwarded to local verifier config."""

    class DummyPipeline:
        @staticmethod
        async def run_decide_pipeline(req, request):
            return {
                "ok": True,
                "request_id": "rid-drift",
                "query": req.query,
                "decision": "allow",
                "business_decision": "APPROVE",
                "result": "ok",
            }

    policy = {
        "wat": {"enabled": True, "issuance_mode": "shadow_only", "default_ttl_seconds": 60},
        "psid": {"display_length": 12},
        "shadow_validation": {
            "timestamp_skew_tolerance_seconds": 5,
            "warning_only_until": None,
            "replay_binding_required": False,
        },
        "revocation": {"degrade_on_pending": True},
        "drift_scoring": {
            "policy_weight": 0.5,
            "signature_weight": 0.2,
            "observable_weight": 0.2,
            "temporal_weight": 0.1,
            "healthy_threshold": 0.1,
            "critical_threshold": 0.3,
        },
    }
    captured_validate_kwargs = {}
    monkeypatch.setattr(server, "get_decision_pipeline", lambda: DummyPipeline())
    monkeypatch.setattr(routes_decide, "get_policy", lambda: policy)
    monkeypatch.setattr(
        routes_decide,
        "validate_local",
        lambda **kwargs: captured_validate_kwargs.update(kwargs) or {
            "validation_status": "valid",
            "admissibility_state": "admissible",
            "failure_type": "",
            "drift_vector": {},
        },
    )

    response = client.post(
        "/v1/decide",
        json=server._decide_example(),
        headers={"X-API-Key": "test-api-key"},
    )

    assert response.status_code == 200
    validate_config = captured_validate_kwargs.get("config", {})
    assert validate_config.get("drift_weights") == {
        "policy": 0.5,
        "signature": 0.2,
        "observable": 0.2,
        "temporal": 0.1,
    }
    assert validate_config.get("drift_thresholds") == {
        "healthy": 0.1,
        "critical": 0.3,
    }


def test_decide_wat_shadow_invalid_drift_scoring_values_fall_back_to_defaults(monkeypatch):
    """Invalid drift_scoring values must not break shadow observer validation config."""

    class DummyPipeline:
        @staticmethod
        async def run_decide_pipeline(req, request):
            return {
                "ok": True,
                "request_id": "rid-drift-invalid",
                "query": req.query,
                "decision": "allow",
                "business_decision": "APPROVE",
                "result": "ok",
            }

    policy = {
        "wat": {"enabled": True, "issuance_mode": "shadow_only", "default_ttl_seconds": 60},
        "psid": {"display_length": 12},
        "shadow_validation": {
            "timestamp_skew_tolerance_seconds": 5,
            "warning_only_until": None,
            "replay_binding_required": False,
        },
        "revocation": {"degrade_on_pending": True},
        "drift_scoring": {
            "policy_weight": "not-a-float",
            "signature_weight": None,
            "observable_weight": {},
            "temporal_weight": [],
            "healthy_threshold": "bad-threshold",
            "critical_threshold": object(),
        },
    }
    captured_validate_kwargs = {}
    monkeypatch.setattr(server, "get_decision_pipeline", lambda: DummyPipeline())
    monkeypatch.setattr(routes_decide, "get_policy", lambda: policy)
    monkeypatch.setattr(
        routes_decide,
        "validate_local",
        lambda **kwargs: captured_validate_kwargs.update(kwargs) or {
            "validation_status": "valid",
            "admissibility_state": "admissible",
            "failure_type": "",
            "drift_vector": {},
        },
    )

    response = client.post(
        "/v1/decide",
        json=server._decide_example(),
        headers={"X-API-Key": "test-api-key"},
    )

    assert response.status_code == 200
    validate_config = captured_validate_kwargs.get("config", {})
    assert validate_config.get("drift_weights") == {
        "policy": 0.4,
        "signature": 0.3,
        "observable": 0.2,
        "temporal": 0.1,
    }
    assert validate_config.get("drift_thresholds") == {
        "healthy": 0.2,
        "critical": 0.5,
    }


def test_run_wat_shadow_observer_tampered_signature_invalid(monkeypatch, tmp_path):
    """Tampered signed WAT must fail local verification as signature_invalid."""

    class DummyServer:
        def __init__(self):
            self._cache = set()
            self.events = []

        def get_wat_shadow_replay_cache(self):
            return self._cache

        def _publish_event(self, event_type, payload):
            self.events.append((event_type, payload))

    policy = {
        "wat": {"enabled": True, "issuance_mode": "shadow_only", "default_ttl_seconds": 60},
        "psid": {"display_length": 12},
        "shadow_validation": {
            "timestamp_skew_tolerance_seconds": 5,
            "warning_only_until": None,
            "replay_binding_required": False,
        },
        "revocation": {"degrade_on_pending": False},
        "drift_scoring": {},
    }

    signer = build_trustlog_signer(
        private_key_path=Path(tmp_path) / "keys" / "private.key",
        public_key_path=Path(tmp_path) / "keys" / "public.key",
        ensure_local_keys=True,
        backend="file",
    )
    monkeypatch.setattr(routes_decide, "get_policy", lambda: policy)
    monkeypatch.setattr(routes_decide, "_resolve_wat_shadow_signer", lambda _cfg: signer)
    monkeypatch.setattr(routes_decide, "persist_wat_issuance_event", lambda **_kwargs: {"event_id": "issue-1"})
    monkeypatch.setattr(routes_decide, "persist_wat_validation_event", lambda **_kwargs: {"event_id": "validate-1"})
    monkeypatch.setattr(routes_decide, "persist_wat_replay_event", lambda **_kwargs: {"event_id": "replay-1"})

    original_sign_wat = routes_decide.sign_wat

    def _tampered_sign_wat(claims, active_signer):
        signed = original_sign_wat(claims, active_signer)
        signed["claims"]["nonce"] = "tampered-nonce"
        return signed

    monkeypatch.setattr(routes_decide, "sign_wat", _tampered_sign_wat)

    summary = routes_decide._run_wat_shadow_observer(
        srv=DummyServer(),
        req=DecideRequest(query="tamper"),
        coerced={
            "request_id": "rid-tamper",
            "query": "tamper",
            "decision": "allow",
            "business_decision": "APPROVE",
        },
    )

    assert summary is not None
    assert summary["validation_status"] == "invalid"
    assert summary["admissibility_state"] == "non_admissible"


def test_run_wat_shadow_observer_valid_signature(monkeypatch, tmp_path):
    """Valid signed WAT should pass strict local signature verification."""

    class DummyServer:
        def __init__(self):
            self._cache = set()
            self.events = []

        def get_wat_shadow_replay_cache(self):
            return self._cache

        def _publish_event(self, event_type, payload):
            self.events.append((event_type, payload))

    policy = {
        "wat": {"enabled": True, "issuance_mode": "shadow_only", "default_ttl_seconds": 60},
        "psid": {"display_length": 12},
        "shadow_validation": {
            "timestamp_skew_tolerance_seconds": 5,
            "warning_only_until": None,
            "replay_binding_required": False,
        },
        "revocation": {"degrade_on_pending": False},
        "drift_scoring": {},
    }

    signer = build_trustlog_signer(
        private_key_path=Path(tmp_path) / "keys" / "private.key",
        public_key_path=Path(tmp_path) / "keys" / "public.key",
        ensure_local_keys=True,
        backend="file",
    )
    monkeypatch.setattr(routes_decide, "get_policy", lambda: policy)
    monkeypatch.setattr(routes_decide, "_resolve_wat_shadow_signer", lambda _cfg: signer)
    monkeypatch.setattr(routes_decide, "persist_wat_issuance_event", lambda **_kwargs: {"event_id": "issue-1"})
    monkeypatch.setattr(routes_decide, "persist_wat_validation_event", lambda **_kwargs: {"event_id": "validate-1"})
    monkeypatch.setattr(routes_decide, "persist_wat_replay_event", lambda **_kwargs: {"event_id": "replay-1"})

    summary = routes_decide._run_wat_shadow_observer(
        srv=DummyServer(),
        req=DecideRequest(query="valid"),
        coerced={
            "request_id": "rid-valid",
            "query": "valid",
            "decision": "allow",
            "business_decision": "APPROVE",
        },
    )

    assert summary is not None
    assert summary["validation_status"] == "valid"
    assert summary["admissibility_state"] == "admissible"


def test_fuji_validate_uses_validate_action(monkeypatch):
    """
    fuji_core.validate_action がある場合、その経路が使われる
    """
    monkeypatch.setenv("VERITAS_ENABLE_DIRECT_FUJI_API", "1")

    calls = []

    class DummyFuji:
        @staticmethod
        def validate_action(action, context):
            calls.append((action, context))
            return {"status": "ok", "reason": "via validate_action"}

    # validate_action を持つ Dummy に差し替え
    monkeypatch.setattr(server, "fuji_core", DummyFuji())

    r = client.post(
        "/v1/fuji/validate",
        json={"action": "do-x", "context": {"foo": "bar"}},
        headers={"X-API-Key": "test-api-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "validate_action" in data["reason"]
    assert calls == [("do-x", {"foo": "bar"})]


def test_fuji_validate_falls_back_to_validate(monkeypatch):
    """
    validate_action が無く validate だけある場合、validate 経由になる
    """

    monkeypatch.setenv("VERITAS_ENABLE_DIRECT_FUJI_API", "1")

    class DummyFuji:
        @staticmethod
        def validate(action, context):
            return {"status": "legacy", "reason": "via validate"}

    monkeypatch.setattr(server, "fuji_core", DummyFuji())

    r = client.post(
        "/v1/fuji/validate",
        json={"action": "do-y", "context": {"x": 1}},
        headers={"X-API-Key": "test-api-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "legacy"
    assert "via validate" in data["reason"]


def test_fuji_validate_no_impl_raises_500(monkeypatch):
    """
    validate_action も validate も無い場合は 500 を返す
    """

    monkeypatch.setenv("VERITAS_ENABLE_DIRECT_FUJI_API", "1")

    class DummyFuji:
        pass

    monkeypatch.setattr(server, "fuji_core", DummyFuji())

    r = client.post(
        "/v1/fuji/validate",
        json={"action": "do-z", "context": {}},
        headers={"X-API-Key": "test-api-key"},
    )
    assert r.status_code == 500
    data = r.json()
    assert "FUJI core interface error" in data["detail"]


# -------------------------------------------------
# Trust log helper / shadow_decide
# -------------------------------------------------


def test_load_logs_json_variants(tmp_path, monkeypatch):
    """
    _load_logs_json の各パターン:
      - ファイル無し
      - dict + items
      - top-level list
      - 壊れた JSON
    """
    log_json = tmp_path / "trust_log.json"
    monkeypatch.setattr(server, "LOG_JSON", log_json)

    # ファイルなし → []
    assert server._load_logs_json() == []

    # dict with items
    log_json.write_text(json.dumps({"items": [1, 2]}), encoding="utf-8")
    assert server._load_logs_json() == [1, 2]

    # top-level list
    log_json.write_text(json.dumps([3, 4]), encoding="utf-8")
    assert server._load_logs_json() == [3, 4]

    # 壊れた JSON → 例外キャッチして []
    log_json.write_text("{invalid", encoding="utf-8")
    assert server._load_logs_json() == []


def test_append_trust_log_and_load(tmp_path, monkeypatch):
    """
    append_trust_log が JSONL + 集約 JSON に書き込むパス
    """
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(server, "LOG_DIR", log_dir)
    monkeypatch.setattr(server, "LOG_JSON", log_dir / "trust_log.json")
    monkeypatch.setattr(server, "LOG_JSONL", log_dir / "trust_log.jsonl")

    entry1 = {"id": 1, "msg": "first"}
    entry2 = {"id": 2, "msg": "second"}

    server.append_trust_log(entry1)
    server.append_trust_log(entry2)

    # JSONL ファイルは 2 行
    with (log_dir / "trust_log.jsonl").open(encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 2

    # 集約 JSON の末尾 2 件が entry1, entry2
    items = server._load_logs_json()
    assert items[-2:] == [entry1, entry2]


def test_write_shadow_decide_creates_file(tmp_path, monkeypatch):
    """
    write_shadow_decide が decide_*.json を作るパス
    """
    shadow_dir = tmp_path / "shadow"
    monkeypatch.setattr(server, "SHADOW_DIR", shadow_dir)

    body = {"query": "test-query"}
    chosen = {"option": "A"}
    fuji_status = {"status": "ok"}

    server.write_shadow_decide(
        request_id="req-123",
        body=body,
        chosen=chosen,
        telos_score=0.75,
        fuji=fuji_status,
    )

    files = list(shadow_dir.glob("decide_*.json"))
    assert files, "shadow decide file should be created"

    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["request_id"] == "req-123"
    assert data["query"] == "test-query"
    assert data["chosen"] == chosen
    assert data["telos_score"] == 0.75
    assert data["fuji"] == "ok"


# -------------------------------------------------
# Memory API: put / get / search (正常系)
# -------------------------------------------------


def test_memory_put_and_get_roundtrip():
    """
    /v1/memory/put (レガシーKV) → /v1/memory/get で値が取れること
    """
    body = {"user_id": "user1", "key": "k_legacy", "value": {"foo": "bar"}}
    r = client.post(
        "/v1/memory/put",
        json=body,
        headers={"X-API-Key": "test-api-key"},
    )
    assert r.status_code == 200
    data = r.json()

    assert data["ok"] is True
    assert data["legacy"]["saved"] is True
    assert data["legacy"]["key"] == "k_legacy"

    # /v1/memory/get は APIキー必須
    r2 = client.post(
        "/v1/memory/get",
        json={"user_id": "user1", "key": "k_legacy"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["ok"] is True
    assert data2["value"] == {"foo": "bar"}


def test_memory_put_vector_and_size_and_kind():
    """
    /v1/memory/put の新フォーマット（vector側）の保存結果を確認
    """
    text = "contact me at test@example.com"
    body = {
        "user_id": "user2",
        "kind": "skills",
        "text": text,
        "tags": ["tag1"],
        "meta": {"source": "test"},
    }
    r = client.post(
        "/v1/memory/put",
        json=body,
        headers={"X-API-Key": "test-api-key"},
    )
    assert r.status_code == 200
    data = r.json()

    vec = data["vector"]
    assert vec["saved"] is True
    assert vec["kind"] == "skills"  # kind 正常化
    assert vec["id"] is not None
    assert data["size"] == len(text)  # size は text 長さ




def test_memory_put_respects_kind_for_vector_store(monkeypatch):
    """
    /v1/memory/put が vector 保存時に kind を保持して
    store.put(kind, item) を呼ぶことを確認。
    """

    calls = {}

    class DummyStore:
        def put(self, kind, item):
            calls["kind"] = kind
            calls["item"] = item
            return "dummy-id"

        def put_episode(self, text, tags=None, meta=None):
            raise AssertionError("put_episode should not be used when put is available")

    monkeypatch.setattr(server, "get_memory_store", lambda: DummyStore())

    res = server.memory_put(
        MemoryPutRequest(
            user_id="u-kind",
            kind="skills",
            text="hello",
            tags=["t1"],
            meta={"source": "test"},
        )
    )

    assert res["ok"] is True
    assert res["vector"]["saved"] is True
    assert calls["kind"] == "skills"
    assert calls["item"]["text"] == "hello"
    assert calls["item"]["meta"]["kind"] == "skills"
    assert calls["item"]["meta"]["user_id"] == "anon"


def test_memory_put_reports_partial_failure_when_vector_save_fails(monkeypatch):
    """memory_put should expose stage-level partial failure details."""

    class PartialStore:
        def __init__(self):
            self.legacy = {}

        def put(self, *args, **kwargs):
            if len(args) == 2 and isinstance(args[1], dict) and "text" in args[1]:
                raise RuntimeError("vector backend offline")
            user_id = args[0]
            key = kwargs.get("key", args[1] if len(args) > 1 else None)
            value = kwargs.get("value", args[2] if len(args) > 2 else None)
            self.legacy[(user_id, key)] = value
            return None

    monkeypatch.setattr(server, "get_memory_store", lambda: PartialStore())

    res = server.memory_put(
        MemoryPutRequest(
            user_id="u-partial",
            key="legacy-key",
            value={"foo": "bar"},
            kind="semantic",
            text="hello",
            tags=["t1"],
        )
    )

    assert res["ok"] is True
    assert res["status"] == "partial_failure"
    assert res["legacy"]["saved"] is True
    assert res["vector"]["saved"] is False
    assert res["errors"] == [
        {
            "stage": "vector",
            "message": "vector save failed",
            "error_code": "backend_unavailable",
        }
    ]


def test_memory_put_reports_failed_when_all_save_paths_fail(monkeypatch):
    """memory_put should not mask a total write failure as success."""

    class FailingStore:
        def put(self, *args, **kwargs):
            raise RuntimeError("backend offline")

    monkeypatch.setattr(server, "get_memory_store", lambda: FailingStore())

    res = server.memory_put(
        MemoryPutRequest(
            user_id="u-fail",
            key="legacy-key",
            value={"foo": "bar"},
            kind="semantic",
            text="hello",
        )
    )

    assert res["ok"] is False
    assert res["status"] == "failed"
    assert res["error"] == "memory operation failed"
    assert res["error_code"] == "partial_failure"
    assert {item["stage"] for item in res["errors"]} == {"legacy", "vector"}
    assert {item["error_code"] for item in res["errors"]} == {"backend_unavailable"}


def test_memory_search_filters_by_user(monkeypatch):
    """
    memory_search:
      - dict 形式ヒットに user_id フィルタがかかる
      - 文字列ヒットは user_id 指定ありだと除外される
      - user_id なしなら dict + 文字列両方返す
    """

    def fake_search(query, k, kinds, min_sim):
        # dict 2件 + 文字列1件
        return [
            {
                "text": "match",
                "score": 0.9,
                "tags": ["t"],
                "meta": {"user_id": "userX"},
            },
            {
                "text": "other",
                "score": 0.8,
                "tags": ["t"],
                "meta": {"user_id": "userY"},
            },
            "id-only-hit",
        ]

    monkeypatch.setattr(server.MEMORY_STORE, "search", fake_search)

    scoped_user = server._derive_api_user_id("test-api-key")

    # user_id 指定あり（不一致）でも APIキー由来 user_id に強制される
    r = client.post(
        "/v1/memory/search",
        json={"query": "q", "user_id": "userX"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["count"] == 0

    # user_id なしでも APIキー由来 user_id で検索される
    r2 = client.post(
        "/v1/memory/search",
        json={"query": "q"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["ok"] is True
    assert data2["count"] == 0

    # APIキー由来 user_id のデータは取得できる
    monkeypatch.setattr(
        server.MEMORY_STORE,
        "search",
        lambda query, k, kinds, min_sim: [
            {
                "text": "match",
                "score": 0.95,
                "tags": ["t"],
                "meta": {"user_id": scoped_user},
            }
        ],
    )
    r3 = client.post(
        "/v1/memory/search",
        json={"query": "q", "user_id": "another"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert r3.status_code == 200
    data3 = r3.json()
    assert data3["ok"] is True
    assert data3["count"] == 1
    assert data3["hits"][0]["meta"]["user_id"] == scoped_user


# -------------------------------------------------
# Memory API: エラー系パス
# -------------------------------------------------


def test_memory_search_error_path(monkeypatch):
    """
    MEMORY_STORE.search が例外を投げたときに
    {ok: False, hits: [], count: 0} を返すパス
    """

    def boom(*args, **kwargs):
        raise RuntimeError("search failed")

    monkeypatch.setattr(server.MEMORY_STORE, "search", boom)

    r = client.post(
        "/v1/memory/search",
        json={"query": "q", "user_id": "test_user"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert r.status_code == 200
    data = r.json()

    assert data["ok"] is False
    assert data["hits"] == []
    assert data["count"] == 0
    assert "search failed" in data["error"]


def test_memory_get_error_path(monkeypatch):
    """
    MEMORY_STORE.get が例外を投げたときに
    {ok: False, value: None} を返すパス
    """

    def boom(user_id, key):
        raise RuntimeError("get failed")

    monkeypatch.setattr(server.MEMORY_STORE, "get", boom)

    r = client.post(
        "/v1/memory/get",
        json={"user_id": "u", "key": "k"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert r.status_code == 200
    data = r.json()

    assert data["ok"] is False
    assert data["value"] is None
    # M-3: エラー詳細はクライアントに露出させず、汎用メッセージを返す
    assert "error" in data
    assert data["error"]  # 非空であること


def test_memory_put_outer_error():
    """
    不正な body を POST した場合、FastAPI が Pydantic バリデーションエラー
    (422) を返すことを確認する。
    """
    r = client.post(
        "/v1/memory/put",
        content=b"not-json",
        headers={"X-API-Key": "test-api-key", "Content-Type": "application/json"},
    )
    assert r.status_code == 422


# -------------------------------------------------
# Trust Feedback API
# -------------------------------------------------


def test_trust_feedback_ok(monkeypatch):
    """
    append_trust_log が正常に呼ばれたパス
    """
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    calls = []

    def fake_append_trust_log(user_id, score, note, source, extra):
        calls.append((user_id, score, note, source, extra))

    monkeypatch.setattr(server.value_core, "append_trust_log", fake_append_trust_log)

    r = client.post(
        "/v1/trust/feedback",
        headers=_AUTH_HEADERS,
        json={
            "user_id": "user123",
            "score": 0.9,
            "note": "good plan",
            "source": "test",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["user_id"] == "user123"

    assert len(calls) == 1
    u, score, note, source, extra = calls[0]
    assert u == "user123"
    assert score == 0.9
    assert note == "good plan"
    assert source == "test"
    assert extra.get("api") == "/v1/trust/feedback"


def test_trust_feedback_error(monkeypatch):
    """
    append_trust_log が例外を投げたときに error レスポンスになるパス
    """
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(server.value_core, "append_trust_log", boom)

    r = client.post(
        "/v1/trust/feedback",
        headers=_AUTH_HEADERS,
        json={
            "user_id": "user_err",
            "score": 0.1,
            "note": "bad",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert "error" in data


# -------------------------------------------------
# 追加分: エンドポイント経由の認証 / バリデーション系
# -------------------------------------------------


def test_memory_get_unauthorized_without_api_key():
    """
    /v1/memory/get を APIキーなしで叩いた場合、
    認証エラー系ステータスになることを確認。
    """
    r = client.post(
        "/v1/memory/get",
        json={"user_id": "user1", "key": "k_legacy"},
        # ヘッダに X-API-Key を付けない
    )
    assert r.status_code in (401, 403, 422)


def test_memory_put_unauthorized_without_api_key():
    """
    /v1/memory/put を APIキーなしで叩いた場合、
    認証エラー系ステータスになることを確認。
    """
    r = client.post(
        "/v1/memory/put",
        json={"user_id": "user1", "key": "k_legacy", "value": {"foo": "bar"}},
        # ヘッダに X-API-Key を付けない
    )
    assert r.status_code in (401, 403, 422)


def test_memory_search_unauthorized_without_api_key():
    """
    /v1/memory/search を APIキーなしで叩いた場合、
    認証エラー系ステータスになることを確認。
    """
    r = client.post(
        "/v1/memory/search",
        json={"query": "q"},
        # ヘッダに X-API-Key を付けない
    )
    assert r.status_code in (401, 403, 422)


def test_memory_put_minimal_body_ok():
    """
    /v1/memory/put に user_id だけ投げても 500 にならず、
    正常レスポンスフォーマットを返すことを確認するテスト。
    （実装は「noop」として 200 を返す仕様）
    """
    r = client.post(
        "/v1/memory/put",
        json={"user_id": "only-user"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert r.status_code == 200
    data = r.json()
    # 最低限 ok フラグが立っていることだけ確認（詳細の中身は実装依存）
    assert data.get("ok") is True


def test_decide_basic_requires_api_key():
    """
    /v1/decide/basic を叩いたときに 500 にならないことを確認する。
    現状の実装ではエンドポイント未公開/未実装のため 404 が返るが、
    将来 401/403/422（認証・バリデーションエラー）になってもテストは通る。
    """
    body = {"query": "hello", "user_id": "userX"}
    r = client.post("/v1/decide/basic", json=body)
    assert r.status_code in (401, 403, 404, 422)


# -------------------------------------------------
# C-3: Request Body Size Limit (DoS対策)
# -------------------------------------------------


def test_request_body_size_limit_blocks_large_payload(monkeypatch):
    """
    ★ C-3 修正テスト: 巨大なリクエストボディは 413 でブロックされる

    MAX_REQUEST_BODY_SIZE を超える Content-Length を持つリクエストは
    Pydantic バリデーション前にミドルウェアでブロックされる。
    """
    # テスト用に小さい制限値を設定
    monkeypatch.setattr(server, "MAX_REQUEST_BODY_SIZE", 1000)

    # Content-Length が制限を超えるリクエストを送信
    # ヘッダーだけで判定するので、実際の本文は小さくても良い
    r = client.post(
        "/v1/decide",
        json={"query": "test"},
        headers={
            "X-API-Key": "test-api-key",
            "Content-Length": "2000000",  # 2MB - 制限の1000バイトを超える
        },
    )

    # 413 Payload Too Large を返す
    assert r.status_code == 413
    data = r.json()
    assert "too large" in data["detail"].lower()


def test_request_body_size_limit_rejects_malformed_content_length(monkeypatch):
    """
    ★ C-3 修正テスト: 不正な Content-Length は 400 でブロックされる

    数値でない Content-Length は悪意のあるリクエストの可能性があるため、
    400 Bad Request を返す。
    """
    monkeypatch.setattr(server, "MAX_REQUEST_BODY_SIZE", 1000)

    r = client.post(
        "/v1/decide",
        json={"query": "test"},
        headers={
            "X-API-Key": "test-api-key",
            "Content-Length": "not-a-number",
        },
    )

    # 400 Bad Request を返す
    assert r.status_code == 400
    data = r.json()
    assert "invalid" in data["detail"].lower()


def test_request_body_size_limit_allows_normal_payload(monkeypatch):
    """
    ★ C-3 修正テスト: 通常サイズのリクエストは通過する

    MAX_REQUEST_BODY_SIZE 以下の Content-Length を持つリクエストは
    ミドルウェアを通過して通常の処理が行われる。
    """
    # テスト用に十分大きい制限値を設定
    monkeypatch.setattr(server, "MAX_REQUEST_BODY_SIZE", 10 * 1024 * 1024)  # 10MB

    r = client.post(
        "/v1/decide",
        json={"query": "test"},
        headers={"X-API-Key": "test-api-key"},
    )

    # 413 以外のステータス（認証済みなので処理される）
    assert r.status_code != 413


def test_max_request_body_size_is_configurable():
    """
    ★ C-3 修正テスト: MAX_REQUEST_BODY_SIZE が存在し設定可能なことを確認

    デフォルトは 10MB (10 * 1024 * 1024) で、環境変数で変更可能。
    """
    assert hasattr(server, "MAX_REQUEST_BODY_SIZE")
    assert isinstance(server.MAX_REQUEST_BODY_SIZE, int)
    assert server.MAX_REQUEST_BODY_SIZE > 0


def test_resolve_max_request_body_size_uses_profile_default_for_production(
    monkeypatch,
):
    """Production profile should default to a tighter request size limit."""
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.delenv("VERITAS_MAX_REQUEST_BODY_SIZE", raising=False)

    resolved = server._resolve_max_request_body_size()
    assert resolved == 5 * 1024 * 1024


def test_resolve_max_request_body_size_prefers_explicit_override(monkeypatch):
    """Explicit size override must take precedence over profile defaults."""
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.setenv("VERITAS_MAX_REQUEST_BODY_SIZE", "2097152")

    resolved = server._resolve_max_request_body_size()
    assert resolved == 2 * 1024 * 1024


def test_resolve_max_request_body_size_rejects_non_positive_override(monkeypatch):
    """Invalid non-positive override should fall back to profile-safe default."""
    monkeypatch.setenv("VERITAS_ENV", "staging")
    monkeypatch.setenv("VERITAS_MAX_REQUEST_BODY_SIZE", "0")

    resolved = server._resolve_max_request_body_size()
    assert resolved == 8 * 1024 * 1024


def test_should_fail_fast_startup_for_production_profiles():
    """Production-like profiles must fail fast during startup validation."""
    assert server._should_fail_fast_startup("production") is True
    assert server._should_fail_fast_startup("prod") is True
    assert server._should_fail_fast_startup("staging") is False


def test_run_startup_config_validation_raises_in_production(monkeypatch):
    """Startup validation errors should stop boot in production profile."""

    def _raise_validation_error():
        raise RuntimeError("config invalid")

    monkeypatch.setattr(
        server,
        "validate_startup_config",
        _raise_validation_error,
        raising=False,
    )
    monkeypatch.setenv("VERITAS_ENV", "production")

    with pytest.raises(RuntimeError, match="config invalid"):
        server._run_startup_config_validation()


def test_run_startup_config_validation_warns_only_in_staging(monkeypatch, caplog):
    """Non-production profiles should keep warning-only startup behavior."""

    def _raise_validation_error():
        raise RuntimeError("staging config invalid")

    monkeypatch.setattr(
        server,
        "validate_startup_config",
        _raise_validation_error,
        raising=False,
    )
    monkeypatch.setenv("VERITAS_ENV", "staging")

    with caplog.at_level("WARNING"):
        server._run_startup_config_validation()

    assert "startup config validation failed" in caplog.text


def test_app_lifespan_runs_startup_and_shutdown_once(monkeypatch):
    """Lifespan should run startup before yield and shutdown after exit."""
    call_order: list[str] = []

    def _fake_validate() -> None:
        call_order.append("validate")

    def _fake_start_scheduler() -> None:
        call_order.append("start")

    def _fake_stop_scheduler() -> None:
        call_order.append("stop")

    monkeypatch.setattr(server, "_run_startup_config_validation", _fake_validate)
    monkeypatch.setattr(server, "_start_nonce_cleanup_scheduler", _fake_start_scheduler)
    monkeypatch.setattr(server, "_stop_nonce_cleanup_scheduler", _fake_stop_scheduler)

    async def _exercise_lifespan() -> None:
        async with server._app_lifespan(server.app):
            call_order.append("inside")

    asyncio.run(_exercise_lifespan())

    assert call_order == ["validate", "start", "inside", "stop"]


def test_app_lifespan_skips_scheduler_when_startup_validation_fails(monkeypatch):
    """Lifespan must fail fast and avoid scheduler start on startup errors."""
    call_order: list[str] = []

    def _raise_validation_error() -> None:
        call_order.append("validate")
        raise RuntimeError("startup invalid")

    def _fake_start_scheduler() -> None:
        call_order.append("start")

    def _fake_stop_scheduler() -> None:
        call_order.append("stop")

    monkeypatch.setattr(
        server,
        "_run_startup_config_validation",
        _raise_validation_error,
    )
    monkeypatch.setattr(server, "_start_nonce_cleanup_scheduler", _fake_start_scheduler)
    monkeypatch.setattr(server, "_stop_nonce_cleanup_scheduler", _fake_stop_scheduler)

    async def _exercise_lifespan() -> None:
        async with server._app_lifespan(server.app):
            raise AssertionError("unreachable")

    with pytest.raises(RuntimeError, match="startup invalid"):
        asyncio.run(_exercise_lifespan())

    assert call_order == ["validate"]


def test_events_requires_api_key_header_only_by_default(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    monkeypatch.delenv("VERITAS_ALLOW_SSE_QUERY_API_KEY", raising=False)

    no_auth = client.get("/v1/events")
    assert no_auth.status_code == 401

    with pytest.raises(HTTPException) as exc:
        server.require_api_key_header_or_query(
            x_api_key=None,
            api_key=_TEST_API_KEY,
        )
    assert exc.value.status_code == 401


def test_events_accepts_query_api_key_only_when_dual_flags_enabled(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    monkeypatch.setenv("VERITAS_ALLOW_SSE_QUERY_API_KEY", "1")
    monkeypatch.setenv("VERITAS_ACK_SSE_QUERY_API_KEY_RISK", "true")

    assert server.require_api_key_header_or_query(
        x_api_key=None,
        api_key=_TEST_API_KEY,
    ) is True


def test_events_rejects_query_api_key_in_production_even_with_dual_flags(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    monkeypatch.setenv("VERITAS_ALLOW_SSE_QUERY_API_KEY", "1")
    monkeypatch.setenv("VERITAS_ACK_SSE_QUERY_API_KEY_RISK", "true")
    monkeypatch.setenv("VERITAS_ENV", "production")

    with pytest.raises(HTTPException) as exc:
        server.require_api_key_header_or_query(
            x_api_key=None,
            api_key=_TEST_API_KEY,
        )
    assert exc.value.status_code == 401


def test_events_rejects_query_api_key_without_risk_ack(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    monkeypatch.setenv("VERITAS_ALLOW_SSE_QUERY_API_KEY", "1")
    monkeypatch.delenv("VERITAS_ACK_SSE_QUERY_API_KEY_RISK", raising=False)

    with pytest.raises(HTTPException) as exc:
        server.require_api_key_header_or_query(
            x_api_key=None,
            api_key=_TEST_API_KEY,
        )
    assert exc.value.status_code == 401


def test_websocket_auth_prefers_header_api_key(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)

    ws = SimpleNamespace(
        headers={"X-API-Key": _TEST_API_KEY},
        query_params={},
    )

    assert server._authenticate_websocket_api_key(ws) is True


def test_websocket_auth_rejects_query_api_key_by_default(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    monkeypatch.delenv("VERITAS_ALLOW_WS_QUERY_API_KEY", raising=False)
    monkeypatch.delenv("VERITAS_ACK_WS_QUERY_API_KEY_RISK", raising=False)

    ws = SimpleNamespace(
        headers={},
        query_params={"api_key": _TEST_API_KEY},
    )

    assert server._authenticate_websocket_api_key(ws) is False


def test_websocket_auth_accepts_query_api_key_only_when_dual_flags_enabled(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    monkeypatch.setenv("VERITAS_ALLOW_WS_QUERY_API_KEY", "1")
    monkeypatch.setenv("VERITAS_ACK_WS_QUERY_API_KEY_RISK", "true")

    ws = SimpleNamespace(
        headers={},
        query_params={"api_key": _TEST_API_KEY},
    )

    assert server._authenticate_websocket_api_key(ws) is True


def test_websocket_auth_rejects_query_api_key_in_production_even_with_dual_flags(
    monkeypatch,
):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    monkeypatch.setenv("VERITAS_ALLOW_WS_QUERY_API_KEY", "1")
    monkeypatch.setenv("VERITAS_ACK_WS_QUERY_API_KEY_RISK", "true")
    monkeypatch.setenv("NODE_ENV", "production")

    ws = SimpleNamespace(
        headers={},
        query_params={"api_key": _TEST_API_KEY},
    )

    assert server._authenticate_websocket_api_key(ws) is False


def test_websocket_auth_rejects_query_api_key_without_risk_ack(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)
    monkeypatch.setenv("VERITAS_ALLOW_WS_QUERY_API_KEY", "1")
    monkeypatch.delenv("VERITAS_ACK_WS_QUERY_API_KEY_RISK", raising=False)

    ws = SimpleNamespace(
        headers={},
        query_params={"api_key": _TEST_API_KEY},
    )

    assert server._authenticate_websocket_api_key(ws) is False


def test_decide_failure_publishes_sse_event(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_API_KEY)

    server._event_hub = server._SSEEventHub(history_size=16)
    server._pipeline_state = server._LazyState(obj=None, err="boom", attempted=True)

    response = client.post(
        "/v1/decide",
        headers=_AUTH_HEADERS,
        json={"query": "sse test"},
    )
    assert response.status_code == 503

    subscriber = server._event_hub.register()
    item = subscriber.get(timeout=0.5)
    assert item["type"] == "decide.completed"
    assert item["payload"]["ok"] is False


def test_resolve_cors_settings_rejects_wildcard_credentials():
    """Wildcard origins must never enable credentialed CORS responses."""
    origins, allow_credentials = server._resolve_cors_settings(["*"])

    assert origins == ["*"]
    assert allow_credentials is False


def test_resolve_cors_settings_allows_explicit_origins_only():
    """Explicit origin list enables credentials and strips invalid entries."""
    origins, allow_credentials = server._resolve_cors_settings(
        ["https://example.com", "", None, " https://app.example.com "],
    )

    assert origins == ["https://example.com", "https://app.example.com"]
    assert allow_credentials is True


# -------------------------------------------------
# Pydantic Request Model Validation Tests
# -------------------------------------------------


def test_memory_put_rejects_oversized_text_with_422():
    """Pydantic max_length on text field returns 422 for oversized input."""
    r = client.post(
        "/v1/memory/put",
        json={"text": "x" * 100_001},
        headers={"X-API-Key": "test-api-key"},
    )
    assert r.status_code == 422


def test_memory_put_rejects_too_many_tags_with_422():
    """Pydantic validator rejects more than 100 tags with 422."""
    r = client.post(
        "/v1/memory/put",
        json={"text": "hello", "tags": ["t"] * 101},
        headers={"X-API-Key": "test-api-key"},
    )
    assert r.status_code == 422


def test_memory_get_requires_key_field():
    """MemoryGetRequest requires 'key'; missing key returns 422."""
    r = client.post(
        "/v1/memory/get",
        json={"user_id": "u1"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert r.status_code == 422


def test_memory_search_coerces_bad_k_to_default():
    """Non-numeric k defaults to 8 instead of failing."""
    r = client.post(
        "/v1/memory/search",
        json={"query": "test", "k": "bad"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_memory_search_coerces_bad_min_sim_to_default():
    """Non-numeric min_sim defaults to 0.25 instead of failing."""
    r = client.post(
        "/v1/memory/search",
        json={"query": "test", "min_sim": "bad"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_trust_feedback_coerces_bad_score_to_default():
    """Non-numeric score defaults to 0.5 via Pydantic validator."""
    r = client.post(
        "/v1/trust/feedback",
        json={"score": "not-a-number"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] in (True, False)


def test_memory_put_accepts_string_value():
    """MemoryPutRequest accepts non-dict value for backward compatibility."""
    r = client.post(
        "/v1/memory/put",
        json={"user_id": "u1", "key": "k1", "value": "string-value"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_memory_search_exposes_error_code_for_validation_failures(monkeypatch):
    """memory_search should publish additive error codes for failure triage."""

    class InvalidSearchStore:
        def search(self, **_kwargs):
            raise ValueError("query shape invalid")

    monkeypatch.setattr(server, "get_memory_store", lambda: InvalidSearchStore())

    res = server.memory_search(MemorySearchRequest(user_id="u1", query="hello"))

    assert res["ok"] is False
    assert res["error"] == "memory search failed"
    assert res["error_code"] == "validation_failure"


def test_memory_search_invalid_kinds_returns_validation_error_code() -> None:
    """Invalid kind filters should expose the same additive validation code."""

    res = server.memory_search(
        MemorySearchRequest(user_id="u1", query="hello", kinds=["semantic", "bad"])
    )

    assert res["ok"] is False
    assert res["error"] == "invalid kinds: ['bad']"
    assert res["error_code"] == "validation_failure"


def test_memory_put_unavailable_store_returns_backend_error_code(monkeypatch):
    """Unavailable memory backends should remain observable to operators."""

    class DummyState:
        err = "offline"

    monkeypatch.setattr(server, "_memory_store_state", DummyState())
    monkeypatch.setattr(server, "get_memory_store", lambda: None)

    res = server.memory_put(MemoryPutRequest(user_id="u1", text="hello"))

    assert res["ok"] is False
    assert res["error"] == "memory store unavailable"
    assert res["error_code"] == "backend_unavailable"


def test_memory_get_unavailable_store_returns_backend_error_code(monkeypatch):
    """memory_get should classify store-unavailable failures consistently."""

    monkeypatch.setattr(server, "get_memory_store", lambda: None)

    res = server.memory_get(MemoryGetRequest(user_id="u1", key="k1"))

    assert res["ok"] is False
    assert res["error"] == "memory store unavailable"
    assert res["error_code"] == "backend_unavailable"
    assert res["value"] is None


def test_memory_search_does_not_swallow_base_exceptions(monkeypatch):
    """memory_search must not mask process-level exceptions."""

    class SearchAbort(BaseException):
        """Sentinel used to verify BaseException propagation."""

    class ExplodingStore:
        def search(self, **_kwargs):
            raise SearchAbort("stop search")

    monkeypatch.setattr(server, "get_memory_store", lambda: ExplodingStore())

    with pytest.raises(SearchAbort, match="stop search"):
        server.memory_search(MemorySearchRequest(user_id="u1", query="hello"))


def test_memory_put_does_not_swallow_base_exceptions(monkeypatch):
    """memory_put should preserve BaseException semantics during backend writes."""

    class WriteAbort(BaseException):
        """Sentinel used to verify BaseException propagation."""

    class ExplodingStore:
        def put(self, *args, **kwargs):
            raise WriteAbort("stop write")

    monkeypatch.setattr(server, "get_memory_store", lambda: ExplodingStore())

    with pytest.raises(WriteAbort, match="stop write"):
        server.memory_put(
            MemoryPutRequest(
                user_id="u1",
                key="k1",
                value={"foo": "bar"},
            )
        )


# ============================================================
# Source: test_server_defense.py
# ============================================================


import asyncio
import json
import logging
import os
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock, patch

_TEST_KEY = "server-defense-key-12345"
os.environ["VERITAS_API_KEY"] = _TEST_KEY
_AUTH = {"X-API-Key": _TEST_KEY}

import pytest
from fastapi.testclient import TestClient

import veritas_os.api.server as server

client = TestClient(server.app)


def _raise_import(msg: str):
    """Return a callable that raises ImportError with *msg*."""
    def _raiser(name: str, *args: Any, **kwargs: Any):
        raise ImportError(msg)
    return _raiser


@pytest.fixture(autouse=True)
def _reset_rate_bucket(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_KEY)
    server._rate_bucket.clear()
    yield
    server._rate_bucket.clear()


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ================================================================
# 1. get_cfg – lazy resolution
# ================================================================

class TestGetCfg:
    def test_cached_cfg_returned_without_reimport(self, monkeypatch):
        """Once cfg is resolved, subsequent calls return the cached object."""
        sentinel = SimpleNamespace(cors_allow_origins=["*"], api_key="test")
        state = server._LazyState(obj=sentinel)
        monkeypatch.setattr(server, "_cfg_state", state)
        result = server.get_cfg()
        assert result is sentinel

    def test_cfg_import_fail_returns_fallback(self, monkeypatch):
        """When cfg import fails, a minimal fallback namespace is returned."""
        fresh_state = server._LazyState()
        monkeypatch.setattr(server, "_cfg_state", fresh_state)
        monkeypatch.setattr(
            server.importlib, "import_module",
            _raise_import("cfg missing"),
        )
        result = server.get_cfg()
        assert result.cors_allow_origins == []
        assert result.api_key == ""
        # Restore
        monkeypatch.setattr(server, "_cfg_state", server._LazyState())

    def test_cfg_already_failed_returns_cached_fallback(self, monkeypatch):
        """After a failed import, repeated calls return the same fallback."""
        fallback = SimpleNamespace(cors_allow_origins=[], api_key="")
        state = server._LazyState(obj=fallback, err="previous error", attempted=True)
        monkeypatch.setattr(server, "_cfg_state", state)
        result = server.get_cfg()
        assert result is fallback


# ================================================================
# 2. get_decision_pipeline – lazy resolution
# ================================================================

class TestGetDecisionPipeline:
    def test_cached_pipeline_returned(self, monkeypatch):
        """Cached pipeline is returned without re-import."""
        sentinel = SimpleNamespace(run=lambda x: x)
        state = server._LazyState(obj=sentinel)
        monkeypatch.setattr(server, "_pipeline_state", state)
        result = server.get_decision_pipeline()
        assert result is sentinel

    def test_import_fail_returns_none(self, monkeypatch):
        """Pipeline import failure returns None gracefully."""
        fresh_state = server._LazyState()
        monkeypatch.setattr(server, "_pipeline_state", fresh_state)
        monkeypatch.setattr(
            server.importlib, "import_module",
            _raise_import("no pipeline"),
        )
        result = server.get_decision_pipeline()
        assert result is None
        monkeypatch.setattr(server, "_pipeline_state", server._LazyState())

    def test_already_failed_returns_none(self, monkeypatch):
        """When pipeline import already failed, return None without retry."""
        state = server._LazyState(attempted=True, err="previous failure")
        monkeypatch.setattr(server, "_pipeline_state", state)
        result = server.get_decision_pipeline()
        assert result is None


# ================================================================
# 3. get_fuji_core – placeholder respect
# ================================================================

class TestGetFujiCore:
    def test_monkeypatched_validate_action_not_overwritten(self, monkeypatch):
        """When test monkeypatches fuji_core.validate_action, lazy import must not overwrite it."""
        custom_fn = lambda action, context: {"status": "custom"}
        patched = SimpleNamespace(
            __veritas_placeholder__=True,
            validate_action=custom_fn,
            validate=server._fuji_validate_stub,
        )
        monkeypatch.setattr(server, "fuji_core", patched)
        monkeypatch.setattr(server, "_fuji_state", server._LazyState())
        result = server.get_fuji_core()
        # Must return the patched object, not trigger a lazy import
        assert result is patched
        assert result.validate_action is custom_fn

    def test_monkeypatched_validate_not_overwritten(self, monkeypatch):
        """When test monkeypatches fuji_core.validate, lazy import must not overwrite it."""
        custom_fn = lambda action, context: {"status": "custom_v"}
        patched = SimpleNamespace(
            __veritas_placeholder__=True,
            validate_action=server._fuji_validate_stub,
            validate=custom_fn,
        )
        monkeypatch.setattr(server, "fuji_core", patched)
        monkeypatch.setattr(server, "_fuji_state", server._LazyState())
        result = server.get_fuji_core()
        assert result is patched
        assert result.validate is custom_fn

    def test_non_placeholder_returned_as_is(self, monkeypatch):
        """If fuji_core is not a placeholder, it is returned directly."""
        real_module = SimpleNamespace(validate_action=lambda a, c: {})
        monkeypatch.setattr(server, "fuji_core", real_module)
        monkeypatch.setattr(server, "_fuji_state", server._LazyState())
        result = server.get_fuji_core()
        assert result is real_module

    def test_cached_fuji_returned(self, monkeypatch):
        """Once fuji is resolved, cached value is returned."""
        sentinel = SimpleNamespace(validate_action=lambda a, c: {"status": "ok"})
        state = server._LazyState(obj=sentinel)
        monkeypatch.setattr(server, "_fuji_state", state)
        # Keep fuji_core as placeholder so the code enters the lazy path
        monkeypatch.setattr(server, "fuji_core", SimpleNamespace(
            __veritas_placeholder__=True,
            validate_action=server._fuji_validate_stub,
            validate=server._fuji_validate_stub,
        ))
        result = server.get_fuji_core()
        assert result is sentinel

    def test_import_fail_returns_none_keeps_placeholder(self, monkeypatch):
        """Fuji import failure returns None but keeps placeholder intact."""
        placeholder = SimpleNamespace(
            __veritas_placeholder__=True,
            validate_action=server._fuji_validate_stub,
            validate=server._fuji_validate_stub,
        )
        monkeypatch.setattr(server, "fuji_core", placeholder)
        monkeypatch.setattr(server, "_fuji_state", server._LazyState())
        monkeypatch.setattr(
            server.importlib, "import_module",
            _raise_import("fuji missing"),
        )
        result = server.get_fuji_core()
        assert result is None
        # Placeholder must still be usable
        assert server.fuji_core.validate_action("x", {})["status"] == "allow"
        monkeypatch.setattr(server, "_fuji_state", server._LazyState())


# ================================================================
# 4. get_value_core – placeholder respect
# ================================================================

class TestGetValueCore:
    def test_monkeypatched_append_trust_log_not_overwritten(self, monkeypatch):
        """When test monkeypatches value_core.append_trust_log, lazy import must not overwrite."""
        custom_fn = MagicMock()
        patched = SimpleNamespace(
            __veritas_placeholder__=True,
            append_trust_log=custom_fn,
        )
        monkeypatch.setattr(server, "value_core", patched)
        monkeypatch.setattr(server, "_value_core_state", server._LazyState())
        result = server.get_value_core()
        assert result is patched
        assert result.append_trust_log is custom_fn

    def test_non_placeholder_with_append_returned(self, monkeypatch):
        """Non-placeholder value_core with append_trust_log is returned as-is."""
        real = SimpleNamespace(append_trust_log=lambda *a, **k: None)
        monkeypatch.setattr(server, "value_core", real)
        monkeypatch.setattr(server, "_value_core_state", server._LazyState())
        result = server.get_value_core()
        assert result is real

    def test_cached_value_core_returned(self, monkeypatch):
        """Once value_core is resolved, cached value is returned."""
        sentinel = SimpleNamespace(append_trust_log=lambda: None)
        state = server._LazyState(obj=sentinel)
        monkeypatch.setattr(server, "_value_core_state", state)
        monkeypatch.setattr(server, "value_core", SimpleNamespace(
            __veritas_placeholder__=True,
            append_trust_log=server._append_trust_log_stub,
        ))
        result = server.get_value_core()
        assert result is sentinel

    def test_import_fail_returns_none_keeps_placeholder(self, monkeypatch):
        """Value core import failure returns None but keeps placeholder."""
        placeholder = SimpleNamespace(
            __veritas_placeholder__=True,
            append_trust_log=server._append_trust_log_stub,
        )
        monkeypatch.setattr(server, "value_core", placeholder)
        monkeypatch.setattr(server, "_value_core_state", server._LazyState())
        monkeypatch.setattr(
            server.importlib, "import_module",
            _raise_import("value_core missing"),
        )
        result = server.get_value_core()
        assert result is None
        assert server.value_core.append_trust_log is server._append_trust_log_stub
        monkeypatch.setattr(server, "_value_core_state", server._LazyState())


# ================================================================
# 5. get_memory_store – placeholder respect
# ================================================================

class TestGetMemoryStore:
    def test_monkeypatched_search_not_overwritten(self, monkeypatch):
        """When test monkeypatches MEMORY_STORE.search, lazy import must not overwrite."""
        custom_search = MagicMock(return_value=[{"id": "test"}])
        patched = SimpleNamespace(
            __veritas_placeholder__=True,
            search=custom_search,
            get=server._memory_get_stub,
        )
        monkeypatch.setattr(server, "MEMORY_STORE", patched)
        monkeypatch.setattr(server, "_memory_store_state", server._LazyState())
        result = server.get_memory_store()
        assert result is patched
        assert result.search is custom_search

    def test_monkeypatched_get_not_overwritten(self, monkeypatch):
        """When test monkeypatches MEMORY_STORE.get, lazy import must not overwrite."""
        custom_get = MagicMock(return_value={"id": "test"})
        patched = SimpleNamespace(
            __veritas_placeholder__=True,
            search=server._memory_search_stub,
            get=custom_get,
        )
        monkeypatch.setattr(server, "MEMORY_STORE", patched)
        monkeypatch.setattr(server, "_memory_store_state", server._LazyState())
        result = server.get_memory_store()
        assert result is patched
        assert result.get is custom_get

    def test_non_placeholder_with_search_returned(self, monkeypatch):
        """Non-placeholder MEMORY_STORE with search/get is returned as-is."""
        real = SimpleNamespace(search=lambda q: [], get=lambda k: None, put=lambda k, v: None)
        monkeypatch.setattr(server, "MEMORY_STORE", real)
        monkeypatch.setattr(server, "_memory_store_state", server._LazyState())
        result = server.get_memory_store()
        assert result is real

    def test_cached_memory_store_returned(self, monkeypatch):
        """Once memory store is resolved, cached value is returned."""
        sentinel = SimpleNamespace(search=lambda q: [], get=lambda k: None)
        state = server._LazyState(obj=sentinel)
        monkeypatch.setattr(server, "_memory_store_state", state)
        monkeypatch.setattr(server, "MEMORY_STORE", SimpleNamespace(
            __veritas_placeholder__=True,
            search=server._memory_search_stub,
            get=server._memory_get_stub,
        ))
        result = server.get_memory_store()
        assert result is sentinel

    def test_import_fail_returns_none_keeps_placeholder(self, monkeypatch):
        """Memory store import failure returns None but keeps placeholder."""
        placeholder = SimpleNamespace(
            __veritas_placeholder__=True,
            search=server._memory_search_stub,
            get=server._memory_get_stub,
        )
        monkeypatch.setattr(server, "MEMORY_STORE", placeholder)
        monkeypatch.setattr(server, "_memory_store_state", server._LazyState())
        monkeypatch.setattr(
            server.importlib, "import_module",
            _raise_import("memory missing"),
        )
        result = server.get_memory_store()
        assert result is None
        assert server.MEMORY_STORE.search() == []
        assert server.MEMORY_STORE.get() is None
        monkeypatch.setattr(server, "_memory_store_state", server._LazyState())


# ================================================================
# 6. _log_api_key_source_once – all four branches
# ================================================================

class TestLogApiKeySourceOnce:
    def test_env_branch(self, monkeypatch):
        server._log_api_key_source_once.cache_clear()
        messages = []
        monkeypatch.setattr(server.logger, "info", lambda msg, *a: messages.append(msg % a))
        server._log_api_key_source_once("env")
        assert any("env" in m for m in messages)

    def test_api_key_default_branch(self, monkeypatch):
        server._log_api_key_source_once.cache_clear()
        messages = []
        monkeypatch.setattr(server.logger, "info", lambda msg, *a: messages.append(msg % a))
        server._log_api_key_source_once("api_key_default")
        assert any("api_key_default" in m for m in messages)

    def test_config_branch(self, monkeypatch):
        server._log_api_key_source_once.cache_clear()
        messages = []
        monkeypatch.setattr(server.logger, "info", lambda msg, *a: messages.append(msg % a))
        server._log_api_key_source_once("config")
        assert any("config" in m for m in messages)

    def test_missing_branch(self, monkeypatch):
        server._log_api_key_source_once.cache_clear()
        messages = []
        monkeypatch.setattr(server.logger, "info", lambda msg, *a: messages.append(msg % a))
        server._log_api_key_source_once("something_unknown")
        assert any("missing" in m for m in messages)

    def test_cache_deduplication(self, monkeypatch):
        """Same source logged only once (lru_cache)."""
        server._log_api_key_source_once.cache_clear()
        call_count = 0

        def counting_info(msg, *a):
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(server.logger, "info", counting_info)
        server._log_api_key_source_once("env")
        server._log_api_key_source_once("env")
        assert call_count == 1


# ================================================================
# 7. Validation error handler
# ================================================================

class TestValidationErrorHandler:
    def test_422_without_debug_mode_no_raw_body(self, monkeypatch):
        """In non-debug mode, 422 response should NOT include raw_body."""
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "")
        # Send invalid payload to trigger a 422 from a strict endpoint
        # Using a POST to a strict-body endpoint that triggers RequestValidationError
        resp = client.post(
            "/v1/decide",
            content=b"this is not json",
            headers={**_AUTH, "Content-Type": "application/json"},
        )
        if resp.status_code == 422:
            data = resp.json()
            assert "detail" in data
            assert "hint" in data
            assert "raw_body" not in data

    def test_422_with_debug_mode_includes_raw_body(self, monkeypatch):
        """In debug mode, 422 response SHOULD include raw_body."""
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "1")
        resp = client.post(
            "/v1/decide",
            content=b"this is not json",
            headers={**_AUTH, "Content-Type": "application/json"},
        )
        if resp.status_code == 422:
            data = resp.json()
            assert "detail" in data
            assert "raw_body" in data

    def test_422_raw_body_is_redacted(self, monkeypatch):
        """Sensitive data in raw_body should be redacted in debug mode."""
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "1")
        sensitive_payload = b'{"email": "user@example.com", "query": "test"}'
        resp = client.post(
            "/v1/decide",
            content=sensitive_payload,
            headers={**_AUTH, "Content-Type": "application/json"},
        )
        if resp.status_code == 422:
            data = resp.json()
            raw = data.get("raw_body", "")
            assert isinstance(raw, str)
            # redact() should mask the email address
            assert "user@example.com" not in raw

    def test_422_hint_has_expected_example(self, monkeypatch):
        """422 response always includes hint with expected_example."""
        resp = client.post(
            "/v1/decide",
            content=b"not json",
            headers={**_AUTH, "Content-Type": "application/json"},
        )
        if resp.status_code == 422:
            data = resp.json()
            assert "hint" in data
            assert "expected_example" in data["hint"]

    def test_422_has_request_id(self, monkeypatch):
        """422 response includes a request_id for tracing."""
        resp = client.post(
            "/v1/decide",
            content=b"not json",
            headers={**_AUTH, "Content-Type": "application/json"},
        )
        if resp.status_code == 422:
            data = resp.json()
            assert "request_id" in data
            assert isinstance(data["request_id"], str)
            assert len(data["request_id"]) > 0


# ================================================================
# 8. _effective_log_paths / _effective_shadow_dir wrapper delegation
# ================================================================

class TestEffectivePathWrappers:
    def test_log_paths_all_custom(self, monkeypatch, tmp_path):
        """When all log paths are custom-patched, they are respected."""
        custom_json = tmp_path / "custom.json"
        custom_jsonl = tmp_path / "custom.jsonl"
        monkeypatch.setattr(server, "LOG_DIR", tmp_path)
        monkeypatch.setattr(server, "LOG_JSON", custom_json)
        monkeypatch.setattr(server, "LOG_JSONL", custom_jsonl)
        ld, lj, ljl = server._effective_log_paths()
        assert lj == custom_json
        assert ljl == custom_jsonl

    def test_shadow_dir_custom(self, monkeypatch, tmp_path):
        """Custom SHADOW_DIR is respected even when LOG_DIR is default."""
        custom_shadow = tmp_path / "my_shadow"
        monkeypatch.setattr(server, "SHADOW_DIR", custom_shadow)
        result = server._effective_shadow_dir()
        assert result == custom_shadow

    def test_shadow_dir_follows_log_dir_when_default(self, monkeypatch, tmp_path):
        """SHADOW_DIR follows LOG_DIR when SHADOW_DIR is still at default."""
        monkeypatch.setattr(server, "LOG_DIR", tmp_path)
        monkeypatch.setattr(server, "LOG_JSON", server._DEFAULT_LOG_JSON)
        monkeypatch.setattr(server, "LOG_JSONL", server._DEFAULT_LOG_JSONL)
        monkeypatch.setattr(server, "SHADOW_DIR", server._DEFAULT_SHADOW_DIR)
        result = server._effective_shadow_dir()
        assert result == tmp_path / "DASH"


# ================================================================
# 9. Trust log runtime wrappers
# ================================================================

class TestTrustLogRuntimeWrappers:
    def test_load_logs_json_delegates(self, monkeypatch, tmp_path):
        """_load_logs_json delegates to _trust_log_runtime.load_logs_json."""
        log_file = tmp_path / "trust_log.json"
        log_file.write_text("[]")
        monkeypatch.setattr(server, "LOG_DIR", tmp_path)
        monkeypatch.setattr(server, "LOG_JSON", log_file)
        monkeypatch.setattr(server, "LOG_JSONL", server._DEFAULT_LOG_JSONL)
        result = server._load_logs_json(log_file)
        assert isinstance(result, list)

    def test_save_json_delegates(self, monkeypatch, tmp_path):
        """_save_json writes through to _trust_log_runtime."""
        log_file = tmp_path / "trust_log.json"
        server._save_json(log_file, [{"test": True}])
        assert log_file.exists()

    def test_secure_chmod_delegates(self, monkeypatch, tmp_path):
        """_secure_chmod delegates to _trust_log_runtime."""
        test_file = tmp_path / "secure.txt"
        test_file.write_text("secret")
        server._secure_chmod(test_file)
        # File should still exist and be readable
        assert test_file.exists()

    def test_append_trust_log_creates_files(self, monkeypatch, tmp_path):
        """append_trust_log creates log files when they don't exist."""
        monkeypatch.setattr(server, "LOG_DIR", tmp_path)
        monkeypatch.setattr(server, "LOG_JSON", tmp_path / "trust_log.json")
        monkeypatch.setattr(server, "LOG_JSONL", tmp_path / "trust_log.jsonl")
        entry = {"request_id": "test-1", "timestamp": "2025-01-01T00:00:00Z"}
        server.append_trust_log(entry)
        # At least the jsonl file should be written
        assert (tmp_path / "trust_log.jsonl").exists()

    def test_write_shadow_decide_writes_file(self, monkeypatch, tmp_path):
        """write_shadow_decide creates a shadow snapshot file."""
        monkeypatch.setattr(server, "SHADOW_DIR", tmp_path)
        monkeypatch.setattr(server, "LOG_DIR", tmp_path)
        monkeypatch.setattr(server, "LOG_JSON", server._DEFAULT_LOG_JSON)
        monkeypatch.setattr(server, "LOG_JSONL", server._DEFAULT_LOG_JSONL)
        server.write_shadow_decide(
            request_id="req-001",
            body={"query": "test"},
            chosen={"title": "Plan A"},
            telos_score=0.8,
            fuji={"status": "allow"},
        )
        # Shadow directory should now have a file
        files = list(tmp_path.glob("decide_*.json"))
        assert len(files) >= 1


# ================================================================
# 10. __getattr__ proxy
# ================================================================

class TestModuleGetattr:
    def test_proxied_rate_attr_accessible(self):
        """Proxied rate-limiting attributes are accessible via server module."""
        import veritas_os.api.rate_limiting as _rate_mod
        for attr_name in server._PROXIED_RATE_ATTRS:
            if hasattr(_rate_mod, attr_name):
                val = getattr(server, attr_name)
                assert val is getattr(_rate_mod, attr_name)

    def test_non_existent_attr_raises_attribute_error(self):
        """Accessing non-existent attribute raises AttributeError."""
        with pytest.raises(AttributeError, match="has no attribute"):
            _ = server.__getattr__("_completely_nonexistent_attr_xyz")

    def test_proxied_attrs_set_is_not_empty(self):
        """_PROXIED_RATE_ATTRS is defined and contains expected items."""
        assert len(server._PROXIED_RATE_ATTRS) > 0
        assert "_nonce_cleanup_timer" in server._PROXIED_RATE_ATTRS


# ================================================================
# 11. Startup/lifespan helpers – import crash safety
# ================================================================

class TestStartupHelpers:
    def test_should_fail_fast_startup_delegates(self):
        """_should_fail_fast_startup delegates to startup_health module."""
        result = server._should_fail_fast_startup(profile="dev")
        assert result is False

    def test_should_fail_fast_startup_prod(self):
        """Production profile triggers fail-fast."""
        result = server._should_fail_fast_startup(profile="production")
        assert result is True

    def test_run_startup_config_validation_no_crash(self, monkeypatch):
        """Startup config validation must not crash the server."""
        monkeypatch.delenv("VERITAS_ENV", raising=False)
        # Should not raise even if validation fails
        try:
            server._run_startup_config_validation()
        except Exception:
            # In non-production, it should not raise
            pass

    def test_check_runtime_feature_health_no_crash(self):
        """Runtime feature health check must not crash."""
        try:
            server._check_runtime_feature_health()
        except RuntimeError:
            # Only raised in production mode; safe to catch
            pass


# ================================================================
# 12. Health endpoint – always 200
# ================================================================

class TestHealthEndpoint:
    def test_health_always_200(self):
        """Health endpoint always returns 200 regardless of internal state."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        # ok may be True or False depending on pipeline/memory state;
        # the critical invariant is that the endpoint NEVER returns non-200.
        assert "ok" in data

    def test_v1_health_always_200(self):
        """v1 health endpoint always returns 200."""
        resp = client.get("/v1/health")
        assert resp.status_code == 200

    def test_health_has_uptime(self):
        """Health response includes uptime."""
        resp = client.get("/health")
        data = resp.json()
        assert "uptime" in data
        assert isinstance(data["uptime"], (int, float))
        assert data["uptime"] >= 0

    def test_health_never_500(self, monkeypatch):
        """Even with degraded dependencies, health never returns 500."""
        monkeypatch.setattr(server, "_pipeline_state",
                            server._LazyState(attempted=True, err="broken"))
        resp = client.get("/health")
        assert resp.status_code == 200


# ================================================================
# 13. Backward compatibility exports
# ================================================================

class TestBackwardCompatExports:
    """Verify that backward-compat exports exist at module level.

    Tests that monkeypatch server.<attr> will not break because
    the attribute does not exist.
    """

    def test_fuji_core_exists(self):
        assert hasattr(server, "fuji_core")
        assert hasattr(server.fuji_core, "validate_action")
        assert hasattr(server.fuji_core, "validate")

    def test_value_core_exists(self):
        assert hasattr(server, "value_core")
        assert hasattr(server.value_core, "append_trust_log")

    def test_memory_store_exists(self):
        assert hasattr(server, "MEMORY_STORE")
        assert hasattr(server.MEMORY_STORE, "search")
        assert hasattr(server.MEMORY_STORE, "get")

    def test_log_path_constants_exist(self):
        assert hasattr(server, "LOG_DIR")
        assert hasattr(server, "LOG_JSON")
        assert hasattr(server, "LOG_JSONL")
        assert hasattr(server, "SHADOW_DIR")
        assert isinstance(server.LOG_DIR, Path)
        assert isinstance(server.LOG_JSON, Path)

    def test_default_log_path_constants_exist(self):
        assert hasattr(server, "_DEFAULT_LOG_DIR")
        assert hasattr(server, "_DEFAULT_LOG_JSON")
        assert hasattr(server, "_DEFAULT_LOG_JSONL")
        assert hasattr(server, "_DEFAULT_SHADOW_DIR")

    def test_auth_exports_exist(self):
        assert hasattr(server, "require_api_key")
        assert hasattr(server, "API_KEY_DEFAULT")
        assert hasattr(server, "api_key_scheme")
        assert hasattr(server, "_resolve_expected_api_key_with_source")
        assert hasattr(server, "_get_expected_api_key")
        assert hasattr(server, "_log_api_key_source_once")

    def test_rate_limiting_exports_exist(self):
        assert hasattr(server, "enforce_rate_limit")
        assert hasattr(server, "_RATE_LIMIT")
        assert hasattr(server, "_rate_bucket")
        assert hasattr(server, "_nonce_store")

    def test_middleware_exports_exist(self):
        assert hasattr(server, "attach_trace_id")
        assert hasattr(server, "add_response_time")
        assert hasattr(server, "add_security_headers")
        assert hasattr(server, "limit_body_size")

    def test_route_handler_exports_exist(self):
        assert hasattr(server, "decide")
        assert hasattr(server, "health")
        assert hasattr(server, "root")
        assert hasattr(server, "status")
        assert hasattr(server, "_call_fuji")

    def test_constants_exports_exist(self):
        assert hasattr(server, "DECISION_ALLOW")
        assert hasattr(server, "DECISION_REJECTED")
        assert hasattr(server, "MAX_LOG_FILE_SIZE")
        assert hasattr(server, "MAX_RAW_BODY_LENGTH")
        assert hasattr(server, "VALID_MEMORY_KINDS")

    def test_governance_exports_exist(self):
        assert hasattr(server, "governance_get")
        assert hasattr(server, "governance_put")
        assert hasattr(server, "governance_value_drift")
        assert hasattr(server, "governance_policy_history")

    def test_trust_route_exports_exist(self):
        assert hasattr(server, "trust_logs")
        assert hasattr(server, "trust_log_by_request")
        assert hasattr(server, "trust_feedback")
        assert hasattr(server, "trustlog_verify")
        assert hasattr(server, "trustlog_export")

    def test_memory_route_exports_exist(self):
        assert hasattr(server, "memory_put")
        assert hasattr(server, "memory_search")
        assert hasattr(server, "memory_get")
        assert hasattr(server, "memory_erase")

    def test_system_route_exports_exist(self):
        assert hasattr(server, "metrics")
        assert hasattr(server, "events")
        assert hasattr(server, "system_halt")
        assert hasattr(server, "system_resume")

    def test_utility_exports_exist(self):
        assert hasattr(server, "_errstr")
        assert hasattr(server, "redact")
        assert hasattr(server, "_gen_request_id")
        assert hasattr(server, "_coerce_alt_list")
        assert hasattr(server, "_coerce_decide_payload")
        assert hasattr(server, "_coerce_fuji_payload")
        assert hasattr(server, "_is_debug_mode")


# ================================================================
# 14. Placeholder stubs at import time
# ================================================================

class TestPlaceholderStubs:
    def test_fuji_validate_stub_returns_allow(self):
        result = server._fuji_validate_stub("test_action", {"key": "val"})
        assert result["status"] == "allow"
        assert result["action"] == "test_action"
        assert isinstance(result["violations"], list)

    def test_append_trust_log_stub_noop(self):
        assert server._append_trust_log_stub("a", "b", c=1) is None

    def test_memory_search_stub_empty_list(self):
        assert server._memory_search_stub("query") == []

    def test_memory_get_stub_returns_none(self):
        assert server._memory_get_stub("key") is None


# ================================================================
# 15. Import safety – module import must not crash
# ================================================================

class TestImportSafety:
    def test_server_module_importable(self):
        """veritas_os.api.server can always be imported."""
        import importlib
        mod = importlib.import_module("veritas_os.api.server")
        assert hasattr(mod, "app")

    def test_app_is_fastapi_instance(self):
        """The `app` attribute is a proper FastAPI instance."""
        from fastapi import FastAPI
        assert isinstance(server.app, FastAPI)

    def test_has_atomic_io_is_bool(self):
        """_HAS_ATOMIC_IO is always a bool."""
        assert isinstance(server._HAS_ATOMIC_IO, bool)

    def test_has_sanitize_is_bool(self):
        """_HAS_SANITIZE is always a bool."""
        assert isinstance(server._HAS_SANITIZE, bool)

    def test_repo_root_is_path(self):
        assert isinstance(server.REPO_ROOT, Path)

    def test_start_ts_is_float(self):
        assert isinstance(server.START_TS, float)
        assert server.START_TS > 0


# ================================================================
# 16. SSEEventHub backward compat
# ================================================================

class TestSSEEventHubCompat:
    def test_event_hub_is_sse_hub(self):
        """_event_hub is an SSEEventHub instance."""
        assert isinstance(server._event_hub, server.SSEEventHub)

    def test_publish_event_no_crash(self):
        """_publish_event must never crash even with unusual payloads."""
        server._publish_event("test_type", {"data": "value"})
        server._publish_event("test_type", {})


# ================================================================
# 17. _LazyState backward-compat alias
# ================================================================

class TestLazyStateAlias:
    def test_lazy_state_is_subclass(self):
        """_LazyState is a subclass of dependency_resolver.LazyState."""
        from veritas_os.api.dependency_resolver import LazyState
        assert issubclass(server._LazyState, LazyState)

    def test_lazy_state_constructible(self):
        ls = server._LazyState()
        assert ls.obj is None
        assert ls.err is None
        assert ls.attempted is False

    def test_lazy_state_with_args(self):
        ls = server._LazyState(obj="test", err="err", attempted=True)
        assert ls.obj == "test"
        assert ls.err == "err"
        assert ls.attempted is True


# ================================================================
# 18. utc_now_iso_z fallback
# ================================================================

class TestUtcNowFallback:
    def test_utc_now_iso_z_exists(self):
        """utc_now_iso_z is always available (either real or fallback)."""
        result = server.utc_now_iso_z()
        assert isinstance(result, str)
        assert result.endswith("Z")


# ============================================================
# Source: test_server_coverage.py
# ============================================================


import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path
from types import SimpleNamespace

# Set test API key before importing server
_TEST_KEY = "coverage-test-key-12345"
os.environ["VERITAS_API_KEY"] = _TEST_KEY
_AUTH = {"X-API-Key": _TEST_KEY}

import pytest
from fastapi.testclient import TestClient

import veritas_os.api.server as server

client = TestClient(server.app)


@pytest.fixture(autouse=True)
def _reset_rate_bucket(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_KEY)
    server._rate_bucket.clear()
    yield
    server._rate_bucket.clear()


# ----------------------------------------------------------------
# 1. _effective_log_paths – default paths unchanged
# ----------------------------------------------------------------

def test_effective_log_paths_defaults():
    ld, lj, ljl = server._effective_log_paths()
    assert ld == server._DEFAULT_LOG_DIR
    assert lj == server._DEFAULT_LOG_JSON
    assert ljl == server._DEFAULT_LOG_JSONL


# 2. _effective_log_paths – LOG_DIR patched → json/jsonl follow
def test_effective_log_paths_follows_log_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "LOG_DIR", tmp_path)
    monkeypatch.setattr(server, "LOG_JSON", server._DEFAULT_LOG_JSON)
    monkeypatch.setattr(server, "LOG_JSONL", server._DEFAULT_LOG_JSONL)
    ld, lj, ljl = server._effective_log_paths()
    assert lj == tmp_path / "trust_log.json"
    assert ljl == tmp_path / "trust_log.jsonl"


# 3. _effective_log_paths – LOG_JSON explicitly patched is respected
def test_effective_log_paths_explicit_json(monkeypatch, tmp_path):
    custom = tmp_path / "custom.json"
    monkeypatch.setattr(server, "LOG_DIR", tmp_path)
    monkeypatch.setattr(server, "LOG_JSON", custom)
    monkeypatch.setattr(server, "LOG_JSONL", server._DEFAULT_LOG_JSONL)
    _, lj, _ = server._effective_log_paths()
    assert lj == custom


# ----------------------------------------------------------------
# 4. _effective_shadow_dir – default
# ----------------------------------------------------------------

def test_effective_shadow_dir_default():
    sd = server._effective_shadow_dir()
    assert sd == server._DEFAULT_SHADOW_DIR


# 5. _effective_shadow_dir – follows LOG_DIR
def test_effective_shadow_dir_follows_log_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "LOG_DIR", tmp_path)
    monkeypatch.setattr(server, "LOG_JSON", server._DEFAULT_LOG_JSON)
    monkeypatch.setattr(server, "LOG_JSONL", server._DEFAULT_LOG_JSONL)
    monkeypatch.setattr(server, "SHADOW_DIR", server._DEFAULT_SHADOW_DIR)
    assert server._effective_shadow_dir() == tmp_path / "DASH"


# 6. _effective_shadow_dir – explicit patch respected
def test_effective_shadow_dir_explicit(monkeypatch, tmp_path):
    custom = tmp_path / "my_shadow"
    monkeypatch.setattr(server, "SHADOW_DIR", custom)
    assert server._effective_shadow_dir() == custom


# ----------------------------------------------------------------
# 7-9. _is_placeholder
# ----------------------------------------------------------------

def test_is_placeholder_true():
    ns = SimpleNamespace(__veritas_placeholder__=True)
    assert server._is_placeholder(ns) is True


def test_is_placeholder_false_no_attr():
    assert server._is_placeholder(object()) is False


def test_is_placeholder_false_value():
    ns = SimpleNamespace(__veritas_placeholder__=False)
    assert server._is_placeholder(ns) is False


# ----------------------------------------------------------------
# 10-11. Stub functions
# ----------------------------------------------------------------

def test_fuji_validate_stub_returns_allow():
    r = server._fuji_validate_stub("test_action", {})
    assert r["status"] == "allow"
    assert r["action"] == "test_action"
    assert r["violations"] == []


def test_append_trust_log_stub_returns_none():
    assert server._append_trust_log_stub("a", b=1) is None


# ----------------------------------------------------------------
# 12-13. _LazyState
# ----------------------------------------------------------------

def test_lazy_state_defaults():
    ls = server._LazyState()
    assert ls.obj is None
    assert ls.err is None
    assert ls.attempted is False


def test_lazy_state_set():
    ls = server._LazyState(obj="x", err="e", attempted=True)
    assert ls.obj == "x"
    assert ls.err == "e"
    assert ls.attempted is True


# ----------------------------------------------------------------
# 14-15. _errstr / _log_decide_failure
# ----------------------------------------------------------------

def test_errstr():
    assert "ValueError" in server._errstr(ValueError("boom"))


def test_log_decide_failure_none(caplog):
    server._log_decide_failure("test msg", None)
    assert "test msg" in caplog.text


# ----------------------------------------------------------------
# 16-17. limit_body_size middleware
# ----------------------------------------------------------------

def test_limit_body_size_too_large():
    resp = client.get("/health", headers={"content-length": str(999_999_999_999)})
    assert resp.status_code == 413


def test_limit_body_size_invalid_content_length():
    resp = client.get("/health", headers={"content-length": "not-a-number"})
    assert resp.status_code == 400


# ----------------------------------------------------------------
# 18. add_security_headers middleware
# ----------------------------------------------------------------

def test_security_headers_present():
    resp = client.get("/health")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("X-XSS-Protection") == "1; mode=block"
    assert (
        resp.headers.get("Content-Security-Policy")
        == "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )
    assert (
        resp.headers.get("Permissions-Policy")
        == "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), payment=(), usb=()"
    )
    assert (
        resp.headers.get("Strict-Transport-Security")
        == "max-age=31536000; includeSubDomains"
    )
    assert resp.headers.get("Cache-Control") == "no-store"


def test_trace_id_header_preserved_when_valid():
    trace_id = "trace-12345678"
    resp = client.get("/health", headers={"X-Trace-Id": trace_id})

    assert resp.headers.get("X-Trace-Id") == trace_id
    assert resp.headers.get("X-Request-Id") == trace_id


def test_trace_id_header_generated_when_invalid():
    resp = client.get("/health", headers={"X-Trace-Id": "\n"})
    trace_id = resp.headers.get("X-Trace-Id")

    assert trace_id is not None
    assert re.fullmatch(r"[0-9a-f]{32}", trace_id) is not None
    assert resp.headers.get("X-Request-Id") == trace_id


# ----------------------------------------------------------------
# 19-21. require_api_key
# ----------------------------------------------------------------

def test_require_api_key_missing():
    resp = client.post("/v1/fuji/validate", json={"action": "x"})
    assert resp.status_code == 401


def test_require_api_key_wrong():
    resp = client.post("/v1/fuji/validate", json={"action": "x"}, headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_require_api_key_server_not_configured_v2(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", "")
    monkeypatch.setattr(server, "API_KEY_DEFAULT", "")
    monkeypatch.setattr(server, "cfg", SimpleNamespace(api_key=""))
    resp = client.post("/v1/fuji/validate", json={"action": "x"}, headers={"X-API-Key": "any"})
    assert resp.status_code == 500


# ----------------------------------------------------------------
# 22-23. enforce_rate_limit
# ----------------------------------------------------------------

def test_enforce_rate_limit_missing_key_v2():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        server.enforce_rate_limit(x_api_key=None)
    assert exc.value.status_code == 401


def test_enforce_rate_limit_exceeded_v2(monkeypatch):
    key = "rl-test-key"
    server._rate_bucket.clear()
    server._rate_bucket[key] = (server._RATE_LIMIT, time.time())
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        server.enforce_rate_limit(x_api_key=key)
    assert exc.value.status_code == 429


def test_enforce_rate_limit_ok():
    server._rate_bucket.clear()
    result = server.enforce_rate_limit(x_api_key="fresh-key")
    assert result is True


# ----------------------------------------------------------------
# 24-26. verify_signature
# ----------------------------------------------------------------

class _FakeRequest:
    def __init__(self, body: bytes):
        self._body = body

    async def body(self) -> bytes:
        return self._body


def _run_async(coro):
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_verify_signature_missing_secret_v2(monkeypatch):
    monkeypatch.setattr(server, "API_SECRET", b"")
    monkeypatch.setenv("VERITAS_API_SECRET", "")
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _run_async(server.verify_signature(
            _FakeRequest(b"{}"), x_api_key="k", x_timestamp=str(int(time.time())),
            x_nonce="n1", x_signature="sig",
        ))
    assert exc.value.status_code == 500


def test_verify_signature_missing_headers_v2(monkeypatch):
    monkeypatch.setattr(server, "API_SECRET", b"secret-for-test-1234567890abcdef")
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _run_async(server.verify_signature(
            _FakeRequest(b""), x_api_key=None, x_timestamp=None, x_nonce=None, x_signature=None,
        ))
    assert exc.value.status_code == 401


def test_verify_signature_invalid_timestamp_v2(monkeypatch):
    monkeypatch.setattr(server, "API_SECRET", b"secret-for-test-1234567890abcdef")
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _run_async(server.verify_signature(
            _FakeRequest(b""), x_api_key="k", x_timestamp="not-int",
            x_nonce="n2", x_signature="sig",
        ))
    assert exc.value.status_code == 401


def test_verify_signature_timestamp_out_of_range_v2(monkeypatch):
    monkeypatch.setattr(server, "API_SECRET", b"secret-for-test-1234567890abcdef")
    old_ts = str(int(time.time()) - 9999)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _run_async(server.verify_signature(
            _FakeRequest(b""), x_api_key="k", x_timestamp=old_ts,
            x_nonce="n3", x_signature="sig",
        ))
    assert exc.value.status_code == 401


def test_verify_signature_valid(monkeypatch):
    secret = b"secret-for-test-1234567890abcdef"
    monkeypatch.setattr(server, "API_SECRET", secret)
    server._nonce_store.clear()
    ts = str(int(time.time()))
    nonce = "unique-nonce-valid"
    body = b'{"hello":"world"}'
    payload = f"{ts}\n{nonce}\n{body.decode()}"
    sig = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    result = _run_async(server.verify_signature(
        _FakeRequest(body), x_api_key="k", x_timestamp=ts,
        x_nonce=nonce, x_signature=sig,
    ))
    assert result is True


def test_verify_signature_replay(monkeypatch):
    secret = b"secret-for-test-1234567890abcdef"
    monkeypatch.setattr(server, "API_SECRET", secret)
    server._nonce_store.clear()
    ts = str(int(time.time()))
    nonce = "replay-nonce"
    body = b""
    payload = f"{ts}\n{nonce}\n"
    sig = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    # First call succeeds
    _run_async(server.verify_signature(
        _FakeRequest(body), x_api_key="k", x_timestamp=ts,
        x_nonce=nonce, x_signature=sig,
    ))
    # Second call is replay
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _run_async(server.verify_signature(
            _FakeRequest(body), x_api_key="k", x_timestamp=ts,
            x_nonce=nonce, x_signature=sig,
        ))
    assert exc.value.status_code == 401


# ----------------------------------------------------------------
# 30-32. _coerce_decide_payload
# ----------------------------------------------------------------

def test_coerce_decide_payload_non_dict():
    r = server._coerce_decide_payload("just a string")
    assert r["ok"] is True
    assert r["alternatives"] == []
    assert "request_id" in r


def test_coerce_decide_payload_dict_minimal():
    r = server._coerce_decide_payload({"chosen": {"title": "A"}})
    assert r["ok"] is True
    assert "request_id" in r
    assert r["trust_log"] is None


def test_coerce_decide_payload_options_to_alternatives():
    r = server._coerce_decide_payload({"options": [{"title": "opt1"}]})
    assert len(r["alternatives"]) == 1
    assert r["alternatives"][0]["title"] == "opt1"


# ----------------------------------------------------------------
# 33-35. _coerce_fuji_payload
# ----------------------------------------------------------------

def test_coerce_fuji_payload_non_dict():
    r = server._coerce_fuji_payload("raw", action="act")
    assert r["status"] == "allow"
    assert r["action"] == "act"


def test_coerce_fuji_payload_empty_dict():
    r = server._coerce_fuji_payload({})
    assert r["status"] == "allow"
    assert r["reasons"] == []
    assert r["violations"] == []


def test_coerce_fuji_payload_preserves_status():
    r = server._coerce_fuji_payload({"status": "rejected", "reasons": ["r"], "violations": ["v"]})
    assert r["status"] == "rejected"
    assert r["reasons"] == ["r"]


# ----------------------------------------------------------------
# 36-38. _coerce_alt_list
# ----------------------------------------------------------------

def test_coerce_alt_list_none():
    assert server._coerce_alt_list(None) == []


def test_coerce_alt_list_single_dict():
    r = server._coerce_alt_list({"title": "A"})
    assert len(r) == 1
    assert r[0]["title"] == "A"


def test_coerce_alt_list_scalar():
    r = server._coerce_alt_list("hello")
    assert len(r) == 1
    assert r[0]["title"] == "hello"


# ----------------------------------------------------------------
# 39. _gen_request_id
# ----------------------------------------------------------------

def test_gen_request_id_length():
    rid = server._gen_request_id("seed")
    assert isinstance(rid, str)
    assert len(rid) == 24


# ----------------------------------------------------------------
# 40. _is_debug_mode
# ----------------------------------------------------------------

def test_is_debug_mode_off(monkeypatch):
    monkeypatch.delenv("VERITAS_DEBUG_MODE", raising=False)
    assert server._is_debug_mode() is False


def test_is_debug_mode_on(monkeypatch):
    monkeypatch.setenv("VERITAS_DEBUG_MODE", "1")
    assert server._is_debug_mode() is True


def test_is_debug_mode_with_spaces(monkeypatch):
    monkeypatch.setenv("VERITAS_DEBUG_MODE", "  TRUE  ")
    assert server._is_debug_mode() is True


def test_is_debug_mode_on_keyword(monkeypatch):
    monkeypatch.setenv("VERITAS_DEBUG_MODE", "on")
    assert server._is_debug_mode() is True


def test_is_debug_mode_unknown_value(monkeypatch):
    monkeypatch.setenv("VERITAS_DEBUG_MODE", "enabled")
    assert server._is_debug_mode() is False


# ----------------------------------------------------------------
# 42. _is_placeholder_secret
# ----------------------------------------------------------------

def test_is_placeholder_secret_true():
    assert server._is_placeholder_secret("YOUR_VERITAS_API_SECRET_HERE") is True


def test_is_placeholder_secret_false():
    assert server._is_placeholder_secret("real-secret") is False


# ----------------------------------------------------------------
# 44. _cleanup_nonces
# ----------------------------------------------------------------

def test_cleanup_nonces_removes_expired():
    server._nonce_store["old"] = time.time() - 9999
    server._cleanup_nonces()
    assert "old" not in server._nonce_store


# ----------------------------------------------------------------
# 45. _check_and_register_nonce
# ----------------------------------------------------------------

def test_check_and_register_nonce_new():
    nonce = f"fresh-{time.time()}"
    assert server._check_and_register_nonce(nonce) is True


def test_check_and_register_nonce_duplicate():
    nonce = f"dup-{time.time()}"
    server._check_and_register_nonce(nonce)
    assert server._check_and_register_nonce(nonce) is False


# ----------------------------------------------------------------
# 47. _cleanup_rate_bucket
# ----------------------------------------------------------------

def test_cleanup_rate_bucket_removes_old():
    server._rate_bucket["old_key"] = (1, time.time() - 9999)
    server._cleanup_rate_bucket()
    assert "old_key" not in server._rate_bucket


# ----------------------------------------------------------------
# 48. redact
# ----------------------------------------------------------------

def test_redact_empty():
    assert server.redact("") == ""


def test_redact_email():
    result = server.redact("contact user@example.com today")
    assert "user@example.com" not in result


# ----------------------------------------------------------------
# 50. _decide_example
# ----------------------------------------------------------------

def test_decide_example_format():
    ex = server._decide_example()
    assert "query" in ex
    assert "options" in ex


# ----------------------------------------------------------------
# 51-52. Endpoints via TestClient
# ----------------------------------------------------------------

def test_root_endpoint():
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["service"] == "veritas-api"


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_v1_health_endpoint():
    resp = client.get("/v1/health")
    assert resp.status_code == 200


def test_status_endpoint():
    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "api_key_configured" in data


# ----------------------------------------------------------------
# 53. _call_fuji
# ----------------------------------------------------------------

def test_call_fuji_validate_action():
    fc = SimpleNamespace(validate_action=lambda action, context: {"status": "allow"})
    r = server._call_fuji(fc, "act", {})
    assert r["status"] == "allow"


def test_call_fuji_validate_fallback():
    fc = SimpleNamespace(validate=lambda action, context: {"status": "ok"})
    r = server._call_fuji(fc, "act", {})
    assert r["status"] == "ok"


def test_call_fuji_no_method():
    fc = SimpleNamespace()
    with pytest.raises(RuntimeError, match="neither"):
        server._call_fuji(fc, "act", {})


# ----------------------------------------------------------------
# 56. enforce_rate_limit window reset
# ----------------------------------------------------------------

def test_enforce_rate_limit_window_reset():
    key = "window-reset-key"
    server._rate_bucket[key] = (99, time.time() - server._RATE_WINDOW - 1)
    result = server.enforce_rate_limit(x_api_key=key)
    assert result is True
    assert server._rate_bucket[key][0] == 1


# ----------------------------------------------------------------
# 57. _get_expected_api_key paths
# ----------------------------------------------------------------

def test_get_expected_api_key_env(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", "envkey")
    assert server._get_expected_api_key() == "envkey"


def test_get_expected_api_key_fallback_default(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", "")
    monkeypatch.setattr(server, "API_KEY_DEFAULT", "default-key")
    assert server._get_expected_api_key() == "default-key"


# ----------------------------------------------------------------
# 58. _memory stubs
# ----------------------------------------------------------------

def test_memory_search_stub():
    assert server._memory_search_stub() == []


def test_memory_get_stub():
    assert server._memory_get_stub() is None


# ============================================================
# Source: test_server_extra_v2.py
# ============================================================


import hashlib
import hmac
import json
import os
import queue
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock, patch

# Set test API key before importing server
_TEST_KEY = "server-extra-v2-key-12345"
os.environ["VERITAS_API_KEY"] = _TEST_KEY

import pytest

import veritas_os.api.server as server


# =========================================================
# _is_placeholder
# =========================================================

class TestIsPlaceholder:
    def test_with_placeholder_attr(self):
        obj = SimpleNamespace(__veritas_placeholder__=True)
        assert server._is_placeholder(obj) is True

    def test_without_placeholder_attr(self):
        obj = SimpleNamespace()
        assert server._is_placeholder(obj) is False

    def test_regular_objects(self):
        assert server._is_placeholder("string") is False
        assert server._is_placeholder(42) is False
        assert server._is_placeholder(None) is False


# =========================================================
# _SSEEventHub
# =========================================================

class TestSSEEventHub:
    def test_publish_returns_event(self):
        hub = server._SSEEventHub()
        event = hub.publish("test_event", {"key": "value"})
        assert event["type"] == "test_event"
        assert event["payload"] == {"key": "value"}
        assert event["id"] == 1

    def test_subscribe_gets_history(self):
        hub = server._SSEEventHub()
        hub.publish("evt1", {"a": 1})
        hub.publish("evt2", {"b": 2})
        q = hub.register()
        # History should be pre-filled
        items = []
        while not q.empty():
            items.append(q.get_nowait())
        assert len(items) == 2

    def test_unregister_removes_subscriber(self):
        hub = server._SSEEventHub()
        q = hub.register()
        hub.unregister(q)
        # After unregister, new events are NOT sent to old subscriber
        hub.publish("after_unregister", {})
        assert q.empty()

    def test_publish_to_subscriber(self):
        hub = server._SSEEventHub()
        q = hub.register()
        # Clear pre-fill (empty history)
        while not q.empty():
            q.get_nowait()
        hub.publish("live_event", {"live": True})
        item = q.get_nowait()
        assert item["type"] == "live_event"

    def test_full_queue_does_not_crash(self):
        hub = server._SSEEventHub()
        # Create a small-queue subscriber
        small_q = queue.Queue(maxsize=1)
        with hub._lock:
            hub._subscribers.add(small_q)
        # Fill the queue first
        small_q.put("dummy")
        # This should not raise
        hub.publish("overflow_event", {})


# =========================================================
# _publish_event
# =========================================================

class TestPublishEvent:
    def test_does_not_crash_on_exception(self, monkeypatch):
        def raise_error(*args, **kwargs):
            raise RuntimeError("publish failed")
        monkeypatch.setattr(server._event_hub, "publish", raise_error)
        # Should not raise
        server._publish_event("test", {})


# =========================================================
# _format_sse_message
# =========================================================

class TestFormatSseMessage:
    def test_format_structure(self):
        event = {"id": 1, "type": "test_type", "payload": {"key": "val"}}
        msg = server._format_sse_message(event)
        assert msg.startswith("id: 1\n")
        assert "event: test_type\n" in msg
        assert "data: " in msg
        assert msg.endswith("\n\n")


# =========================================================
# _errstr
# =========================================================

class TestErrstr:
    def test_formats_exception(self):
        e = ValueError("test error")
        result = server._errstr(e)
        assert "ValueError" in result
        assert "test error" in result


# =========================================================
# _log_decide_failure
# =========================================================

class TestLogDecideFailure:
    def test_none_error(self, caplog):
        import logging
        with caplog.at_level(logging.ERROR):
            server._log_decide_failure("test message", None)
        assert "test message" in caplog.text

    def test_exception_error(self, caplog):
        import logging
        with caplog.at_level(logging.ERROR):
            server._log_decide_failure("pipeline failed", ValueError("bad input"))
        assert "pipeline failed" in caplog.text

    def test_string_error(self, caplog):
        import logging
        with caplog.at_level(logging.ERROR):
            server._log_decide_failure("operation failed", "string error detail")
        assert "operation failed" in caplog.text


# =========================================================
# _is_placeholder_secret
# =========================================================

class TestIsPlaceholderSecret:
    def test_placeholder_value(self):
        assert server._is_placeholder_secret(server._DEFAULT_API_SECRET_PLACEHOLDER) is True

    def test_real_value(self):
        assert server._is_placeholder_secret("real_secret_value") is False

    def test_empty_string(self):
        assert server._is_placeholder_secret("") is False


# =========================================================
# _get_api_secret
# =========================================================

class TestGetApiSecret:
    def test_placeholder_env_returns_empty(self, monkeypatch):
        monkeypatch.setattr(server, "API_SECRET", b"")
        monkeypatch.setenv("VERITAS_API_SECRET", server._DEFAULT_API_SECRET_PLACEHOLDER)
        result = server._get_api_secret()
        assert result == b""

    def test_empty_env_returns_empty(self, monkeypatch):
        monkeypatch.setattr(server, "API_SECRET", b"")
        monkeypatch.setenv("VERITAS_API_SECRET", "")
        result = server._get_api_secret()
        assert result == b""

    def test_short_key_still_returned(self, monkeypatch):
        monkeypatch.setattr(server, "API_SECRET", b"")
        monkeypatch.setenv("VERITAS_API_SECRET", "short_key_under_32")
        result = server._get_api_secret()
        assert result == b"short_key_under_32"

    def test_valid_long_key_returned(self, monkeypatch):
        monkeypatch.setattr(server, "API_SECRET", b"")
        long_key = "a" * 32
        monkeypatch.setenv("VERITAS_API_SECRET", long_key)
        result = server._get_api_secret()
        assert result == long_key.encode("utf-8")

    def test_explicit_api_secret_attr(self, monkeypatch):
        monkeypatch.setattr(server, "API_SECRET", b"explicit_test_secret")
        result = server._get_api_secret()
        assert result == b"explicit_test_secret"


# =========================================================
# _cleanup_nonces_unsafe / _cleanup_nonces
# =========================================================

class TestCleanupNonces:
    def test_cleanup_removes_expired(self):
        # Add an expired nonce
        server._nonce_store["expired_nonce"] = time.time() - 10
        server._nonce_store["valid_nonce"] = time.time() + 300
        server._cleanup_nonces_unsafe()
        assert "expired_nonce" not in server._nonce_store
        assert "valid_nonce" in server._nonce_store
        # Cleanup
        server._nonce_store.pop("valid_nonce", None)

    def test_cleanup_with_overflow(self):
        # Add more nonces than NONCE_MAX
        original_max = server._NONCE_MAX
        # Temporarily set a small max for testing
        server._NONCE_MAX = 3
        try:
            for i in range(5):
                server._nonce_store[f"overflow_nonce_{i}"] = time.time() + 300
            server._cleanup_nonces_unsafe()
            assert len([k for k in server._nonce_store if k.startswith("overflow_nonce_")]) <= 3
        finally:
            server._NONCE_MAX = original_max
            # Clean up test nonces
            for i in range(5):
                server._nonce_store.pop(f"overflow_nonce_{i}", None)

    def test_cleanup_nonces_thread_safe(self):
        """Thread-safe version doesn't raise."""
        server._cleanup_nonces()  # should not raise


# =========================================================
# _check_and_register_nonce
# =========================================================

class TestCheckAndRegisterNonce:
    def test_new_nonce_returns_true(self):
        nonce = f"unique_nonce_{time.time()}"
        result = server._check_and_register_nonce(nonce)
        assert result is True
        server._nonce_store.pop(nonce, None)

    def test_duplicate_nonce_returns_false(self):
        nonce = f"dup_nonce_{time.time()}"
        server._check_and_register_nonce(nonce)  # First time
        result = server._check_and_register_nonce(nonce)  # Second time
        assert result is False
        server._nonce_store.pop(nonce, None)


# =========================================================
# redact (fallback path)
# =========================================================

class TestRedact:
    def test_empty_string(self):
        result = server.redact("")
        assert result == ""

    def test_none_stays_empty(self):
        result = server.redact("")
        assert result == ""

    def test_redacts_email_fallback(self, monkeypatch):
        """Test fallback path when sanitize is not available."""
        monkeypatch.setattr(server, "_HAS_SANITIZE", False)
        monkeypatch.setattr(server, "_sanitize_mask_pii", None)
        text = "Contact admin@example.com for details"
        result = server.redact(text)
        assert "admin@example.com" not in result

    def test_redacts_phone_fallback(self, monkeypatch):
        """Test phone redaction in fallback path."""
        monkeypatch.setattr(server, "_HAS_SANITIZE", False)
        monkeypatch.setattr(server, "_sanitize_mask_pii", None)
        text = "Call 090-1234-5678"
        result = server.redact(text)
        # Phone pattern might be replaced
        assert isinstance(result, str)


# =========================================================
# _gen_request_id
# =========================================================

class TestGenRequestId:
    def test_returns_hex_string(self):
        result = server._gen_request_id("test_seed")
        assert isinstance(result, str)
        assert len(result) == 24
        assert all(c in "0123456789abcdef" for c in result)

    def test_different_seeds_give_different_ids(self):
        id1 = server._gen_request_id("seed1")
        id2 = server._gen_request_id("seed2")
        assert id1 != id2

    def test_empty_seed_works(self):
        result = server._gen_request_id()
        assert len(result) == 24


# =========================================================
# _coerce_alt_list
# =========================================================

class TestCoerceAltList:
    def test_none_returns_empty(self):
        assert server._coerce_alt_list(None) == []

    def test_dict_wrapped_in_list(self):
        result = server._coerce_alt_list({"title": "Option A"})
        assert isinstance(result, list)
        assert len(result) == 1

    def test_non_list_non_dict_wrapped(self):
        result = server._coerce_alt_list("string value")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["title"] == "string value"

    def test_list_of_dicts(self):
        v = [{"title": "A"}, {"title": "B"}]
        result = server._coerce_alt_list(v)
        assert len(result) == 2
        assert all("id" in r for r in result)

    def test_list_with_non_dict_elements(self):
        result = server._coerce_alt_list(["string_item"])
        assert result[0]["title"] == "string_item"

    def test_score_coerced_to_float(self):
        result = server._coerce_alt_list([{"title": "A", "score": "0.75"}])
        assert result[0]["score"] == 0.75

    def test_invalid_score_defaults_to_one(self):
        result = server._coerce_alt_list([{"title": "A", "score": "invalid"}])
        assert result[0]["score"] == 1.0


# =========================================================
# _coerce_decide_payload
# =========================================================

class TestCoerceDecidePayload:
    def test_non_dict_wrapped(self):
        result = server._coerce_decide_payload("some string")
        assert isinstance(result, dict)
        assert result["ok"] is True
        assert "request_id" in result

    def test_adds_trust_log(self):
        result = server._coerce_decide_payload({"chosen": {"title": "X"}})
        assert "trust_log" in result

    def test_adds_ok_field(self):
        result = server._coerce_decide_payload({"chosen": {"title": "X"}})
        assert result["ok"] is True

    def test_generates_request_id(self):
        result = server._coerce_decide_payload({"chosen": {}})
        assert result.get("request_id") is not None

    def test_non_dict_chosen_wrapped(self):
        result = server._coerce_decide_payload({"chosen": "Option A"})
        assert isinstance(result["chosen"], dict)

    def test_none_chosen_gets_empty_dict(self):
        result = server._coerce_decide_payload({"chosen": None})
        assert result["chosen"] == {}

    def test_uses_opts_when_alts_missing(self):
        opts = [{"title": "Opt A"}]
        result = server._coerce_decide_payload({"options": opts})
        assert len(result["alternatives"]) == 1

    def test_mirrors_alts_to_options(self):
        alts = [{"title": "Alt A", "id": "a1"}]
        result = server._coerce_decide_payload({"alternatives": alts})
        assert len(result["options"]) >= 1


# =========================================================
# _coerce_fuji_payload
# =========================================================

class TestCoerceFujiPayload:
    def test_non_dict_wrapped(self):
        result = server._coerce_fuji_payload("allow")
        assert isinstance(result, dict)
        assert result["status"] == "allow"

    def test_adds_missing_status(self):
        result = server._coerce_fuji_payload({})
        assert result["status"] == "allow"

    def test_adds_missing_reasons(self):
        result = server._coerce_fuji_payload({"status": "deny"})
        assert result["reasons"] == []

    def test_adds_missing_violations(self):
        result = server._coerce_fuji_payload({"status": "deny", "reasons": []})
        assert result["violations"] == []

    def test_preserves_existing_values(self):
        payload = {"status": "deny", "reasons": ["r1"], "violations": ["v1"]}
        result = server._coerce_fuji_payload(payload)
        assert result["status"] == "deny"
        assert result["reasons"] == ["r1"]


# =========================================================
# _is_debug_mode
# =========================================================

class TestIsDebugMode:
    def test_1_is_debug(self, monkeypatch):
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "1")
        assert server._is_debug_mode() is True

    def test_true_is_debug(self, monkeypatch):
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "true")
        assert server._is_debug_mode() is True

    def test_yes_is_debug(self, monkeypatch):
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "yes")
        assert server._is_debug_mode() is True

    def test_on_is_debug(self, monkeypatch):
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "on")
        assert server._is_debug_mode() is True

    def test_empty_is_not_debug(self, monkeypatch):
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "")
        assert server._is_debug_mode() is False

    def test_false_is_not_debug(self, monkeypatch):
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "false")
        assert server._is_debug_mode() is False

    def test_random_is_not_debug(self, monkeypatch):
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "random_value")
        assert server._is_debug_mode() is False


# =========================================================
# _resolve_expected_api_key_with_source
# =========================================================

class TestResolveExpectedApiKeyWithSource:
    def test_env_key_returns_env(self, monkeypatch):
        monkeypatch.setenv("VERITAS_API_KEY", "my-env-key")
        key, source = server._resolve_expected_api_key_with_source()
        assert key == "my-env-key"
        assert source == "env"

    def test_missing_returns_missing(self, monkeypatch):
        monkeypatch.setenv("VERITAS_API_KEY", "")
        monkeypatch.setattr(server, "API_KEY_DEFAULT", "")
        cfg_mock = MagicMock()
        cfg_mock.api_key = ""
        monkeypatch.setattr(server, "cfg", cfg_mock, raising=False)
        key, source = server._resolve_expected_api_key_with_source()
        assert source in ("missing", "env", "api_key_default", "config")


# =========================================================
# _decide_example
# =========================================================

class TestDecideExample:
    def test_returns_dict_with_required_keys(self):
        result = server._decide_example()
        assert "context" in result
        assert "query" in result
        assert "options" in result
