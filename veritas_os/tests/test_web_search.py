# tests/test_web_search.py
from __future__ import annotations

from typing import Any, Dict
import importlib

import pytest

# veritas_os.tools.web_search モジュール本体を明示的にロード
web_search_mod = importlib.import_module("veritas_os.tools.web_search")


@pytest.fixture()
def _bypass_ssrf(monkeypatch):
    """Bypass DNS-based SSRF host checks.

    CI / sandbox environments often cannot resolve external hostnames
    (e.g. example.com).  Tests that mock ``requests.post`` never make
    real HTTP calls, so the DNS-based guard is irrelevant.
    """
    web_search_mod._is_private_or_local_host.cache_clear()
    monkeypatch.setattr(
        web_search_mod, "_is_private_or_local_host", lambda _host: False,
    )


class DummyResponse:
    """requests.post をモックするための簡易レスポンス"""

    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def raise_for_status(self) -> None:
        # エラーは発生させない
        return None

    def json(self) -> Dict[str, Any]:
        return self._data


# -----------------------------
# ヘルパー関数の単体テスト
# -----------------------------
def test_is_agi_query_true_for_agi_word() -> None:
    assert web_search_mod._is_agi_query("AGI research") is True
    assert web_search_mod._is_agi_query("人工汎用知能の安全性") is True
    assert web_search_mod._is_agi_query("人工一般知能とは") is True


def test_is_agi_query_false_for_normal_query() -> None:
    assert web_search_mod._is_agi_query("python web framework") is False
    assert web_search_mod._is_agi_query("可愛い猫の動画") is False


def test_looks_agi_result_true_by_site() -> None:
    title = "Some paper"
    snippet = "interesting result"
    url = "https://arxiv.org/abs/1234.5678"
    assert web_search_mod._looks_agi_result(title, snippet, url) is True


def test_looks_agi_result_true_by_keyword() -> None:
    title = "A Survey of Artificial General Intelligence"
    snippet = "We study AGI"
    url = "https://example.com/agi-survey"
    assert web_search_mod._looks_agi_result(title, snippet, url) is True


def test_looks_agi_result_false_for_unrelated() -> None:
    title = "Cute cats compilation"
    snippet = "funny animals and pets"
    url = "https://example.com/cats"
    assert web_search_mod._looks_agi_result(title, snippet, url) is False


def test_safe_float_rejects_non_finite_values(monkeypatch) -> None:
    """環境変数が非有限値ならデフォルト値にフォールバックする。"""
    monkeypatch.setenv("VERITAS_WEBSEARCH_RETRY_DELAY", "nan")
    assert web_search_mod._safe_float("VERITAS_WEBSEARCH_RETRY_DELAY", 1.5) == 1.5

    monkeypatch.setenv("VERITAS_WEBSEARCH_RETRY_DELAY", "inf")
    assert web_search_mod._safe_float("VERITAS_WEBSEARCH_RETRY_DELAY", 2.5) == 2.5


def test_sanitize_max_results_clamps_values() -> None:
    assert web_search_mod._sanitize_max_results(0) == 1
    assert web_search_mod._sanitize_max_results(101) == 100
    assert web_search_mod._sanitize_max_results("3") == 3
    assert web_search_mod._sanitize_max_results("abc") == 5


def test_normalize_result_item_rejects_unsafe_scheme() -> None:
    """危険なスキームは正規化段階で除外する。"""
    item = {
        "title": "bad",
        "link": "javascript:alert(1)",
        "snippet": "x",
    }
    assert web_search_mod._normalize_result_item(item) is None


def test_normalize_result_item_rejects_url_with_userinfo() -> None:
    """userinfo を含む URL は漏えいリスク低減のため除外する。"""
    item = {
        "title": "bad",
        "link": "https://user:secret@example.com/path",
        "snippet": "x",
    }
    assert web_search_mod._normalize_result_item(item) is None


def test_normalize_result_item_rejects_url_without_hostname() -> None:
    """host を含まない URL は不正入力として除外する。"""
    item = {
        "title": "bad",
        "link": "https:///missing-host",
        "snippet": "x",
    }
    assert web_search_mod._normalize_result_item(item) is None


def test_normalize_result_item_rejects_missing_url() -> None:
    """URL が無い検索結果は後続処理を不安定にするため除外する。"""
    item = {
        "title": "title only",
        "snippet": "snippet only",
    }

    assert web_search_mod._normalize_result_item(item) is None


