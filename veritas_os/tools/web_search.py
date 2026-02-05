# veritas_os/tools/web_search.py
"""
VERITAS OS 用 Web検索アダプタ（Serper.dev 等の Google互換API を想定）

目的
- VERITAS OS の Web検索を行う。
- ただし「Veritas / Bureau Veritas」等の誤同定が起きやすいため、
  VERITAS OS を探している文脈では誤同定防止を強制する。

重要（テスト互換 / 実運用の両立）
- 通常クエリは「改変しない」：
    payload["q"] は入力 query と一致する（tests が要求）
- 通常クエリの num は max_results*2（tests が要求）
- 一方で、VERITAS OS を探していると判定できる場合のみ、
  誤同定防止（アンカー＋ブラックリスト）を強制する
- VERITAS文脈 or AGI文脈では、フィルタで目減りするため num を多めに取得して良い

戻り値フォーマット:
{
  "ok": bool,
  "results": [{"title": str, "url": str, "snippet": str}, ...],
  "error": Optional[str],
  "meta": {
     "raw_count": int,
     "agi_filter_applied": bool,
     "agi_result_count": int | None,
     "boosted_query": str | None,
     "final_query": str,                 # ★必ず入る（Serperに投げた最終クエリ）
     "anchor_applied": bool,             # ★VERITAS文脈のみ True になり得る
     "blacklist_applied": bool,          # ★VERITAS文脈のみ True になり得る
     "blocked_count": int,               # 結果側フィルタで弾いた数（VERITAS文脈のみ）
  }
}

env:
  VERITAS_WEBSEARCH_URL : endpoint
  VERITAS_WEBSEARCH_KEY : API key (X-API-KEY)
"""

from __future__ import annotations

import logging
import os
import random
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

WEBSEARCH_URL: str = os.getenv("VERITAS_WEBSEARCH_URL", "").strip()
WEBSEARCH_KEY: str = os.getenv("VERITAS_WEBSEARCH_KEY", "").strip()
WEBSEARCH_MAX_RETRIES = int(os.getenv("VERITAS_WEBSEARCH_MAX_RETRIES", "3"))
WEBSEARCH_RETRY_DELAY = float(os.getenv("VERITAS_WEBSEARCH_RETRY_DELAY", "1.0"))
WEBSEARCH_RETRY_MAX_DELAY = float(
    os.getenv("VERITAS_WEBSEARCH_RETRY_MAX_DELAY", "8.0")
)
WEBSEARCH_RETRY_JITTER = float(os.getenv("VERITAS_WEBSEARCH_RETRY_JITTER", "0.1"))

logger = logging.getLogger(__name__)

# -------------------------------
# AGI 系クエリ用キーワード/サイト
# -------------------------------
AGI_KEYWORDS: List[str] = [
    "agi",
    "artificial general intelligence",
    "人工汎用知能",
    "人工一般知能",
]

AGI_SITES: List[str] = [
    "arxiv.org",
    "openreview.net",
    "deepmind.com",
    "openai.com",
    "alignmentforum.org",
    "lesswrong.com",
]

# -------------------------------
# Web誤同定防止（VERITAS文脈のみ適用）
# -------------------------------
ANCHOR_CLAUSE: str = '("VERITAS OS" AND (TrustLog OR FUJI OR ValueCore))'

# ドメイン誤同定（別Veritas）: Bureau Veritas 等
BLACKLIST_SITES: List[str] = [
    "veritas.com",
    "www.veritas.com",
    "bureauveritas.com",
    "www.bureauveritas.com",
]

# キーワードでも弾く（タイトル/スニペット/URL）
BLACKLIST_KEYWORDS: List[str] = [
    "bureau veritas",
    "bureauveritas",
    "veritas.com",
]

# URL判定用（bureauveritas.* を広く弾く）
RE_BUREAUVERITAS = re.compile(r"(^|\.)bureauveritas\.[a-z]{2,}$", re.IGNORECASE)


def _normalize_str(x: Any, *, limit: int = 4000) -> str:
    try:
        s = "" if x is None else str(x)
    except Exception:
        s = repr(x)
    if limit and len(s) > int(limit):
        return s[: int(limit)]
    return s


