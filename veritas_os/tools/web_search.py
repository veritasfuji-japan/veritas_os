# veritas_os/tools/web_search.py
"""
VERITAS OS 用 Web検索アダプタ（Serper.dev 経由）

- 通常クエリ: そのまま Serper に投げて結果を返す
- AGI 系クエリ:
    - クエリを AGI / 論文サイト寄りにブースト
    - 返ってきた結果のうち、AGI っぽいものだけをフィルタ
    - 1件も残らない場合は「0件」として返す（error = "no_agi_like_results"）

戻り値のフォーマット:

    {
        "ok": bool,                 # True/False
        "results": [
            {"title": str, "url": str, "snippet": str},
            ...
        ],
        "error": Optional[str],     # 失敗時 or 特殊条件時のエラー種別
        "meta": {                   # 補助情報（あれば）
            "raw_count": int,           # 元の結果件数
            "agi_filter_applied": bool, # AGI フィルタを適用したか
            "agi_result_count": int,    # フィルタ後の件数
            "boosted_query": str | None # AGI クエリ時のブースト後クエリ
        }
    }

※ env:
    VERITAS_WEBSEARCH_URL : Serper.dev のエンドポイント URL
    VERITAS_WEBSEARCH_KEY : Serper.dev の API キー（X-API-KEY）
"""

import os
from typing import Any, Dict, List

import requests

WEBSEARCH_URL: str = os.getenv("VERITAS_WEBSEARCH_URL", "").strip()
WEBSEARCH_KEY: str = os.getenv("VERITAS_WEBSEARCH_KEY", "").strip()

# ---------------------------------
# AGI 系クエリ用キーワード/サイト
# ---------------------------------
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


def _is_agi_query(q: str) -> bool:
    """クエリが AGI 関連っぽいかどうかをざっくり判定"""
    q_low = (q or "").lower()
    if "agi" in q_low:
        return True
    if "人工汎用知能" in q_low or "人工一般知能" in q_low:
        return True
    # 「AGI research」など
    if "agi research" in q_low:
        return True
    return False


def _looks_agi_result(title: str, snippet: str, url: str) -> bool:
    """検索結果が AGI / その周辺の話っぽいかを判定"""
    text = f"{title} {snippet}".lower()
    url_low = (url or "").lower()

    # URL が AGI 周辺サイトならその時点でかなり信用
    if any(site in url_low for site in AGI_SITES):
        return True

    # タイトル・スニペット内に AGI キーワードが入っているか
    for kw in AGI_KEYWORDS:
        if kw.lower() in text:
            return True

    return False


def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Serper.dev を使った Web 検索アダプタ。

    - 通常: そのまま Serper に渡す
    - AGI 系クエリ: 
        1) クエリを論文サイト寄りにブースト
        2) 結果を AGI っぽいものだけにフィルタ
           → 1件も残らない場合は「0件」として返す
    """
    if not WEBSEARCH_URL or not WEBSEARCH_KEY:
        return {
            "ok": False,
            "results": [],
            "error": "WEBSEARCH_API not configured (set VERITAS_WEBSEARCH_URL / KEY)",
        }

    try:
        headers = {
            # ★ Serper は Authorization ではなく X-API-KEY
            "X-API-KEY": WEBSEARCH_KEY,
            "Content-Type": "application/json",
        }

        agi_query = _is_agi_query(query or "")

        # ---- ① クエリブースト ----
        boosted_query = query
        if agi_query:
            # かなり AGI/論文サイトに寄せる（元クエリ + 強制ブースト）
            boosted_query = (
                f"{query} "
                '"artificial general intelligence" AGI '
                "site:arxiv.org OR site:openreview.net "
                "OR site:alignmentforum.org OR site:lesswrong.com"
            )

        payload: Dict[str, Any] = {
            "q": boosted_query,
            "num": int(max_results * 2),  # 余裕をもって多めに取ってくる
        }

        resp = requests.post(WEBSEARCH_URL, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data: Dict[str, Any] = resp.json()

        organic = data.get("organic") or []
        raw_items: List[Dict[str, Any]] = []

        for item in organic:
            url = item.get("link") or item.get("url") or ""
            title = item.get("title") or ""
            snippet = item.get("snippet") or item.get("description") or ""
            raw_items.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                }
            )

        # ---- ② AGI クエリなら結果フィルタを厳しめに適用 ----
        if agi_query:
            agi_items: List[Dict[str, Any]] = []
            for it in raw_items:
                if _looks_agi_result(
                    it.get("title") or "",
                    it.get("snippet") or "",
                    it.get("url") or "",
                ):
                    agi_items.append(it)

            # 1件も AGI ぽい結果がなければ、そのまま「0件」として返す
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
                    },
                }

            final_items = agi_items[: max_results]
            return {
                "ok": True,
                "results": final_items,
                "error": None,
                "meta": {
                    "raw_count": len(raw_items),
                    "agi_filter_applied": True,
                    "agi_result_count": len(agi_items),
                    "boosted_query": boosted_query,
                },
            }

        # ---- 通常クエリ（AGI 以外）はそのまま返す ----
        final_items = raw_items[: max_results]
        return {
            "ok": True,
            "results": final_items,
            "error": None,
            "meta": {
                "raw_count": len(raw_items),
                "agi_filter_applied": False,
                "boosted_query": None,
            },
        }

    except Exception as e:
        return {
            "ok": False,
            "results": [],
            "error": f"WEBSEARCH_API error: {repr(e)}",
        }

