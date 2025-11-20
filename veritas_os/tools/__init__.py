#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VERITAS Environment Tools
- web_search, github_search などの共通ディスパッチ
"""
from __future__ import annotations

from typing import Any, Dict, Callable
from .web_search import web_search
from .github_adapter import github_search_repos


def call_tool(kind: str, **kwargs) -> dict:
    """
    kind でツールを振り分ける共通インターフェイス
    """
    if kind == "web_search":
        return web_search(
            query=kwargs.get("query", ""),
            max_results=kwargs.get("max_results", 5),
        )

    if kind == "github_search":
        return github_search_repos(
            query=kwargs.get("query", ""),
            max_results=kwargs.get("max_results", 5),
        )

    return {
        "ok": False,
        "results": [],
        "error": f"unknown tool: {kind}",
    }
