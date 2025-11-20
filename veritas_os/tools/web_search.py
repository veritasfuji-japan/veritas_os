# veritas_os/tools/web_search.py
import os
import requests
from typing import Any, Dict, List

WEBSEARCH_URL = os.getenv("VERITAS_WEBSEARCH_URL", "").strip()
WEBSEARCH_KEY = os.getenv("VERITAS_WEBSEARCH_KEY", "").strip()


def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Serper.dev を使ったシンプルな Web 検索アダプタ
    """
    if not WEBSEARCH_URL or not WEBSEARCH_KEY:
        return {
            "ok": False,
            "results": [],
            "error": "WEBSEARCH_API not configured (set VERITAS_WEBSEARCH_URL / KEY)",
        }

    try:
        headers = {
            # ★ Serper は Authorization ではなく X-API-KEY で受け取る
            "X-API-KEY": WEBSEARCH_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "q": query,
            "num": int(max_results),
        }

        resp = requests.post(WEBSEARCH_URL, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        items: List[Dict[str, Any]] = []
        for item in (data.get("organic") or [])[: max_results]:
            items.append(
                {
                    "title": item.get("title"),
                    "url": item.get("link") or item.get("url"),
                    "snippet": item.get("snippet") or item.get("description"),
                }
            )

        return {
            "ok": True,
            "results": items,
            "error": None,
            "meta": {"raw_count": len(items)},
        }

    except Exception as e:
        return {
            "ok": False,
            "results": [],
            "error": f"WEBSEARCH_API error: {repr(e)}",
        }
