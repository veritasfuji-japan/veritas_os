# veritas_os/tests/test_github_adapter.py
# -*- coding: utf-8 -*-

from veritas_os.tools import github_adapter


def test_prepare_query_basic_and_truncate():
    # 改行 → スペース & strip の確認
    q, truncated = github_adapter._prepare_query("  foo\nbar  ")
    assert q == "foo bar"
    assert truncated is False

    q_ctrl, truncated_ctrl = github_adapter._prepare_query("a\x00\x1fb")
    assert q_ctrl == "a b"
    assert truncated_ctrl is False

    # None でも落ちない
    q2, truncated2 = github_adapter._prepare_query(None)
    assert q2 == ""
    assert truncated2 is False

    # 長すぎるクエリは MAX_QUERY_LEN でカット
    raw = "x" * (github_adapter.MAX_QUERY_LEN + 10)
    q3, truncated3 = github_adapter._prepare_query(raw)
    assert len(q3) == github_adapter.MAX_QUERY_LEN
    assert truncated3 is True


def test_github_search_repos_without_token(monkeypatch):
    """
    VERITAS_GITHUB_TOKEN が設定されていない場合は
    即エラーを返す（API を叩かない）。
    """
    monkeypatch.setenv("VERITAS_GITHUB_TOKEN", "")

    res = github_adapter.github_search_repos("veritas_os")

    assert res["ok"] is False
    assert res["results"] == []
    assert "GitHub API unavailable" in res["error"]


def test_github_search_repos_empty_query(monkeypatch):
    """
    トークンはあるがクエリが空 / 空白のみ → empty_query エラー。
    """
    monkeypatch.setenv("VERITAS_GITHUB_TOKEN", "dummy-token")

    res = github_adapter.github_search_repos("   ")

    assert res["ok"] is False
    assert res["results"] == []
    assert res["error"] == "empty_query"


def test_github_search_repos_success(monkeypatch):
    """
    正常系: GitHub API が成功したときに shape が整っているか。
    実際のネットワークは叩かず、requests.get をモックする。
    """
    monkeypatch.setenv("VERITAS_GITHUB_TOKEN", "dummy-token")

    class DummyResp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            # 何もしない = 200 OK 想定
            return None

        def json(self):
            return self._payload

    def fake_get(url, headers=None, params=None, timeout=None, **kwargs):
        # URL・パラメータがそれなりに渡っているかだけ軽く確認
        assert "api.github.com/search/repositories" in url
        assert params["q"] == "veritas_os"
        assert params["per_page"] == 3
        assert kwargs.get("allow_redirects") is False
        assert "Authorization" in headers
        assert "dummy-token" in headers["Authorization"]
        payload = {
            "items": [
                {
                    "full_name": "veritasfuji-japan/veritas_os",
                    "html_url": "https://github.com/veritasfuji-japan/veritas_os",
                    "description": "Proto-AGI Decision OS",
                    "stargazers_count": 42,
                }
            ]
        }
        return DummyResp(payload)

    monkeypatch.setattr(github_adapter.requests, "get", fake_get)

    res = github_adapter.github_search_repos("veritas_os", max_results=3)

    assert res["ok"] is True
    assert res["error"] is None
    assert isinstance(res["results"], list)
    assert res["meta"]["raw_count"] == 1
    assert res["meta"]["used_query"] == "veritas_os"
    assert res["meta"]["truncated_query"] is False

    item = res["results"][0]
    assert item["full_name"] == "veritasfuji-japan/veritas_os"
    assert item["html_url"].startswith("https://github.com/")
    assert item["description"] == "Proto-AGI Decision OS"
    assert item["stars"] == 42


def test_github_search_repos_handles_api_error(monkeypatch):
    """
    GitHub API 側で例外が起きたときも、
    GitHub API error: ... というエラーを返して落ちないこと。
    """
    monkeypatch.setenv("VERITAS_GITHUB_TOKEN", "dummy-token")

    def fake_get(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(github_adapter.requests, "get", fake_get)

    res = github_adapter.github_search_repos("veritas_os")

    assert res["ok"] is False
    assert res["results"] == []
    assert "GitHub API error:" in res["error"]


def test_github_search_repos_retries_on_timeout(monkeypatch):
    """一時的なタイムアウト時に再試行する。"""
    monkeypatch.setenv("VERITAS_GITHUB_TOKEN", "dummy-token")
    monkeypatch.setattr(github_adapter, "GITHUB_MAX_RETRIES", 2)
    monkeypatch.setattr(github_adapter, "GITHUB_RETRY_DELAY", 0.0)
    monkeypatch.setattr(github_adapter, "GITHUB_RETRY_MAX_DELAY", 0.0)
    monkeypatch.setattr(github_adapter, "GITHUB_RETRY_JITTER", 0.0)
    monkeypatch.setattr(github_adapter.time, "sleep", lambda *_: None)

    class DummyResp:
        def __init__(self, payload):
            self._payload = payload
            self.status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    calls = {"count": 0}

    def fake_get(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise github_adapter.requests.exceptions.Timeout("boom")
        payload = {
            "items": [
                {
                    "full_name": "veritasfuji-japan/veritas_os",
                    "html_url": "https://github.com/veritasfuji-japan/veritas_os",
                    "description": "Proto-AGI Decision OS",
                    "stargazers_count": 42,
                }
            ]
        }
        return DummyResp(payload)

    monkeypatch.setattr(github_adapter.requests, "get", fake_get)

    res = github_adapter.github_search_repos("veritas_os")

    assert calls["count"] == 2
    assert res["ok"] is True
    assert res["results"][0]["full_name"] == "veritasfuji-japan/veritas_os"


def test_get_github_token_reads_latest_env(monkeypatch):
    """Environment token updates are reflected without module reload."""
    monkeypatch.setenv("VERITAS_GITHUB_TOKEN", "token-a")
    assert github_adapter._get_github_token() == "token-a"

    monkeypatch.setenv("VERITAS_GITHUB_TOKEN", "token-b")
    assert github_adapter._get_github_token() == "token-b"


def test_normalize_repo_item_uses_safe_defaults():
    result = github_adapter._normalize_repo_item(
        {
            "full_name": None,
            "html_url": None,
            "description": None,
            "stargazers_count": "7",
        }
    )

    assert result["full_name"] == ""
    assert result["html_url"] == ""
    assert result["description"] == ""
    assert result["stars"] == 7


def test_normalize_repo_item_drops_unsafe_html_url():
    result = github_adapter._normalize_repo_item(
        {
            "full_name": "owner/repo",
            "html_url": "javascript:alert(1)",
            "description": "demo",
            "stargazers_count": 1,
        }
    )

    assert result["html_url"] == ""


def test_safe_float_non_finite_returns_default(monkeypatch):
    monkeypatch.setenv("VERITAS_GITHUB_RETRY_DELAY", "nan")
    assert github_adapter._safe_float("VERITAS_GITHUB_RETRY_DELAY", 1.5) == 1.5
