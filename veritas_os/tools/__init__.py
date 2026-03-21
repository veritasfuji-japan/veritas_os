#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VERITAS Environment Tools
- web_search, github_search, llm_safety などの共通ディスパッチ
"""
from __future__ import annotations

import importlib
from typing import Any, Dict

_DEFAULT_MAX_RESULTS = 5
_DEFAULT_MAX_CATEGORIES = 5
_MIN_LIMIT = 1
_MAX_RESULTS_LIMIT = 100
_MAX_CATEGORIES_LIMIT = 20

web_search = None
github_search_repos = None
llm_safety_run = None


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


def _resolve_tool_callable(
    attr_name: str,
    module_name: str,
    export_name: str,
) -> Any:
    """Resolve optional tool implementations lazily for sparse environments."""
    current = globals().get(attr_name)
    if callable(current):
        return current

    module = importlib.import_module(module_name)
    resolved = getattr(module, export_name)
    globals()[attr_name] = resolved
    return resolved


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
        tool_impl = _resolve_tool_callable(
            "web_search",
            "veritas_os.tools.web_search",
            "web_search",
        )
        return tool_impl(
            query=kwargs.get("query", ""),
            max_results=max_results,
        )

    # --- GitHub 検索 ---
    if normalized_kind == "github_search":
        tool_impl = _resolve_tool_callable(
            "github_search_repos",
            "veritas_os.tools.github_adapter",
            "github_search_repos",
        )
        return tool_impl(
            query=kwargs.get("query", ""),
            max_results=max_results,
        )

    # --- LLM ベース安全ヘッド ---
    if normalized_kind == "llm_safety":
        tool_impl = _resolve_tool_callable(
            "llm_safety_run",
            "veritas_os.tools.llm_safety",
            "run",
        )
        # llm_safety.run(text=..., context=..., alternatives=...)
        return tool_impl(
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