def test_normalize_result_item_truncates_long_fields(_bypass_ssrf) -> None:
    """検索結果の各フィールドは上限長で切り詰める。"""
    item = {
        "title": "t" * 700,
        "link": "https://example.com/" + ("p" * 3000),
        "snippet": "s" * 3000,
    }

    normalized = web_search_mod._normalize_result_item(item)

    assert normalized is not None
    assert len(normalized["title"]) == 512
    assert len(normalized["url"]) == 2048
    assert len(normalized["snippet"]) == 2048


# -----------------------------
# web_search 本体のテスト
# -----------------------------


def test_sanitize_websearch_url_rejects_unsafe_scheme() -> None:
    """危険なスキームの URL は空文字へ正規化する。"""
    assert web_search_mod._sanitize_websearch_url("file:///etc/passwd") == ""


def test_resolve_websearch_credentials_ignores_unsafe_runtime_url(monkeypatch) -> None:
    """実行時 URL が危険なスキームならモジュール既定値へフォールバックする。"""
    monkeypatch.setattr(
        web_search_mod, "WEBSEARCH_URL", "https://fallback.example/serper", raising=False
    )
    monkeypatch.setattr(web_search_mod, "WEBSEARCH_KEY", "fallback-key", raising=False)
    monkeypatch.setenv("VERITAS_WEBSEARCH_URL", "file:///etc/passwd")
    monkeypatch.setenv("VERITAS_WEBSEARCH_KEY", "runtime-key")

    resolved_url, resolved_key = web_search_mod._resolve_websearch_credentials()

    assert resolved_url == "https://fallback.example/serper"
    assert resolved_key == "runtime-key"


def test_resolve_websearch_credentials_prefers_runtime_env(monkeypatch) -> None:
    """実行時の環境変数が資格情報解決で優先される。"""
    monkeypatch.setattr(
        web_search_mod, "WEBSEARCH_URL", "https://fallback.example/serper", raising=False
    )
    monkeypatch.setattr(web_search_mod, "WEBSEARCH_KEY", "fallback-key", raising=False)
    monkeypatch.setenv("VERITAS_WEBSEARCH_URL", "https://runtime.example/serper")
    monkeypatch.setenv("VERITAS_WEBSEARCH_KEY", "runtime-key")

    resolved_url, resolved_key = web_search_mod._resolve_websearch_credentials()

    assert resolved_url == "https://runtime.example/serper"
    assert resolved_key == "runtime-key"


def test_resolve_websearch_credentials_falls_back_to_module_defaults(monkeypatch) -> None:
    """環境変数が空の場合は既存のモジュール設定を利用する。"""
    monkeypatch.setattr(
        web_search_mod, "WEBSEARCH_URL", "https://fallback.example/serper", raising=False
    )
    monkeypatch.setattr(web_search_mod, "WEBSEARCH_KEY", "fallback-key", raising=False)
    monkeypatch.delenv("VERITAS_WEBSEARCH_URL", raising=False)
    monkeypatch.delenv("VERITAS_WEBSEARCH_KEY", raising=False)

    resolved_url, resolved_key = web_search_mod._resolve_websearch_credentials()

    assert resolved_url == "https://fallback.example/serper"
    assert resolved_key == "fallback-key"




def test_resolve_websearch_host_allowlist_prefers_runtime_env(monkeypatch) -> None:
    """実行時の allowlist 環境変数を優先して解決する。"""
    monkeypatch.setattr(
        web_search_mod,
        "WEBSEARCH_HOST_ALLOWLIST",
        {"fallback.example", "fallback2.example"},
        raising=False,
    )
    monkeypatch.setenv(
        "VERITAS_WEBSEARCH_HOST_ALLOWLIST",
        "runtime.example, runtime2.example",
    )

    resolved_allowlist = web_search_mod._resolve_websearch_host_allowlist()

    assert resolved_allowlist == {"runtime.example", "runtime2.example"}


def test_resolve_websearch_host_allowlist_falls_back_to_module_defaults(monkeypatch) -> None:
    """allowlist 環境変数が空ならモジュール既定値にフォールバックする。"""
    monkeypatch.setattr(
        web_search_mod,
        "WEBSEARCH_HOST_ALLOWLIST",
        {"fallback.example", "fallback2.example"},
        raising=False,
    )
    monkeypatch.delenv("VERITAS_WEBSEARCH_HOST_ALLOWLIST", raising=False)

    resolved_allowlist = web_search_mod._resolve_websearch_host_allowlist()

    assert resolved_allowlist == {"fallback.example", "fallback2.example"}


