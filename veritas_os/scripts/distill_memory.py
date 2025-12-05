#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
VERITAS Memory Distill CLI

エピソードメモリ（episodic）を要約して、
セマンティックメモリ（semantic）として保存するためのワンショット CLI。
"""

from __future__ import annotations

import argparse
import os
import sys

from veritas_os.core import memory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VERITAS Memory Distill CLI (episodic → semantic summary)"
    )
    parser.add_argument(
        "--user",
        "--user_id",
        dest="user_id",
        type=str,
        required=False,
        help="対象ユーザーID（未指定なら VERITAS_USER_ID or 'cli'）",
    )
    parser.add_argument(
        "--max_items",
        type=int,
        default=200,
        help="蒸留対象とする最大エピソード数（新しい順）",
    )
    parser.add_argument(
        "--min_len",
        type=int,
        default=20,
        help="対象とするエピソード本文の最小文字数（短すぎるログを除外）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="セマンティックメモリへ保存せず、生成テキストだけ表示する",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="詳細ログを表示する",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    user_id = args.user_id or os.getenv("VERITAS_USER_ID") or "cli"

    if args.verbose:
        print(
            f"[MemoryDistill] user_id={user_id}, "
            f"max_items={args.max_items}, min_len={args.min_len}, "
            f"dry_run={args.dry_run}"
        )

    # distill_memory_for_user の仕様：
    # - doc: {"text": ..., "tags": [...], "meta": {...}} 相当を返す想定
    # - dry_run=True のときは保存せずに dict だけ返す実装にするなら、
    #   memory.py 側のシグネチャに dry_run を足してもよい
    try:
        # もし distill_memory_for_user に dry_run を追加した場合は渡す：
        # doc = memory.distill_memory_for_user(
        #     user_id=user_id,
        #     max_items=args.max_items,
        #     min_text_len=args.min_len,
        #     dry_run=args.dry_run,
        # )
        doc = memory.distill_memory_for_user(
            user_id=user_id,
            max_items=args.max_items,
            min_text_len=args.min_len,
        )
    except Exception as e:
        print(f"[MemoryDistill] ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if not doc:
        print("[MemoryDistill] nothing saved / generated.")
        return

    # 表示用
    text = doc.get("text") if isinstance(doc, dict) else str(doc)

    print("\n[MemoryDistill] Saved semantic note (preview):")
    print("------------------------------------------------")
    print(text)
    print("------------------------------------------------")

    # 将来的に doc["meta"]["memory_id"] などを返す仕様にしたら、
    # ここで ID も表示できるようにしておくと便利
    meta = doc.get("meta") if isinstance(doc, dict) else None
    if isinstance(meta, dict):
        mem_id = meta.get("id") or meta.get("memory_id")
        if mem_id:
            print(f"[MemoryDistill] semantic memory id: {mem_id}")


if __name__ == "__main__":
    main()
