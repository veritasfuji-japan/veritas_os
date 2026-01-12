# veritas_os/tools/web_search.py
"""
VERITAS OS 用 Web検索アダプタ（Serper.dev 経由）

重要要件（誤同定防止 / 最重要）:
- 常にクエリへアンカーを強制付与:
    ("VERITAS OS" AND (TrustLog OR FUJI OR ValueCore))
- veritas.com / bureauveritas.* を除外（-site / -keyword の両方）
- 呼び出し側が何を渡しても、このアダプタ内で強制する
- evidence に残す query も「アンカー後の確定クエリ」を使えるよう meta.final_query を返す

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
     "anchor_applied": bool,
     "blacklist_applied": bool,
     "blocked_count": int,               # ドメイン/キーワードで弾いた数（結果側フィルタ）
  }
}

env:
  VERITAS_WEBSEARCH_URL : Serper.dev endpoint
  VERITAS_WEBSEARCH_KEY : Serper.dev API key (X-API-KEY)
"""

import os
import re
from typing import Any, Dict, List, Optional

import requests

WEBSEARCH_URL: str = os.getenv("VERITAS_WEBSEARCH_URL", "").strip()
WEBSEARCH_KEY: str = os.getenv("VERITAS_WEBSEARCH_KEY", "").strip()

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
# Web誤同定防止（最重要）
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


def _is_agi_query(q: str) -> bool:
    """クエリが AGI 関連っぽいかどうかをざっくり判定"""
    q_low = (q or "").lower()
    if "agi" in q_low:
        return True
    if "人工汎用知能" in q_low or "人工一般知能" in q_low:
        return True
    if "agi research" in q_low:
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


def _normalize_str(x: Any, *, limit: int = 4000) -> str:
    try:
        s = "" if x is None else str(x)
    except Exception:
        s = repr(x)
    if limit and len(s) > int(limit):
        return s[: int(limit)]
    return s


def _apply_anchor_and_blacklist(query: str) -> Dict[str, Any]:
    """
    ★最重要：クエリを強制アンカーし、ブラックリスト除外句も付与する
    - 呼び出し側が何を投げてもここで矯正する
    """
    q = _normalize_str(query, limit=2000).strip()

    # (A) アンカーを必ず付与
    # 既に入っていても重複は避ける（雑に contains で判定）
    anchor_applied = False
    if "VERITAS OS" not in q and "veritas os" not in q.lower():
        q = f"{q} {ANCHOR_CLAUSE}".strip()
        anchor_applied = True
    else:
        # "VERITAS OS" が含まれていても TrustLog/FUJI/ValueCore の束が無いなら付与
        q_low = q.lower()
        if not (("trustlog" in q_low) or ("fuji" in q_low) or ("valuecore" in q_low)):
            q = f"{q} {ANCHOR_CLAUSE}".strip()
            anchor_applied = True

    # (B) ブラックリスト除外句（-site / -keyword）を必ず付与
    blacklist_applied = False
    # -site: ドメイン除外（SerperはGoogle互換クエリ寄り）
    # -keyword: 文字列除外（保険）
    site_excludes = []
    for s in BLACKLIST_SITES:
        if f"-site:{s}" not in q:
            site_excludes.append(f"-site:{s}")
    kw_excludes = []
    for kw in BLACKLIST_KEYWORDS:
        # 文字列除外はクオートしておく
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
    結果側でも二重防衛（ブラックリストが漏れても弾く）
    """
    t = (title or "").lower()
    s = (snippet or "").lower()
    u = (url or "").lower()

    # keyword block
    for kw in BLACKLIST_KEYWORDS:
        if kw.lower() in t or kw.lower() in s or kw.lower() in u:
            return True

    # domain block
    for site in BLACKLIST_SITES:
        if site.lower() in u:
            return True

    # bureauveritas.* wildcard block（ドメイン抽出が雑でも防ぐ）
    # URL内に bureauveritas.xx が含まれるかを広めに判定
    if "bureauveritas." in u:
        # 末尾ドメインっぽい箇所にマッチするか
        # 例: https://www.bureauveritas.jp/...
        #     bureauveritas.co.jp
        host_guess = u.split("/")[2] if "://" in u and len(u.split("/")) > 2 else u
        host_guess = host_guess.split(":")[0]
        if RE_BUREAUVERITAS.search(host_guess.replace("www.", "")) or "bureauveritas" in host_guess:
            return True

    # veritas.com also blocked (別Veritasの可能性)
    if "veritas.com" in u:
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

    ★最重要: その前に必ず
      - アンカー強制
      - ブラックリスト除外強制
    """
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
                "final_query": _normalize_str(query, limit=2000),
                "anchor_applied": False,
                "blacklist_applied": False,
                "blocked_count": 0,
            },
        }

    try:
        headers = {
            "X-API-KEY": WEBSEARCH_KEY,
            "Content-Type": "application/json",
        }

        # ---- 0) アンカー & ブラックリスト強制 ----
        enforced = _apply_anchor_and_blacklist(query or "")
        final_query = enforced["final_query"]

        agi_query = _is_agi_query(final_query)

        # ---- 1) AGIクエリならブースト（ただしアンカー/除外は維持）----
        boosted_query: Optional[str] = None
        q_to_send = final_query

        if agi_query:
            boosted_query = (
                f"{final_query} "
                '"artificial general intelligence" AGI '
                "site:arxiv.org OR site:openreview.net "
                "OR site:alignmentforum.org OR site:lesswrong.com"
            )
            q_to_send = boosted_query

        payload: Dict[str, Any] = {
            "q": q_to_send,
            "num": int(max_results * 3),  # 余裕をもって多めに取る（ブロック/フィルタで減るため）
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
            raw_items.append({"title": title, "url": url, "snippet": snippet})

        # ---- 2) ブラックリスト結果を結果側で排除（二重防衛）----
        filtered_items: List[Dict[str, Any]] = []
        blocked_count = 0
        for it in raw_items:
            if _is_blocked_result(it.get("title") or "", it.get("snippet") or "", it.get("url") or ""):
                blocked_count += 1
                continue
            filtered_items.append(it)

        # ---- 3) AGIクエリなら AGIっぽさフィルタも適用 ----
        if agi_query:
            agi_items: List[Dict[str, Any]] = []
            for it in filtered_items:
                if _looks_agi_result(it.get("title") or "", it.get("snippet") or "", it.get("url") or ""):
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
                        "final_query": q_to_send,  # ★ Serperに投げた最終（アンカー後）
                        "anchor_applied": enforced["anchor_applied"],
                        "blacklist_applied": enforced["blacklist_applied"],
                        "blocked_count": blocked_count,
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
                    "final_query": q_to_send,  # ★ Serperに投げた最終（アンカー後）
                    "anchor_applied": enforced["anchor_applied"],
                    "blacklist_applied": enforced["blacklist_applied"],
                    "blocked_count": blocked_count,
                },
            }

        # ---- 通常クエリ ----
        final_items = filtered_items[: max_results]
        return {
            "ok": True,
            "results": final_items,
            "error": None,
            "meta": {
                "raw_count": len(raw_items),
                "agi_filter_applied": False,
                "agi_result_count": None,
                "boosted_query": boosted_query,
                "final_query": q_to_send,  # ★ Serperに投げた最終（アンカー後）
                "anchor_applied": enforced["anchor_applied"],
                "blacklist_applied": enforced["blacklist_applied"],
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
                "final_query": _normalize_str(query, limit=2000),
                "anchor_applied": False,
                "blacklist_applied": False,
                "blocked_count": 0,
            },
        }




