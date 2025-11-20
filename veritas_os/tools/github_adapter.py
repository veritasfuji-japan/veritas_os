#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GitHub Adapter for VERITAS Environment Tools
- 公開リポジトリを簡易検索するヘルパー
"""

import os
import requests


GITHUB_TOKEN = os.environ.get("VERITAS_GITHUB_TOKEN", "")

# URL が長くなりすぎないようにクエリ長を制限
MAX_QUERY_LEN = 256


def _prepare_query(raw: str, max_len: int = MAX_QUERY_LEN) -> tuple[str, bool]:
    """
    生のクエリ文字列を GitHub API 用に整形する。
    - 改行 → スペース
    - 前後の空白をトリム
    - 長すぎる場合は max_len でカット
    戻り値: (整形後クエリ, 途中でトリムしたかどうか)
    """
    if raw is None:
        raw = ""
    q = str(raw).replace("\n", " ").replace("\r", " ").strip()
    truncated = False
    if len(q) > max_len:
        q = q[:max_len]
        truncated = True
    return q, truncated


def github_search_repos(query: str, max_results: int = 5) -> dict:
    """
    GitHub のリポジトリ検索
    戻り値:
        {
          "ok": bool,
          "results": [ { "full_name": str, "html_url": str,
                         "description": str, "stars": int }, ... ],
          "error": str | None,
          "meta": { ... }
        }
    """
    if not GITHUB_TOKEN:
        return {
            "ok": False,
            "results": [],
            "error": "GITHUB_API not configured (set VERITAS_GITHUB_TOKEN)",
        }

    q, truncated = _prepare_query(query)

    if not q:
        return {
            "ok": False,
            "results": [],
            "error": "empty_query",
        }

    url = "https://api.github.com/search/repositories"
    params = {
        "q": q,
        "per_page": max_results,
    }
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
    }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return {
            "ok": False,
            "results": [],
            "error": f"GitHub API error: {e}",
        }

    items = data.get("items", []) or []
    results = []
    for it in items:
        results.append(
            {
                "full_name": it.get("full_name"),
                "html_url": it.get("html_url"),
                "description": it.get("description"),
                "stars": it.get("stargazers_count", 0),
            }
        )

    return {
        "ok": True,
        "results": results,
        "error": None,
        "meta": {
            "raw_count": len(items),
            "truncated_query": truncated,
            "used_query": q,
        },
    }

