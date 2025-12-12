# veritas_os/tests/test_tools_env.py

from __future__ import annotations

from typing import Any, Dict, List

import veritas_os.tools as tools
from veritas_os.tools import call_tool


def test_call_tool_web_search(monkeypatch):
    """kind=web_search で web_search(...) が正しく呼ばれるか。"""

    calls: List[Dict[str, Any]] = []

    def fake_web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
        calls.append({"query": query, "max_results": max_results})
        return {"ok": True, "results": ["web"]}

    # tools.__init__ 内の web_search を差し替え
    monkeypatch.setattr(tools, "web_search", fake_web_search, raising=False)

    out = call_tool("web_search", query="veritas os", max_results=3)

    assert out == {"ok": True, "results": ["web"]}
    assert len(calls) == 1
    assert calls[0]["query"] == "veritas os"
    assert calls[0]["max_results"] == 3


def test_call_tool_github_search(monkeypatch):
    """kind=github_search で github_search_repos(...) が正しく呼ばれるか。"""

    calls: List[Dict[str, Any]] = []

    def fake_github_search_repos(
        query: str, max_results: int = 5
    ) -> Dict[str, Any]:
        calls.append({"query": query, "max_results": max_results})
        return {"ok": True, "results": ["repo1", "repo2"]}

    monkeypatch.setattr(
        tools, "github_search_repos", fake_github_search_repos, raising=False
    )

    out = call_tool("github_search", query="veritas_os", max_results=10)

    assert out["ok"] is True
    assert out["results"] == ["repo1", "repo2"]
    assert len(calls) == 1
    assert calls[0]["query"] == "veritas_os"
    assert calls[0]["max_results"] == 10


def test_call_tool_llm_safety_with_text_and_defaults(monkeypatch):
    """
    kind=llm_safety で llm_safety_run(...) が
    text/context/alternatives/max_categories 付きで呼ばれるか。
    """

    calls: List[Dict[str, Any]] = []

    def fake_llm_safety_run(
        text: str,
        context: Dict[str, Any],
        alternatives: list,
        max_categories: int = 5,
    ) -> Dict[str, Any]:
        calls.append(
            {
                "text": text,
                "context": context,
                "alternatives": alternatives,
                "max_categories": max_categories,
            }
        )
        return {"ok": True, "categories": ["safe"]}

    monkeypatch.setattr(tools, "llm_safety_run", fake_llm_safety_run, 
raising=False)

    out = call_tool(
        "llm_safety",
        text="some risky prompt",
        context={"user": "u1"},
        alternatives=[{"title": "A"}],
        max_categories=7,
    )

    assert out == {"ok": True, "categories": ["safe"]}
    assert len(calls) == 1
    c = calls[0]
    assert c["text"] == "some risky prompt"
    assert c["context"] == {"user": "u1"}
    assert c["alternatives"] == [{"title": "A"}]
    assert c["max_categories"] == 7


def test_call_tool_llm_safety_falls_back_to_query(monkeypatch):
    """
    text が無い場合に query が text として渡される分岐を踏む。
    """

    calls: List[Dict[str, Any]] = []

    def fake_llm_safety_run(
        text: str,
        context: Dict[str, Any],
        alternatives: list,
        max_categories: int = 5,
    ) -> Dict[str, Any]:
        calls.append(
            {
                "text": text,
                "context": context,
                "alternatives": alternatives,
                "max_categories": max_categories,
            }
        )
        return {"ok": True}

    monkeypatch.setattr(tools, "llm_safety_run", fake_llm_safety_run, 
raising=False)

    # text を渡さず query だけ渡して fallback を確認
    out = call_tool("llm_safety", query="use this as text")

    assert out == {"ok": True}
    assert len(calls) == 1
    c = calls[0]
    assert c["text"] == "use this as text"          # ★ text fallback 分岐
    assert c["context"] == {}                       # デフォルト {}
    assert c["alternatives"] == []                  # デフォルト []
    assert c["max_categories"] == 5                 # デフォルト 5


def test_call_tool_unknown():
    """未知 kind のとき unknown tool エラー分岐を踏む。"""

    out = call_tool("totally_unknown_tool", foo="bar")

    assert out["ok"] is False
    assert out["results"] == []
    assert "unknown tool" in out["error"]
    assert "totally_unknown_tool" in out["error"]

