# veritas_os/tests/test_core_tools.py
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Dict

import math
import pytest

from veritas_os.core import tools


@pytest.fixture
def clean_tools_state(monkeypatch):
    """
    ALLOWED_TOOLS / BLOCKED_TOOLS / TOOL_REGISTRY / usage_log を
    テストごとにクリーンな状態にしておくフィクスチャ。
    """
    monkeypatch.setattr(tools, "ALLOWED_TOOLS", set(), raising=False)
    monkeypatch.setattr(tools, "BLOCKED_TOOLS", set(), raising=False)
    monkeypatch.setattr(tools, "TOOL_REGISTRY", {}, raising=False)
    tools.clear_tool_usage_log()
    yield
    # （後片付けは不要。pytest がモジュール属性差し替えを戻してくれる）


# =========================
# allowed()
# =========================

def test_allowed_true_for_whitelisted_tool(clean_tools_state):
    tools.ALLOWED_TOOLS.add("web_search")
    assert tools.allowed("web_search") is True


def test_allowed_false_for_blocked_tool(clean_tools_state):
    tools.ALLOWED_TOOLS.add("web_search")
    tools.BLOCKED_TOOLS.add("web_search")
    assert tools.allowed("web_search") is False


def test_call_tool_denied_reason_is_blocked_for_blocked_tool(clean_tools_state):
    tools.ALLOWED_TOOLS.add("web_search")
    tools.BLOCKED_TOOLS.add("web_search")

    resp = tools.call_tool("web_search", query="blocked test")

    assert resp["ok"] is False
    assert resp["meta"]["status"] == "denied"
    assert resp["meta"]["reason"] == "blocked"


def test_allowed_false_for_unknown_tool(clean_tools_state):
    tools.ALLOWED_TOOLS.add("web_search")
    assert tools.allowed("unknown_tool") is False


def test_allowed_false_for_empty_name(clean_tools_state, caplog):
    assert tools.allowed("") is False
    # warning ログが出ていることだけ軽く確認
    assert any("Empty tool name" in r.message for r in caplog.records)


# =========================
# call_tool() 基本動作
# =========================

def test_call_tool_denied_when_not_allowed(clean_tools_state):
    # 許可リストは空のまま → どのツールも拒否
    resp = tools.call_tool("web_search", query="hello")
    assert resp["ok"] is False
    assert resp["meta"]["status"] == "denied"

    log = tools.get_tool_usage_log()
    assert len(log) == 1
    assert log[0]["status"] == "denied"
    assert log[0]["tool"] == "web_search"


def test_call_tool_not_implemented_when_missing_impl(clean_tools_state):
    # ホワイトリストにはあるが、TOOL_REGISTRY に実装が無いパターン
    tools.ALLOWED_TOOLS.add("github_search")
    # TOOL_REGISTRY は fixture で {} に初期化済み

    resp = tools.call_tool("github_search", query="veritas")
    assert resp["ok"] is False
    assert resp["meta"]["status"] == "not_implemented"

    log = tools.get_tool_usage_log()
    assert len(log) == 1
    assert log[0]["status"] == "not_implemented"
    assert log[0]["tool"] == "github_search"


def test_call_tool_success_with_generic_dummy_impl(clean_tools_state):
    captured: Dict[str, Any] = {}

    def dummy_tool(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "results": ["ok"], "error": None}

    tools.ALLOWED_TOOLS.add("dummy")
    tools.TOOL_REGISTRY["dummy"] = dummy_tool

    resp = tools.call_tool("dummy", foo="bar", answer=42)
    assert resp["ok"] is True
    assert resp["results"] == ["ok"]
    assert captured["foo"] == "bar"
    assert captured["answer"] == 42

    # ログも success で 1件記録されているはず
    log = tools.get_tool_usage_log()
    assert len(log) == 1
    assert log[0]["status"] == "success"
    assert log[0]["tool"] == "dummy"
    assert "latency_ms" in log[0]


def test_call_tool_web_search_branch_uses_query_and_max_results(clean_tools_state):
    captured: Dict[str, Any] = {}

    def dummy_web_search(query: str, max_results: int = 5):
        captured["query"] = query
        captured["max_results"] = max_results
        return {"ok": True, "results": [query] * max_results, "error": None}

    tools.ALLOWED_TOOLS.add("web_search")
    tools.TOOL_REGISTRY["web_search"] = dummy_web_search

    resp = tools.call_tool("web_search", query="AGI", max_results=3)
    assert resp["ok"] is True
    assert resp["results"] == ["AGI", "AGI", "AGI"]
    assert captured["query"] == "AGI"
    assert captured["max_results"] == 3


def test_call_tool_normalizes_kind_for_registry_lookup(clean_tools_state):
    captured: Dict[str, Any] = {}

    def dummy_web_search(query: str, max_results: int = 5):
        captured["query"] = query
        captured["max_results"] = max_results
        return {"ok": True, "results": [query], "error": None}

    tools.ALLOWED_TOOLS.add("web_search")
    tools.TOOL_REGISTRY["web_search"] = dummy_web_search

    resp = tools.call_tool(" Web_Search ", query="veritas", max_results=1)
    assert resp["ok"] is True
    assert resp["results"] == ["veritas"]
    assert captured["query"] == "veritas"
    assert captured["max_results"] == 1


# =========================
# ツール管理 API
# =========================

