#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
from typing import Any, Dict, List

from veritas_os.core import memory


def _flatten_hits(hits_raw: Any) -> List[Dict[str, Any]]:
    """
    memory.search の戻り値が list or dict どちらでも扱えるように、
    フラットな list[dict] に正規化するヘルパー。
    """
    out: List[Dict[str, Any]] = []

    if isinstance(hits_raw, dict):
        # {kind: [hits...]} 形式
        for kind, hits in hits_raw.items():
            if not isinstance(hits, list):
                continue
            for h in hits:
                if not isinstance(h, dict):
                    continue
                d = dict(h)
                d.setdefault("kind", kind)
                out.append(d)

    elif isinstance(hits_raw, list):
        # すでに list[dict] 形式
        for h in hits_raw:
            if isinstance(h, dict):
                out.append(dict(h))

    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search VERITAS MemoryOS from CLI"
    )
    parser.add_argument("query", help="検索クエリ")
    parser.add_argument("--user-id", default="fujishita")
    parser.add_argument("-k", "--top-k", type=int, default=5)
    parser.add_argument(
        "--kinds",
        nargs="*",
        default=["doc"],
        help="検索対象 kinds (デフォルト: doc)",
    )

    args = parser.parse_args()

    hits_raw = memory.search(
        query=args.query,
        k=args.top_k,
        kinds=args.kinds,
        user_id=args.user_id,
    )

    hits = _flatten_hits(hits_raw)

    print(f"Query: {args.query}")
    print(f"Hits: {len(hits)}")

    for i, h in enumerate(hits, start=1):
        score = h.get("score")
        kind = h.get("kind", "?")
        print("----")
        try:
            if score is None:
                raise ValueError
            s = float(score)
            print(f"#{i} score={s:.3f} kind={kind}")
        except Exception:
            print(f"#{i} kind={kind}")

        tags = h.get("tags")
        if tags:
            print("tags:", tags)

        # text の取り出し（text or value.text）
        text = (
            h.get("text")
            or (h.get("value") or {}).get("text")
            or ""
        )
        text = str(text).replace("\n", " ")
        if len(text) > 200:
            text = text[:197] + "..."
        print(text)


if __name__ == "__main__":
    main()