def _compute_backoff(attempt: int) -> float:
    """指数バックオフの待機時間を算出する（ジッター込み）。"""
    base_delay = max(WEBSEARCH_RETRY_DELAY, 0.0)
    max_delay = max(WEBSEARCH_RETRY_MAX_DELAY, base_delay)
    jitter = max(WEBSEARCH_RETRY_JITTER, 0.0)
    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
    if jitter:
        delay += random.uniform(0, delay * jitter)
    return delay


def _should_retry_status(status_code: int) -> bool:
    """再試行対象のHTTPステータスかどうかを判定する。"""
    return status_code == 429 or status_code >= 500


def _post_with_retry(
    url: str,
    headers: Dict[str, Any],
    payload: Dict[str, Any],
    timeout: int,
) -> requests.Response:
    """外部API呼び出しを再試行しつつ実行する。"""
    last_exc: Optional[Exception] = None
    for attempt in range(1, WEBSEARCH_MAX_RETRIES + 1):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            status_code = getattr(response, "status_code", None)
            if status_code is not None and _should_retry_status(status_code):
                if attempt < WEBSEARCH_MAX_RETRIES:
                    delay = _compute_backoff(attempt)
                    logger.warning(
                        "WEBSEARCH retryable status=%s attempt=%s, sleep=%.2fs",
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
            if attempt < WEBSEARCH_MAX_RETRIES:
                delay = _compute_backoff(attempt)
                logger.warning(
                    "WEBSEARCH request error attempt=%s, sleep=%.2fs: %r",
                    attempt,
                    delay,
                    exc,
                )
                time.sleep(delay)
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("WEBSEARCH request failed without exception")


def _extract_hostname(url: str) -> str:
    """URLからホスト名を抽出する（スキームなしURLも対応）。"""
    if not url:
        return ""
    candidate = url.strip()
    parsed = urlparse(candidate)
    host = parsed.hostname
    if not host and "://" not in candidate:
        parsed = urlparse(f"http://{candidate}")
        host = parsed.hostname
    return (host or "").lower()


def _is_agi_query(q: str) -> bool:
    """クエリが AGI 関連っぽいかどうかをざっくり判定"""
    q = q or ""
    q_low = q.lower()
    if "agi" in q_low:
        return True
    if "人工汎用知能" in q or "人工一般知能" in q:
        return True
    if "artificial general intelligence" in q_low:
        return True
    return False


def _looks_agi_result(title: str, snippet: str, url: str) -> bool:
    """検索結果が AGI / その周辺の話っぽいかを判定"""
    text = f"{title} {snippet}".lower()
    url_low = (url or "").lower()

    if any(site in url_low for site in AGI_SITES):
        return True

    for kw in AGI_KEYWORDS:
        if kw.lower() in text:
            return True

    return False


def _should_enforce_veritas_anchor(query: str) -> bool:
    """
    「VERITAS OS を探している」文脈だけ、誤同定防止を強制する。
    重要: 通常クエリは改変しない（tests 要件）
    """
    q = (query or "").strip()
    if not q:
        return False

    ql = q.lower()

    # 「Bureau Veritas」を探したい場合は、誤同定防止をかけない（ユーザー意図を尊重）
    if "bureau veritas" in ql or "bureauveritas" in ql:
        return False

    # VERITAS OS 文脈キーワード（ここに引っかかった時だけアンカー＆ブラックリスト）
    veritas_signals = (
        "veritas os",
        "trustlog",
        "fuji",
        "valuecore",
        "veritas_os",
        "veritas-os",
    )
    return any(sig in ql for sig in veritas_signals)


def _apply_anchor_and_blacklist(query: str) -> Dict[str, Any]:
    """
    VERITAS文脈のみ使用:
    - アンカー付与
    - ブラックリスト除外句を付与
    """
    q = _normalize_str(query, limit=2000).strip()
    q_low = q.lower()

    # (A) アンカー付与（重複は避ける）
    anchor_applied = False
    needs_anchor_bundle = not (
        ("veritas os" in q_low)
        and (("trustlog" in q_low) or ("fuji" in q_low) or ("valuecore" in q_low))
    )
    if needs_anchor_bundle and (ANCHOR_CLAUSE.lower() not in q_low):
        q = f"{q} {ANCHOR_CLAUSE}".strip()
        anchor_applied = True

    # (B) ブラックリスト除外句（-site / -keyword）
    blacklist_applied = False

    site_excludes: List[str] = []
    for s in BLACKLIST_SITES:
        token = f"-site:{s}"
        if token.lower() not in q.lower():
            site_excludes.append(token)

    kw_excludes: List[str] = []
    for kw in BLACKLIST_KEYWORDS:
        token = f'-"{kw}"'
        if token.lower() not in q.lower():
            kw_excludes.append(token)

    if site_excludes or kw_excludes:
        blacklist_applied = True
        q = " ".join([q] + site_excludes + kw_excludes).strip()

    return {
        "final_query": q,
        "anchor_applied": anchor_applied,
        "blacklist_applied": blacklist_applied,
    }


def _is_blocked_result(title: str, snippet: str, url: str) -> bool:
    """
    結果側でも二重防衛（漏れても弾く）
    ※これは VERITAS文脈の時だけ使う想定（通常検索を勝手に削らないため）
    """
    t = (title or "").lower()
    s = (snippet or "").lower()
    u = (url or "").lower()
    host = _extract_hostname(u).replace("www.", "")

    for kw in BLACKLIST_KEYWORDS:
        kwl = kw.lower()
        if kwl in t or kwl in s:
            return True

    for site in BLACKLIST_SITES:
        site_host = _extract_hostname(site).replace("www.", "")
        if host and site_host:
            if host == site_host or host.endswith(f".{site_host}"):
                return True

    # bureauveritas.* wildcard block（ドメイン抽出が雑でも防ぐ）
    if host:
        if RE_BUREAUVERITAS.search(host) or "bureauveritas" in host:
            return True

    # veritas.com domain block（ホスト名を優先的にチェック）
    if host:
        if host == "veritas.com" or host.endswith(".veritas.com"):
            return True

    return False


def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Serper.dev を使った Web 検索アダプタ。

    - 通常: query は一切改変しない（tests互換）
    - VERITAS文脈: 誤同定防止（アンカー & ブラックリスト）を強制
    - AGI文脈: ブースト + 結果のAGIっぽさフィルタを適用（任意）
    """
    raw_query = _normalize_str(query, limit=2000).strip()

    if not WEBSEARCH_URL or not WEBSEARCH_KEY:
        return {
            "ok": False,
            "results": [],
            "error": "WEBSEARCH_API not configured (set VERITAS_WEBSEARCH_URL / KEY)",
            "meta": {
                "raw_count": 0,
                "agi_filter_applied": False,
                "agi_result_count": None,
                "boosted_query": None,
                "final_query": raw_query,
                "anchor_applied": False,
                "blacklist_applied": False,
                "blocked_count": 0,
            },
        }

    # max_results の下限を守る（極端値対策）
    try:
        mr = int(max_results)
    except Exception:
        mr = 5
    if mr < 1:
        mr = 1

    try:
        headers = {
            "X-API-KEY": WEBSEARCH_KEY,
            "Content-Type": "application/json",
        }

        # ----------------------------
        # 0) VERITAS文脈のみ 矯正（通常は改変禁止）
        # ----------------------------
        anchor_applied = False
        blacklist_applied = False

        q_to_send = raw_query
        enforce = _should_enforce_veritas_anchor(raw_query)
        if enforce:
            enforced = _apply_anchor_and_blacklist(raw_query)
            q_to_send = enforced["final_query"]
            anchor_applied = bool(enforced["anchor_applied"])
            blacklist_applied = bool(enforced["blacklist_applied"])

        # ----------------------------
        # 1) AGI 文脈ならブースト（q_to_send の末尾に足す）
        # ----------------------------
        agi_query = _is_agi_query(raw_query)
        boosted_query: Optional[str] = None
        if agi_query:
            boosted_query = (
                f"{q_to_send} "
                '"artificial general intelligence" AGI '
                "(site:arxiv.org OR site:openreview.net OR site:alignmentforum.org OR site:lesswrong.com)"
            ).strip()
            q_to_send = boosted_query

        # ----------------------------
        # 2) 取得件数 num（テスト互換のため通常は *2 固定）
        #    - 通常: num = mr*2（testsが要求）
        #    - VERITAS/AGI: フィルタで目減りするため mr*3 まで許容
        # ----------------------------
        num_to_fetch = int(mr * 2)
        if enforce or agi_query:
            num_to_fetch = int(mr * 3)

        payload: Dict[str, Any] = {
            "q": q_to_send,
            "num": num_to_fetch,
        }

        resp = _post_with_retry(
            WEBSEARCH_URL,
            headers=headers,
            payload=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data: Dict[str, Any] = resp.json()

        organic = data.get("organic") or []
        raw_items: List[Dict[str, Any]] = []
        for item in organic:
            url = item.get("link") or item.get("url") or ""
            title = item.get("title") or ""
            snippet = item.get("snippet") or item.get("description") or ""
            raw_items.append({"title": title, "url": url, "snippet": snippet})

        # ----------------------------
        # 3) VERITAS文脈の時だけ、結果側ブラックリスト（二重防衛）
        # ----------------------------
        blocked_count = 0
        filtered_items: List[Dict[str, Any]] = []
        if enforce:
            for it in raw_items:
                if _is_blocked_result(
                    it.get("title") or "",
                    it.get("snippet") or "",
                    it.get("url") or "",
                ):
                    blocked_count += 1
                    continue
                filtered_items.append(it)
        else:
            filtered_items = raw_items

        # ----------------------------
        # 4) AGI文脈なら AGIっぽさフィルタ
        # ----------------------------
        if agi_query:
            agi_items: List[Dict[str, Any]] = []
            for it in filtered_items:
                if _looks_agi_result(
                    it.get("title") or "",
                    it.get("snippet") or "",
                    it.get("url") or "",
                ):
                    agi_items.append(it)

            if not agi_items:
                return {
                    "ok": True,
                    "results": [],
                    "error": "no_agi_like_results",
                    "meta": {
                        "raw_count": len(raw_items),
                        "agi_filter_applied": True,
                        "agi_result_count": 0,
                        "boosted_query": boosted_query,
                        "final_query": q_to_send,  # ★Serperに投げた最終
                        "anchor_applied": anchor_applied,
                        "blacklist_applied": blacklist_applied,
                        "blocked_count": blocked_count,
                    },
                }

            return {
                "ok": True,
                "results": agi_items[:mr],
                "error": None,
                "meta": {
                    "raw_count": len(raw_items),
                    "agi_filter_applied": True,
                    "agi_result_count": len(agi_items),
                    "boosted_query": boosted_query,
                    "final_query": q_to_send,  # ★Serperに投げた最終
                    "anchor_applied": anchor_applied,
                    "blacklist_applied": blacklist_applied,
                    "blocked_count": blocked_count,
                },
            }

        # ----------------------------
        # 5) 通常
        # ----------------------------
        return {
            "ok": True,
            "results": filtered_items[:mr],
            "error": None,
            "meta": {
                "raw_count": len(raw_items),
                "agi_filter_applied": False,
                "agi_result_count": None,
                "boosted_query": boosted_query,
                "final_query": q_to_send,  # ★Serperに投げた最終（通常は raw_query と一致）
                "anchor_applied": anchor_applied,
                "blacklist_applied": blacklist_applied,
                "blocked_count": blocked_count,
            },
        }

    except Exception as e:
        return {
            "ok": False,
            "results": [],
            "error": f"WEBSEARCH_API error: {repr(e)}",
            "meta": {
                "raw_count": 0,
                "agi_filter_applied": False,
                "agi_result_count": None,
                "boosted_query": None,
                "final_query": raw_query,
                "anchor_applied": False,
                "blacklist_applied": False,
                "blocked_count": 0,
            },
        }

