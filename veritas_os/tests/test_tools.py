# veritas_os/tests/test_tools.py

import pytest
from typing import Any, Dict, List

# ★ 実体は veritas_os/core/tools.py なのでこちらをインポート
from veritas_os.core import tools as toolos


def _reset_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    グローバル状態（ALLOWED/BLOCKED/REGISTRY/LOG）を
    テストごとにクリーンな状態にするヘルパー
    """
    monkeypatch.setattr(toolos, "ALLOWED_TOOLS", set(), raising=False)
    monkeypatch.setattr(toolos, "BLOCKED_TOOLS", set(), raising=False)
    monkeypatch.setattr(toolos, "TOOL_REGISTRY", {}, raising=False)
    monkeypatch.setattr(toolos, "_tool_usage_log", [], raising=False)


# =========================
# allowed() のテスト
# =========================

def test_allowed_basic(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_state(monkeypatch)

    toolos.ALLOWED_TOOLS.update({"web_search", "llm_safety"})
    toolos.BLOCKED_TOOLS.update({"shell_exec"})

    # ホワイトリストにあるものは True
    assert toolos.allowed("web_search") is True
    # 大文字・空白付きも正規化されて True
    assert toolos.allowed("  WEB_SEARCH  ") is True

    # ブロックされているものは False
    assert toolos.allowed("shell_exec") is False

    # 未登録は False
    assert toolos.allowed("unknown_tool") is False

    # 空文字は False
    assert toolos.allowed("") is False


# =========================
# call_tool() - denied 系
# =========================

def test_call_tool_denied_not_in_whitelist(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_state(monkeypatch)

    result = toolos.call_tool("unknown_tool", query="test")

    assert result["ok"] is False
    assert result["results"] == []
    assert result["meta"]["status"] == "denied"
    # ホワイトリストに無いので not_in_whitelist
    assert result["meta"]["reason"] == "not_in_whitelist"

    log = toolos.get_tool_usage_log()
    assert len(log) == 1
    assert log[0]["status"] == "denied"
    assert log[0]["tool"] == "unknown_tool"


def test_call_tool_denied_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_state(monkeypatch)

    toolos.ALLOWED_TOOLS.update({"web_search"})
    toolos.BLOCKED_TOOLS.update({"web_search"})

    result = toolos.call_tool("web_search", query="AGI")

    assert result["ok"] is False
    assert result["meta"]["status"] == "denied"
    assert result["meta"]["reason"] == "blocked"

    log = toolos.get_tool_usage_log()
    assert len(log) == 1
    assert log[0]["status"] == "denied"
    assert log[0]["tool"] == "web_search"


def test_call_tool_not_implemented(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_state(monkeypatch)

    # ホワイトリストにはあるが、実装がレジストリに無いケース
    toolos.ALLOWED_TOOLS.update({"web_search"})

    result = toolos.call_tool("web_search", query="AGI")

    assert result["ok"] is False
    assert result["meta"]["status"] == "not_implemented"

    log = toolos.get_tool_usage_log()
    assert len(log) == 1
    assert log[0]["status"] == "not_implemented"
    assert log[0]["tool"] == "web_search"


# =========================
# call_tool() - success 系
# =========================

def test_call_tool_success_generic_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_state(monkeypatch)

    # call_tool が期待している「dict 形式の結果」を返すダミーツール
    def dummy_tool(query: str = "", max_results: int = 5) -> Dict[str, Any]:
        return {
            "ok": True,
            "results": [f"Q={query}", f"max={max_results}"],
            "error": None,
            "meta": {"impl": "dummy"},
        }

    toolos.ALLOWED_TOOLS.update({"dummy"})
    toolos.TOOL_REGISTRY["dummy"] = dummy_tool

    result = toolos.call_tool("dummy", query="hello", max_results=3)

    # call_tool はそのまま返す仕様想定
    assert result["ok"] is True
    assert result["results"] == ["Q=hello", "max=3"]
    assert result["error"] is None
    assert result["meta"]["impl"] == "dummy"

    log = toolos.get_tool_usage_log()
    assert len(log) == 1
    entry = log[0]
    assert entry["status"] == "success"
    assert entry["tool"] == "dummy"
    assert "latency_ms" in entry
    summary = entry.get("result_summary")
    assert summary is not None
    assert summary["ok"] is True
    assert summary["has_error"] is False
    assert summary["result_count"] == 2


def test_call_tool_success_web_search_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_state(monkeypatch)

    captured: List[Dict[str, Any]] = []

    # web_search 用の引数の受け渡しを確認するダミー
    def dummy_web_search(query: str = "", max_results: int = 5) -> Dict[str, Any]:
        captured.append({"query": query, "max_results": max_results})
        return {
            "ok": True,
            "results": [query, max_results],
            "error": None,
            "meta": {"impl": "web_search"},
        }

    toolos.ALLOWED_TOOLS.update({"web_search"})
    toolos.TOOL_REGISTRY["web_search"] = dummy_web_search

    result = toolos.call_tool("web_search", query="AGI", max_results=7)

    assert result["ok"] is True
    assert result["results"] == ["AGI", 7]
    assert captured == [{"query": "AGI", "max_results": 7}]


# =========================
# block / unblock / allowed ツールセット
# =========================

def test_add_and_remove_allowed_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_state(monkeypatch)

    toolos.add_allowed_tool("WEB_SEARCH")
    assert "web_search" in toolos.ALLOWED_TOOLS

    toolos.remove_allowed_tool("web_search")
    assert "web_search" not in toolos.ALLOWED_TOOLS


def test_block_and_unblock_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_state(monkeypatch)

    toolos.ALLOWED_TOOLS.update({"web_search"})

    # block すると BLOCKED に入り、ALLOWED からは消える
    toolos.block_tool("web_search")
    assert "web_search" in toolos.BLOCKED_TOOLS
    assert "web_search" not in toolos.ALLOWED_TOOLS

    # unblock すると BLOCKED からは消える（ALLOWED には自動では戻さない）
    toolos.unblock_tool("web_search")
    assert "web_search" not in toolos.BLOCKED_TOOLS


def test_get_allowed_and_blocked_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_state(monkeypatch)

    toolos.ALLOWED_TOOLS.update({"web_search"})
    toolos.BLOCKED_TOOLS.update({"exec"})

    allowed = toolos.get_allowed_tools()
    blocked = toolos.get_blocked_tools()

    assert allowed == {"web_search"}
    assert blocked == {"exec"}


# =========================
# get_available_tools
# =========================

def test_get_available_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_state(monkeypatch)

    def dummy() -> str:
        return "ok"

    toolos.ALLOWED_TOOLS.update({"web_search"})
    toolos.BLOCKED_TOOLS.update({"exec"})
    toolos.TOOL_REGISTRY["web_search"] = dummy

    tools = toolos.get_available_tools()

    # ホワイトリスト側
    assert "web_search" in tools
    assert tools["web_search"]["implemented"] is True
    assert tools["web_search"]["allowed"] is True
    assert tools["web_search"]["blocked"] is False

    # ブロック側
    assert "exec" in tools
    assert tools["exec"]["implemented"] is False
    assert tools["exec"]["allowed"] is False
    assert tools["exec"]["blocked"] is True


# =========================
# ログ & 統計
# =========================

def test_clear_tool_usage_log_and_get_stats_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_state(monkeypatch)

    # 念のため何件かログを入れてから clear
    toolos._tool_usage_log.extend(
        [
            {"tool": "x", "status": "success"},
            {"tool": "y", "status": "error"},
        ]
    )
    toolos.clear_tool_usage_log()

    log = toolos.get_tool_usage_log()
    assert log == []

    stats = toolos.get_tool_stats()
    assert stats["total_calls"] == 0
    assert stats["success_rate"] == 0.0
    assert stats["by_tool"] == {}
    assert stats["by_status"] == {}
    assert stats["allowed_tools_count"] == len(toolos.ALLOWED_TOOLS)
    assert stats["blocked_tools_count"] == len(toolos.BLOCKED_TOOLS)
    assert stats["implemented_tools_count"] == len(toolos.TOOL_REGISTRY)


def test_get_tool_stats_with_success_and_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_state(monkeypatch)

    # ログを手動で2件入れる
    toolos._tool_usage_log.extend(
        [
            {"tool": "web_search", "status": "success"},
            {"tool": "web_search", "status": "error"},
        ]
    )

    stats = toolos.get_tool_stats()

    assert stats["total_calls"] == 2
    assert stats["success_rate"] == 0.5  # success 1/2
    assert stats["by_tool"]["web_search"] == 2
    assert stats["by_status"]["success"] == 1
    assert stats["by_status"]["error"] == 1


# =========================
# _sanitize_args の簡単チェック
# =========================

def test_sanitize_args_basic() -> None:
    args = {
        "api_key": "SECRET",
        "token": "TOKEN",
        "password": "PASS",
        "normal": "short",
        "long": "x" * 300,
    }

    sanitized = toolos._sanitize_args(args)

    assert sanitized["api_key"] == "***REDACTED***"
    assert sanitized["token"] == "***REDACTED***"
    assert sanitized["password"] == "***REDACTED***"
    assert sanitized["normal"] == "short"
    assert len(sanitized["long"]) < 250  # 途中で切れている想定


