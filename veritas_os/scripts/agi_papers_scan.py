# veritas_os/scripts/agi_papers_scan.py
# -*- coding: utf-8 -*-

"""
AGI 論文スキャン & 要約スクリプト（VERITAS用）

1) Serper(web_search) で AGI 関連論文を検索
2) 結果を LLM に投げて、日本語でサマリを作成
3) world_state.json の external_knowledge.agi_research に保存
"""

from __future__ import annotations

import textwrap
import sys
import time
from typing import List, Dict

from veritas_os.tools import call_tool
from veritas_os.core import llm_client, world


def run(user_query: str = "AGI definition and LLM") -> None:
    """
    AGI 関連の論文を検索してサマリを表示 & world_state に保存するメイン処理
    """

    # 1) Serper で検索
    res = call_tool("web_search", query=user_query, max_results=5)

    if not res.get("ok"):
        print("web_search failed:", res.get("error"))
        return

    items: List[Dict] = res.get("results", []) or []

    print("=== 検索クエリ ===")
    print(user_query)
    print("\n=== 検索結果（ダイジェスト）===\n")

    blocks: List[str] = []
    for i, it in enumerate(items, start=1):
        title = it.get("title") or ""
        snippet = it.get("snippet") or ""
        url = it.get("url") or ""

        block = (
            f"[{i}] {title}\n"
            f"{snippet}\n"
            f"URL: {url}\n"
        )
        print(block)
        blocks.append(block)

    if not blocks:
        print("検索結果が 0 件でした。クエリを変えて再実行してください。")
        return

    # 2) LLM に要約してもらう
    print("\n=== LLM へ要約依頼中... ===\n")

    system_prompt = (
        "あなたはAGI研究のリサーチアシスタントです。"
        "与えられた検索結果から、重要な論点とVERITASのAGI化に役立つ示唆を日本語で整理してください。"
    )

    user_prompt = (
        "以下はAGIに関する論文候補の検索結果です。\n\n"
        + "\n".join(blocks)
        + "\n\n次を日本語で要約してください：\n"
          "1) 全体の共通テーマ\n"
          "2) 各論文の主張・ポイント\n"
          "3) VERITASのAGI化に役立つ示唆\n"
    )

    llm_out = llm_client.chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.3,
        max_tokens=900,
    )

    summary_text: str = llm_out.get("text", "")

    print("=== AGI 論文サマリ ===\n")
    print(textwrap.dedent(summary_text))

    # 3) world_state.json の external_knowledge.agi_research_events に保存
    state = world.get_state()

    # external_knowledge が壊れていても復元できるように型チェック
    ext = state.get("external_knowledge")
    if not isinstance(ext, dict):
        ext = {}
        state["external_knowledge"] = ext

    # ★ ここから agi_research_events に変更
    agi_list = ext.get("agi_research_events")

    if isinstance(agi_list, dict):
        agi_list = [agi_list]
    elif not isinstance(agi_list, list):
        agi_list = []

    ext["agi_research_events"] = agi_list
    # ★ ここまで

    event = {
        "kind": "agi_research",
        "ts": time.time(),
        "query": user_query,
        "papers": [
            {
                "title": it.get("title") or "",
                "url": it.get("url") or "",
                "snippet": it.get("snippet") or "",
            }
            for it in items
        ],
        "summary": summary_text,
    }

    agi_list.append(event)

    # 履歴が長くなりすぎないように最新 200 件だけ残す
    if len(agi_list) > 200:
        ext["agi_research_events"] = agi_list[-200:]

    # external_knowledge だけをマージ更新
    world.set_state({"external_knowledge": ext})
    print("\n[agi_papers_scan] world_state.external_knowledge.agi_research_events に保存しました。")


def main() -> None:
    """
    コマンドライン引数があればそれをクエリに使う。
    例: python -m veritas_os.scripts.agi_papers_scan \"AGI definition\"
    """
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = "AGI definition and LLM"

    run(query)


if __name__ == "__main__":
    main()
