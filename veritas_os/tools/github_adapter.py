#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GitHub Adapter for VERITAS Environment Tools
- 公開リポジトリを簡易検索するヘルパー
"""

import logging
import math
import os
import random
import re
import time
from urllib.parse import urlsplit

import requests


def _safe_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


def _safe_float(key: str, default: float) -> float:
    """環境変数を有限な float として取得し、異常値は default に戻す。"""
    try:
        value = float(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default
    if not math.isfinite(value):
        return default
    return value


GITHUB_MAX_RETRIES = max(_safe_int("VERITAS_GITHUB_MAX_RETRIES", 3), 1)
GITHUB_RETRY_DELAY = _safe_float("VERITAS_GITHUB_RETRY_DELAY", 1.0)
GITHUB_RETRY_MAX_DELAY = _safe_float("VERITAS_GITHUB_RETRY_MAX_DELAY", 8.0)
GITHUB_RETRY_JITTER = _safe_float("VERITAS_GITHUB_RETRY_JITTER", 0.1)

# URL が長くなりすぎないようにクエリ長を制限
MAX_QUERY_LEN = 256

# GitHub API の per_page 上限
GITHUB_API_MAX_PER_PAGE = 100

logger = logging.getLogger(__name__)

_RE_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TRUSTED_GITHUB_HOSTS = {"github.com", "www.github.com"}
_RE_REPO_PATH = re.compile(r"^/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$")
_RESERVED_GITHUB_PATH_ROOTS = {
    "about",
    "account",
    "apps",
    "collections",
    "explore",
    "features",
    "issues",
    "join",
    "login",
    "marketplace",
    "new",
    "notifications",
    "orgs",
    "organizations",
    "pricing",
    "pulls",
    "search",
    "settings",
    "site",
    "sponsors",
    "topics",
}


def _get_github_token() -> str:
    """Return the latest GitHub token from environment variables.

    The token is resolved at call time so that emergency token rotations can
    take effect without restarting the running process.

    Security:
        Tokens containing control characters are rejected. This prevents
        malformed ``Authorization`` headers and reduces header-injection risk
        from accidentally tainted environment values.
    """
    raw_token = os.getenv("VERITAS_GITHUB_TOKEN", "")
    token = raw_token.strip()
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in token):
        logger.warning("VERITAS_GITHUB_TOKEN contains control characters")
        return ""
    return token


def _get_retry_settings() -> tuple[int, float, float, float]:
    """Return GitHub retry settings from current environment values.

    Reading these values at call time allows emergency configuration updates
    (e.g. temporarily lowering retries during incidents) without restarting
    the process.
    """
    max_retries = max(_safe_int("VERITAS_GITHUB_MAX_RETRIES", GITHUB_MAX_RETRIES), 1)
    retry_delay = _safe_float("VERITAS_GITHUB_RETRY_DELAY", GITHUB_RETRY_DELAY)
    retry_max_delay = _safe_float(
        "VERITAS_GITHUB_RETRY_MAX_DELAY", GITHUB_RETRY_MAX_DELAY
    )
    retry_jitter = _safe_float("VERITAS_GITHUB_RETRY_JITTER", GITHUB_RETRY_JITTER)
    return max_retries, retry_delay, retry_max_delay, retry_jitter


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

    html_url = _sanitize_html_url(item.get("html_url"))
    full_name = _sanitize_text_field(item.get("full_name"), max_len=256)
    description = _sanitize_text_field(item.get("description"), max_len=1024)

    return {
        "full_name": full_name,
        "html_url": html_url,
        "description": description,
        "stars": stars,
    }


def _sanitize_text_field(raw_value: object, *, max_len: int) -> str:
    """Return a bounded string with ASCII control characters removed.

    Security policy:
        GitHub metadata is external input and may contain control characters
        (e.g. terminal escape fragments). This sanitizer strips such bytes,
        collapses whitespace, and enforces a maximum length before values are
        returned to callers or logs.
    """
    value = _RE_CONTROL_CHARS.sub(" ", str(raw_value or ""))
    value = " ".join(value.split())
    if len(value) > max_len:
        return value[:max_len]
    return value


def _sanitize_html_url(raw_url: object) -> str:
    """Return a safe GitHub repository URL or an empty string.

    Only absolute HTTPS URLs are accepted to reduce the risk of unsafe
    schemes (e.g. ``javascript:``), downgraded transport, or malformed link
    injection.

    Security policy:
        - Only GitHub hosts are allowed because this field is rendered as an
          external link in clients and should never point to arbitrary domains.
        - URL-embedded credentials are always rejected to prevent accidental
          leakage of secrets via logs or UI.
        - Explicit non-default ports are rejected to avoid ambiguous
          destinations and reduce risks from host spoofing tricks.
        - Query strings and fragments are rejected to avoid displaying tracking
          parameters or ambiguous destinations.
        - Only canonical repository paths (``/owner/repo``) are accepted.
    """
    url = str(raw_url or "").strip()
    if not url:
        return ""

    parsed = urlsplit(url)
    if parsed.scheme != "https":
        logger.warning("Dropped GitHub html_url with unsafe scheme: %r", parsed.scheme)
        return ""
    if not parsed.netloc:
        logger.warning("Dropped GitHub html_url without host")
        return ""
    if parsed.username or parsed.password:
        logger.warning("Dropped GitHub html_url containing credentials")
        return ""

    try:
        port = parsed.port
    except ValueError:
        logger.warning("Dropped GitHub html_url with invalid port")
        return ""

    if port not in (None, 443):
        logger.warning("Dropped GitHub html_url with unsupported port: %r", port)
        return ""

    if (parsed.hostname or "").lower() not in _TRUSTED_GITHUB_HOSTS:
        logger.warning("Dropped GitHub html_url with untrusted host: %r", parsed.hostname)
        return ""
    if parsed.query or parsed.fragment:
        logger.warning("Dropped GitHub html_url containing query or fragment")
        return ""
    if not _RE_REPO_PATH.fullmatch(parsed.path or ""):
        logger.warning("Dropped GitHub html_url with non-repo path: %r", parsed.path)
        return ""
    owner = (parsed.path or "").strip("/").split("/", maxsplit=1)[0].lower()
    if owner in _RESERVED_GITHUB_PATH_ROOTS:
        logger.warning("Dropped GitHub html_url with reserved root path: %r", owner)
        return ""
    return url


def _compute_backoff(
    attempt: int,
    retry_delay: float,
    retry_max_delay: float,
    retry_jitter: float,
) -> float:
    """指数バックオフの待機時間を算出する（ジッター込み）。"""
    base_delay = max(retry_delay, 0.0)
    max_delay = max(retry_max_delay, base_delay)
    jitter = max(retry_jitter, 0.0)
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
    max_retries, retry_delay, retry_max_delay, retry_jitter = _get_retry_settings()
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=timeout,
                allow_redirects=False,
            )
            status_code = getattr(response, "status_code", None)
            if status_code is not None and _should_retry_status(status_code):
                if attempt < max_retries:
                    delay = _compute_backoff(
                        attempt,
                        retry_delay,
                        retry_max_delay,
                        retry_jitter,
                    )
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
            if attempt < max_retries:
                delay = _compute_backoff(
                    attempt,
                    retry_delay,
                    retry_max_delay,
                    retry_jitter,
                )
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

    if not isinstance(data, dict):
        logger.warning(
            "GitHub API error: unexpected JSON payload type=%s",
            type(data).__name__,
        )
        return {
            "ok": False,
            "results": [],
            "error": "GitHub API error: invalid response payload",
        }

    items = data.get("items", []) or []
    if not isinstance(items, list):
        logger.warning(
            "GitHub API error: unexpected items payload type=%s",
            type(items).__name__,
        )
        return {
            "ok": False,
            "results": [],
            "error": "GitHub API error: invalid response payload",
        }

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