def test_tool_whitelist_and_blocklist_management(clean_tools_state):
    tools.add_allowed_tool("calc")
    assert "calc" in tools.get_allowed_tools()

    tools.block_tool("calc")
    assert "calc" in tools.get_blocked_tools()
    assert "calc" not in tools.get_allowed_tools()

    tools.unblock_tool("calc")
    assert "calc" not in tools.get_blocked_tools()

    tools.remove_allowed_tool("calc")  # 実行してもエラーにならないことだけ確認


def test_get_available_tools_marks_flags(clean_tools_state):
    def dummy_tool():
        return {"ok": True, "results": [], "error": None}

    tools.ALLOWED_TOOLS.add("dummy")
    tools.TOOL_REGISTRY["dummy"] = dummy_tool
    tools.BLOCKED_TOOLS.add("dangerous")

    info = tools.get_available_tools()

    assert "dummy" in info
    assert info["dummy"]["allowed"] is True
    assert info["dummy"]["blocked"] is False
    assert info["dummy"]["implemented"] is True

    assert "dangerous" in info
    assert info["dangerous"]["allowed"] is False
    assert info["dangerous"]["blocked"] is True
    # BLOCKED_TOOLS 側は TOOL_REGISTRY に無いので implemented=False
    assert info["dangerous"]["implemented"] is False


# =========================
# ログ & 統計
# =========================

def test_sanitize_args_redacts_and_truncates():
    long_text = "x" * 300
    args = {
        "api_key": "secret-key",
        "token": "t0k3n",
        "password": "pw",
        "normal": "ok",
        "body": long_text,
    }

    sanitized = tools._sanitize_args(args)

    assert sanitized["api_key"] == "***REDACTED***"
    assert sanitized["token"] == "***REDACTED***"
    assert sanitized["password"] == "***REDACTED***"
    assert sanitized["normal"] == "ok"
    assert len(sanitized["body"]) < len(long_text)
    assert sanitized["body"].endswith("...")




def test_sanitize_args_redacts_nested_sensitive_values():
    args = {
        "headers": {"Authorization": "Bearer super-secret-token"},
        "payload": {"nested_api_key": "my-key", "safe": "value"},
        "list_values": [
            {"auth_token": "abc"},
            "x" * 250,
        ],
    }

    sanitized = tools._sanitize_args(args)

    assert sanitized["headers"]["Authorization"] == "***REDACTED***"
    assert sanitized["payload"]["nested_api_key"] == "***REDACTED***"
    assert sanitized["payload"]["safe"] == "value"
    assert sanitized["list_values"][0]["auth_token"] == "***REDACTED***"
    assert sanitized["list_values"][1].endswith("...")


def test_sanitize_args_normalizes_hyphenated_sensitive_keys():
    args = {"x-api-key": "secret", "db-password": "pw", "normal": "ok"}

    sanitized = tools._sanitize_args(args)

    assert sanitized["x-api-key"] == "***REDACTED***"
    assert sanitized["db-password"] == "***REDACTED***"
    assert sanitized["normal"] == "ok"


def test_sanitize_args_converts_tuple_to_list_for_json_safety():
    args = {
        "events": (
            {"Authorization": "Bearer token-value"},
            "ok",
        )
    }

    sanitized = tools._sanitize_args(args)

    assert isinstance(sanitized["events"], list)
    assert sanitized["events"][0]["Authorization"] == "***REDACTED***"
    assert sanitized["events"][1] == "ok"

def test_sanitize_args_converts_set_to_sorted_list_for_json_safety():
    args = {
        "scopes": {"write", "read", "admin"},
        "mixed": {("b", 2), ("a", 1)},
    }

    sanitized = tools._sanitize_args(args)

    assert sanitized["scopes"] == ["admin", "read", "write"]
    assert isinstance(sanitized["mixed"], list)
    assert sanitized["mixed"] == [["a", 1], ["b", 2]]

def test_get_tool_stats_empty_when_no_calls(clean_tools_state):
    stats = tools.get_tool_stats()
    assert stats["total_calls"] == 0
    assert math.isclose(stats["success_rate"], 0.0)
    assert stats["allowed_tools_count"] == len(tools.ALLOWED_TOOLS)
    assert stats["blocked_tools_count"] == len(tools.BLOCKED_TOOLS)


def test_get_tool_usage_log_returns_empty_for_negative_limit(clean_tools_state):
    tools._log_tool_usage(tool="dummy", args={}, status="success")

    assert tools.get_tool_usage_log(limit=-1) == []


def test_get_tool_stats_counts_success_and_status(clean_tools_state):
    # 成功 1件
    def dummy_tool():
        return {"ok": True, "results": [1], "error": None}

    tools.ALLOWED_TOOLS.add("dummy")
    tools.TOOL_REGISTRY["dummy"] = dummy_tool

    tools.call_tool("dummy")
    # 拒否 1件
    tools.call_tool("not_allowed")

    stats = tools.get_tool_stats()
    assert stats["total_calls"] == 2
    assert stats["by_tool"]["dummy"] == 1
    assert stats["by_tool"]["not_allowed"] == 1
    assert stats["by_status"]["success"] == 1
    assert stats["by_status"]["denied"] == 1

    # success_rate が 0〜1 の範囲で、1/2 付近
    assert 0.0 <= stats["success_rate"] <= 1.0
    assert math.isclose(stats["success_rate"], 0.5, rel_tol=1e-6)
