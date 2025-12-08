# veritas_os/tests/test_api_server_extra.py

from __future__ import annotations

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

import veritas_os.api.server as server


client = TestClient(server.app)


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
# Health / Status / Metrics
# -------------------------------------------------

def test_health_and_status_and_metrics():
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

    # metrics
    r = client.get("/v1/metrics")
    assert r.status_code == 200
    data = r.json()
    assert "decide_files" in data
    assert "trust_jsonl_lines" in data
    assert "last_decide_at" in data
    assert "server_time" in data


# -------------------------------------------------
# APIキーまわり (require_api_key / enforce_rate_limit)
# -------------------------------------------------

def test_require_api_key_server_not_configured(monkeypatch):
    """
    サーバ側の API キー未設定パス（500）
    """
    monkeypatch.delenv("VERITAS_API_KEY", raising=False)
    monkeypatch.setattr(server, "API_KEY_DEFAULT", "")
    with pytest.raises(HTTPException) as exc:
        server.require_api_key(x_api_key="anything")  # type: ignore[arg-type]
    assert exc.value.status_code == 500


def test_require_api_key_invalid_key(monkeypatch):
    """
    間違ったキー → 401
    """
    monkeypatch.setenv("VERITAS_API_KEY", "expected-key")
    with pytest.raises(HTTPException) as exc:
        server.require_api_key(x_api_key="wrong-key")  # type: ignore[arg-type]
    assert exc.value.status_code == 401


def test_require_api_key_success(monkeypatch):
    """
    正しいキー → True
    """
    monkeypatch.setenv("VERITAS_API_KEY", "expected-key")
    ok = server.require_api_key(x_api_key="expected-key")  # type: ignore[arg-type]
    assert ok is True


def test_enforce_rate_limit_exceeded():
    """
    _RATE_LIMIT 回まではOK、1回超過で 429
    """
    key = "rate-user"
    server._rate_bucket.clear()  # type: ignore[attr-defined]

    # 制限回数までは通る
    for _ in range(server._RATE_LIMIT):  # type: ignore[attr-defined]
        assert server.enforce_rate_limit(x_api_key=key) is True  # type: ignore[arg-type]

    # 1回超過で HTTP 429
    with pytest.raises(HTTPException) as exc:
        server.enforce_rate_limit(x_api_key=key)  # type: ignore[arg-type]
    assert exc.value.status_code == 429


# -------------------------------------------------
# Memory API: put / get / search
# -------------------------------------------------

def test_memory_put_and_get_roundtrip():
    """
    /v1/memory/put (レガシーKV) → /v1/memory/get で値が取れること
    """
    body = {"user_id": "user1", "key": "k_legacy", "value": {"foo": "bar"}}
    r = client.post("/v1/memory/put", json=body)
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
    r = client.post("/v1/memory/put", json=body)
    assert r.status_code == 200
    data = r.json()

    vec = data["vector"]
    assert vec["saved"] is True
    assert vec["kind"] == "skills"        # kind 正常化
    assert vec["id"] is not None
    assert data["size"] == len(text)      # size は text 長さ


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

    # user_id 指定あり → meta.user_id 一致分だけ
    r = client.post(
        "/v1/memory/search",
        json={"query": "q", "user_id": "userX"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["count"] == 1
    assert data["hits"][0]["meta"]["user_id"] == "userX"

    # user_id なし → dict + 文字列ラップ分 全部返る
    r2 = client.post(
        "/v1/memory/search",
        json={"query": "q"},
    )
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["ok"] is True
    assert data2["count"] == 3

    # 文字列ヒットは {"id": "..."} にラップされているはず
    assert any(isinstance(h, dict) and "id" in h for h in data2["hits"])


# -------------------------------------------------
# Trust Feedback API
# -------------------------------------------------

def test_trust_feedback_ok(monkeypatch):
    """
    append_trust_log が正常に呼ばれたパス
    """
    calls = []

    def fake_append_trust_log(user_id, score, note, source, extra):
        calls.append((user_id, score, note, source, extra))

    monkeypatch.setattr(server.value_core, "append_trust_log", fake_append_trust_log)

    r = client.post(
        "/v1/trust/feedback",
        json={
            "user_id": "user123",
            "score": 0.9,
            "note": "good plan",
            "source": "test",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
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

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(server.value_core, "append_trust_log", boom)

    r = client.post(
        "/v1/trust/feedback",
        json={
            "user_id": "user_err",
            "score": 0.1,
            "note": "bad",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "error"
    assert "detail" in data

