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
from .llm_safety import run as llm_safety_run

_DEFAULT_MAX_RESULTS = 5
_DEFAULT_MAX_CATEGORIES = 5
_MIN_LIMIT = 1
_MAX_RESULTS_LIMIT = 100
_MAX_CATEGORIES_LIMIT = 20


def _normalize_kind(kind: Any) -> str:
    """Normalize tool kind safely for dispatch."""
    return str(kind).strip().lower()


def _clamp_int(
    value: Any,
    *,
    default: int,
    min_value: int,
    max_value: int,
) -> int:
    """Convert ``value`` to int and clamp it to a safe range."""
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, normalized))


def call_tool(kind: str, **kwargs: Any) -> Dict[str, Any]:
    """
    kind でツールを振り分ける共通インターフェイス
    """
    normalized_kind = _normalize_kind(kind)
    if not normalized_kind:
        return {
            "ok": False,
            "results": [],
            "error": "unknown tool: ",
        }

    max_results = _clamp_int(
        kwargs.get("max_results", _DEFAULT_MAX_RESULTS),
        default=_DEFAULT_MAX_RESULTS,
        min_value=_MIN_LIMIT,
        max_value=_MAX_RESULTS_LIMIT,
    )

    max_categories = _clamp_int(
        kwargs.get("max_categories", _DEFAULT_MAX_CATEGORIES),
        default=_DEFAULT_MAX_CATEGORIES,
        min_value=_MIN_LIMIT,
        max_value=_MAX_CATEGORIES_LIMIT,
    )

    # --- web 検索 ---
    if normalized_kind == "web_search":
        return web_search(
            query=kwargs.get("query", ""),
            max_results=max_results,
        )

    # --- GitHub 検索 ---
    if normalized_kind == "github_search":
        return github_search_repos(
            query=kwargs.get("query", ""),
            max_results=max_results,
        )

    # --- LLM ベース安全ヘッド ---
    if normalized_kind == "llm_safety":
        # llm_safety.run(text=..., context=..., alternatives=...)
        return llm_safety_run(
            text=kwargs.get("text", "") or kwargs.get("query", ""),
            context=kwargs.get("context") or {},
            alternatives=kwargs.get("alternatives") or [],
            max_categories=max_categories,
        )

    # --- 未知ツール ---
    return {
        "ok": False,
        "results": [],
        "error": f"unknown tool: {normalized_kind}",
    }
