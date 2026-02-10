#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GitHub Adapter for VERITAS Environment Tools
- 公開リポジトリを簡易検索するヘルパー
"""

import logging
import os
import random
import time

import requests


GITHUB_TOKEN = os.environ.get("VERITAS_GITHUB_TOKEN", "").strip()
GITHUB_MAX_RETRIES = int(os.getenv("VERITAS_GITHUB_MAX_RETRIES", "3"))
GITHUB_RETRY_DELAY = float(os.getenv("VERITAS_GITHUB_RETRY_DELAY", "1.0"))
GITHUB_RETRY_MAX_DELAY = float(os.getenv("VERITAS_GITHUB_RETRY_MAX_DELAY", "8.0"))
GITHUB_RETRY_JITTER = float(os.getenv("VERITAS_GITHUB_RETRY_JITTER", "0.1"))

# URL が長くなりすぎないようにクエリ長を制限
MAX_QUERY_LEN = 256

# GitHub API の per_page 上限
GITHUB_API_MAX_PER_PAGE = 100

logger = logging.getLogger(__name__)


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


def _compute_backoff(attempt: int) -> float:
    """指数バックオフの待機時間を算出する（ジッター込み）。"""
    base_delay = max(GITHUB_RETRY_DELAY, 0.0)
    max_delay = max(GITHUB_RETRY_MAX_DELAY, base_delay)
    jitter = max(GITHUB_RETRY_JITTER, 0.0)
    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
    if jitter:
        delay += random.uniform(0, delay * jitter)
    return delay


def _should_retry_status(status_code: int) -> bool:
    """再試行対象のHTTPステータスかどうかを判定する。"""
    return status_code in {403, 429} or status_code >= 500


def _get_with_retry(
    url: str,
    headers: dict,
    params: dict,
    timeout: int,
) -> requests.Response:
    """GitHub API 呼び出しを再試行しつつ実行する。"""
    last_exc: Exception | None = None
    for attempt in range(1, GITHUB_MAX_RETRIES + 1):
        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=timeout,
            )
            status_code = getattr(response, "status_code", None)
            if status_code is not None and _should_retry_status(status_code):
                if attempt < GITHUB_MAX_RETRIES:
                    delay = _compute_backoff(attempt)
                    logger.warning(
                        "GitHub retryable status=%s attempt=%s, sleep=%.2fs",
                        status_code,
                        attempt,
                        delay,
                    )
                    time.sleep(delay)
                    continue
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            if attempt < GITHUB_MAX_RETRIES:
                delay = _compute_backoff(attempt)
                logger.warning(
                    "GitHub request error attempt=%s, sleep=%.2fs: %s: %s",
                    attempt,
                    delay,
                    type(exc).__name__,
                    exc,
                )
                time.sleep(delay)
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("GitHub request failed without exception")


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
            "error": "GitHub API unavailable",
        }

    q, truncated = _prepare_query(query)

    if not q:
        return {
            "ok": False,
            "results": [],
            "error": "empty_query",
        }

    url = "https://api.github.com/search/repositories"
    # GitHub API の per_page は最大100なので制限する
    # ★ セキュリティ修正: 負の値・非数値型も防止
    try:
        per_page = max(1, min(int(max_results), GITHUB_API_MAX_PER_PAGE))
    except (ValueError, TypeError):
        per_page = 5
    params = {
        "q": q,
        "per_page": per_page,
    }
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
    }

    try:
        r = _get_with_retry(url, headers=headers, params=params, timeout=20)
        data = r.json()
    except Exception as e:
        # ★ セキュリティ修正: 内部例外の詳細をレスポンスに含めない
        logger.warning("GitHub API error: %s: %s", type(e).__name__, e)
        return {
            "ok": False,
            "results": [],
            "error": "GitHub API error: request failed",
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
