#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GitHub Adapter for VERITAS Environment Tools
- 公開リポジトリを簡易検索するヘルパー
"""

import logging
import os
import random
import re
import time

import requests


def _safe_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


def _safe_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


GITHUB_MAX_RETRIES = _safe_int("VERITAS_GITHUB_MAX_RETRIES", 3)
GITHUB_RETRY_DELAY = _safe_float("VERITAS_GITHUB_RETRY_DELAY", 1.0)
GITHUB_RETRY_MAX_DELAY = _safe_float("VERITAS_GITHUB_RETRY_MAX_DELAY", 8.0)
GITHUB_RETRY_JITTER = _safe_float("VERITAS_GITHUB_RETRY_JITTER", 0.1)

# URL が長くなりすぎないようにクエリ長を制限
MAX_QUERY_LEN = 256

# GitHub API の per_page 上限
GITHUB_API_MAX_PER_PAGE = 100

logger = logging.getLogger(__name__)

_RE_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _get_github_token() -> str:
    """Return the latest GitHub token from environment variables.

    The token is resolved at call time so that emergency token rotations can
    take effect without restarting the running process.
    """
    return os.getenv("VERITAS_GITHUB_TOKEN", "").strip()


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
    q = _RE_CONTROL_CHARS.sub(" ", q)
    q = " ".join(q.split())
    truncated = False
    if len(q) > max_len:
        q = q[:max_len]
        truncated = True
    return q, truncated


def _normalize_repo_item(item: dict) -> dict:
    """Normalize a GitHub repository item with safe default values."""
    stars = item.get("stargazers_count", 0)
    if not isinstance(stars, int):
        try:
            stars = int(stars)
        except (TypeError, ValueError):
            stars = 0

    return {
        "full_name": str(item.get("full_name") or ""),
        "html_url": str(item.get("html_url") or ""),
        "description": str(item.get("description") or ""),
        "stars": stars,
    }


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
    token = _get_github_token()
    if not token:
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
        "Authorization": f"Bearer {token}",
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
    results = [_normalize_repo_item(it) for it in items if isinstance(it, dict)]

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