def test_web_search_returns_error_when_not_configured(monkeypatch) -> None:
    """URL / KEY が設定されていない場合、config エラーを返す"""
    monkeypatch.setattr(web_search_mod, "WEBSEARCH_URL", "", raising=False)
    monkeypatch.setattr(web_search_mod, "WEBSEARCH_KEY", "", raising=False)

    resp = web_search_mod.web_search("hello world")

    assert resp["ok"] is False
    assert resp["results"] == []
    assert "WEBSEARCH_API unavailable" in resp["error"]


def test_web_search_normal_query_returns_results(monkeypatch, _bypass_ssrf) -> None:
    """通常クエリでは AGI フィルタ無しでそのまま結果を返す"""
    # 疑似的な設定
    monkeypatch.setattr(
        web_search_mod, "WEBSEARCH_URL", "https://example.com/serper", raising=False
    )
    monkeypatch.setattr(web_search_mod, "WEBSEARCH_KEY", "dummy-key", raising=False)

    data = {
        "organic": [
            {
                "title": "Result 1",
                "link": "https://example.com/1",
                "snippet": "First result",
            },
            {
                "title": "Result 2",
                "link": "https://example.com/2",
                "snippet": "Second result",
            },
            {
                "title": "Result 3",
                "link": "https://example.com/3",
                "snippet": "Third result",
            },
        ]
    }

    captured: Dict[str, Any] = {}

    def fake_post(
        url: str,
        headers: Dict[str, Any],
        json: Dict[str, Any],
        timeout: int,
        **kwargs: Any,
    ):
        # ざっくりヘッダ・URL・ペイロードを検証
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json
        captured["kwargs"] = kwargs
        return DummyResponse(data)

    # requests.post をモック
    monkeypatch.setattr(web_search_mod.requests, "post", fake_post)

    resp = web_search_mod.web_search("normal query", max_results=2)

    # リクエスト周りの検証
    assert captured["url"] == web_search_mod.WEBSEARCH_URL
    assert captured["headers"]["X-API-KEY"] == web_search_mod.WEBSEARCH_KEY
    assert captured["payload"]["q"] == "normal query"
    assert captured["payload"]["num"] == 4  # max_results * 2
    assert captured["kwargs"]["allow_redirects"] is False

    # レスポンスの検証
    assert resp["ok"] is True
    assert resp["error"] is None
    assert len(resp["results"]) == 2  # max_results に切り詰め
    assert resp["meta"]["agi_filter_applied"] is False
    assert resp["meta"]["raw_count"] == len(data["organic"])
    assert resp["meta"]["boosted_query"] is None


def test_web_search_retries_on_timeout(monkeypatch, _bypass_ssrf) -> None:
    """一時的なタイムアウト時に再試行する。"""
    monkeypatch.setattr(
        web_search_mod, "WEBSEARCH_URL", "https://example.com/serper", raising=False
    )
    monkeypatch.setattr(web_search_mod, "WEBSEARCH_KEY", "dummy-key", raising=False)
    monkeypatch.setattr(web_search_mod, "WEBSEARCH_MAX_RETRIES", 2, raising=False)
    monkeypatch.setattr(web_search_mod, "WEBSEARCH_RETRY_DELAY", 0.0, raising=False)
    monkeypatch.setattr(web_search_mod, "WEBSEARCH_RETRY_MAX_DELAY", 0.0, raising=False)
    monkeypatch.setattr(web_search_mod, "WEBSEARCH_RETRY_JITTER", 0.0, raising=False)

    data = {
        "organic": [
            {
                "title": "Result 1",
                "link": "https://example.com/1",
                "snippet": "First result",
            }
        ]
    }
    calls = {"count": 0}

    def fake_post(
        url: str, headers: Dict[str, Any], json: Dict[str, Any], timeout: int, **kwargs: Any
    ):
        calls["count"] += 1
        if calls["count"] == 1:
            raise web_search_mod.requests.exceptions.Timeout("boom")
        return DummyResponse(data)

    monkeypatch.setattr(web_search_mod.requests, "post", fake_post)
    monkeypatch.setattr(web_search_mod.time, "sleep", lambda *_: None)

    resp = web_search_mod.web_search("normal query", max_results=1)

    assert calls["count"] == 2
    assert resp["ok"] is True
    assert resp["results"][0]["title"] == "Result 1"


