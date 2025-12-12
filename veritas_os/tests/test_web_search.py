# tests/test_web_search.py
from __future__ import annotations

from typing import Any, Dict
import importlib

# veritas_os.tools.web_search モジュール本体を明示的にロード
web_search_mod = importlib.import_module("veritas_os.tools.web_search")


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


# -----------------------------
# web_search 本体のテスト
# -----------------------------
def test_web_search_returns_error_when_not_configured(monkeypatch) -> None:
    """URL / KEY が設定されていない場合、config エラーを返す"""
    monkeypatch.setattr(web_search_mod, "WEBSEARCH_URL", "", raising=False)
    monkeypatch.setattr(web_search_mod, "WEBSEARCH_KEY", "", raising=False)

    resp = web_search_mod.web_search("hello world")

    assert resp["ok"] is False
    assert resp["results"] == []
    assert "WEBSEARCH_API not configured" in resp["error"]


def test_web_search_normal_query_returns_results(monkeypatch) -> None:
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
        url: str, headers: Dict[str, Any], json: Dict[str, Any], timeout: int
    ):
        # ざっくりヘッダ・URL・ペイロードを検証
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json
        return DummyResponse(data)

    # requests.post をモック
    monkeypatch.setattr(web_search_mod.requests, "post", fake_post)

    resp = web_search_mod.web_search("normal query", max_results=2)

    # リクエスト周りの検証
    assert captured["url"] == web_search_mod.WEBSEARCH_URL
    assert captured["headers"]["X-API-KEY"] == web_search_mod.WEBSEARCH_KEY
    assert captured["payload"]["q"] == "normal query"
    assert captured["payload"]["num"] == 4  # max_results * 2

    # レスポンスの検証
    assert resp["ok"] is True
    assert resp["error"] is None
    assert len(resp["results"]) == 2  # max_results に切り詰め
    assert resp["meta"]["agi_filter_applied"] is False
    assert resp["meta"]["raw_count"] == len(data["organic"])
    assert resp["meta"]["boosted_query"] is None


def test_web_search_agi_query_filters_and_trims(monkeypatch) -> None:
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
        url: str, headers: Dict[str, Any], json: Dict[str, Any], timeout: int
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


def test_web_search_agi_query_no_agi_like_results(monkeypatch) -> None:
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
        url: str, headers: Dict[str, Any], json: Dict[str, Any], timeout: int
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


def test_web_search_handles_request_exception(monkeypatch) -> None:
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


