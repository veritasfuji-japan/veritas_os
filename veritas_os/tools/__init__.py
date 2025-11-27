#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VERITAS Environment Tools
- web_search, github_search, llm_safety などの共通ディスパッチ
"""
from __future__ import annotations

from typing import Any, Dict

from .web_search import web_search
from .github_adapter import github_search_repos
from .llm_safety import run as llm_safety_run   # ★ 追加：LLM 安全ヘッド


def call_tool(kind: str, **kwargs: Any) -> Dict[str, Any]:
    """
    kind でツールを振り分ける共通インターフェイス
    """
    # --- web 検索 ---
    if kind == "web_search":
        return web_search(
            query=kwargs.get("query", ""),
            max_results=kwargs.get("max_results", 5),
        )

    # --- GitHub 検索 ---
    if kind == "github_search":
        return github_search_repos(
            query=kwargs.get("query", ""),
            max_results=kwargs.get("max_results", 5),
        )

    # --- LLM ベース安全ヘッド ---
    if kind == "llm_safety":
        # llm_safety.run(text=..., context=..., alternatives=...)
        return llm_safety_run(
            text=kwargs.get("text", "") or kwargs.get("query", ""),
            context=kwargs.get("context") or {},
            alternatives=kwargs.get("alternatives") or [],
            max_categories=kwargs.get("max_categories", 5),
        )

    # --- 未知ツール ---
    return {
        "ok": False,
        "results": [],
        "error": f"unknown tool: {kind}",
    }