def test_web_search_agi_query_filters_and_trims(monkeypatch, _bypass_ssrf) -> None:
    """AGI クエリではブースト + フィルタがかかる"""
    monkeypatch.setattr(
        web_search_mod, "WEBSEARCH_URL", "https://example.com/serper", raising=False
    )
    monkeypatch.setattr(web_search_mod, "WEBSEARCH_KEY", "dummy-key", raising=False)

    # AGI っぽいもの 2 件 + 関係ない 1 件
    data = {
        "organic": [
            {
                "title": "DeepMind AGI roadmap",
                "link": "https://deepmind.com/agi-roadmap",
                "snippet": "artificial general intelligence research",
            },
            {
                "title": "A Survey of Artificial General Intelligence",
                "link": "https://example.com/agi-survey",
                "snippet": "We study AGI safety.",
            },
            {
                "title": "Cute cats",
                "link": "https://example.com/cats",
                "snippet": "funny animals",
            },
        ]
    }

    captured: Dict[str, Any] = {}

    def fake_post(
        url: str, headers: Dict[str, Any], json: Dict[str, Any], timeout: int, **kwargs: Any
    ):
        captured["payload"] = json
        return DummyResponse(data)

    monkeypatch.setattr(web_search_mod.requests, "post", fake_post)

    resp = web_search_mod.web_search("AGI research roadmap", max_results=1)

    # ブーストされたクエリに論文サイト指定が含まれているか
    boosted_q = captured["payload"]["q"]
    assert "AGI research roadmap" in boosted_q
    assert "site:arxiv.org" in boosted_q
    assert "site:openreview.net" in boosted_q

    # レスポンス：AGI フィルタが適用され、件数がトリムされている
    assert resp["ok"] is True
    assert resp["error"] is None
    assert resp["meta"]["agi_filter_applied"] is True
    assert resp["meta"]["agi_result_count"] == 2  # AGI っぽいのは 2 件
    assert len(resp["results"]) == 1  # max_results=1 で切り詰め


def test_web_search_agi_query_no_agi_like_results(monkeypatch, _bypass_ssrf) -> None:
    """AGI クエリだが AGI っぽい結果が無い場合、no_agi_like_results を返す"""
    monkeypatch.setattr(
        web_search_mod, "WEBSEARCH_URL", "https://example.com/serper", raising=False
    )
    monkeypatch.setattr(web_search_mod, "WEBSEARCH_KEY", "dummy-key", raising=False)

    data = {
        "organic": [
            {
                "title": "Random blog post",
                "link": "https://example.com/blog",
                "snippet": "Just a random article.",
            }
        ]
    }

    def fake_post(
        url: str, headers: Dict[str, Any], json: Dict[str, Any], timeout: int, **kwargs: Any
    ):
        return DummyResponse(data)

    monkeypatch.setattr(web_search_mod.requests, "post", fake_post)

    resp = web_search_mod.web_search("agi safety", max_results=3)

    assert resp["ok"] is True
    assert resp["results"] == []
    assert resp["error"] == "no_agi_like_results"
    assert resp["meta"]["agi_filter_applied"] is True
    assert resp["meta"]["raw_count"] == 1
    assert resp["meta"]["agi_result_count"] == 0
    assert "boosted_query" in resp["meta"]


def test_web_search_handles_request_exception(monkeypatch, _bypass_ssrf) -> None:
    """requests.post で例外が出た場合に、エラーとしてハンドリングされること"""
    monkeypatch.setattr(
        web_search_mod, "WEBSEARCH_URL", "https://example.com/serper", raising=False
    )
    monkeypatch.setattr(web_search_mod, "WEBSEARCH_KEY", "dummy-key", raising=False)

    def fake_post(*args, **kwargs):
        raise RuntimeError("network failure")

    monkeypatch.setattr(web_search_mod.requests, "post", fake_post)

    resp = web_search_mod.web_search("some query", max_results=2)

    assert resp["ok"] is False
    assert resp["results"] == []
    assert "WEBSEARCH_API error" in resp["error"]
