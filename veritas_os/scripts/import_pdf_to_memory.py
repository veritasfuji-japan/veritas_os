#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List

import pdfplumber

from veritas_os.core import memory  # いつものやつ

# =============== (cid:xx) ゴミ判定 ===============

CID_PATTERN = re.compile(r"\(cid:\d+\)")

def is_cid_garbage_chunk(text: str) -> bool:
    """
    (cid:xx) が支配的で、まともなテキストがほぼ無いチャンクを True にする。
    ヒューリスティックなので、必要に応じてしきい値は調整してOK。
    """
    if not text or not text.strip():
        # 完全な空白は捨てる
        return True

    cid_matches = CID_PATTERN.findall(text)
    cid_count = len(cid_matches)

    if cid_count == 0:
        # cid が無ければ普通のチャンクとして扱う
        return False

    # (cid:xx) を全部消した後の「生き残りテキスト」の長さを見る
    cleaned = CID_PATTERN.sub("", text)
    cleaned_len = len(cleaned.strip())

    # 条件:
    #   - (cid:xx) が 5 個以上
    #   - かつ、cid を除いたテキストが 50 文字未満
    # → ほぼゴミとみなしてスキップ
    if cid_count >= 5 and cleaned_len < 50:
        return True

    return False


# =============== チャンク関数 ===============

def chunk_text(text: str, max_chars: int = 800, overlap: int = 200) -> List[str]:
    """
    長すぎるテキストを max_chars くらいで分割（少しオーバーラップ付き）
    """
    text = " ".join(text.split())
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        chunks.append(text[start:end])
        if end == n:
            break
        start = max(0, end - overlap)
    return chunks


# =============== PDF → MemoryOS ===============

def import_pdf(
    pdf_path: Path,
    user_id: str,
    kind: str = "doc",
    source_label: str | None = None,
    max_chars: int = 800,
) -> int:
    """
    PDFを読み込んで MemoryOS に投入する。
    戻り値: 追加したメモリ件数
    """
    if source_label is None:
        source_label = pdf_path.name

    total = 0
    skipped_cid = 0

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages, 1):
            raw = page.extract_text() or ""
            raw = raw.strip()
            if not raw:
                continue

            chunks = chunk_text(raw, max_chars=max_chars, overlap=200)
            for i, chunk in enumerate(chunks, 1):
                # ---- (cid:xx) ゴミフィルタ ----
                if is_cid_garbage_chunk(chunk):
                    skipped_cid += 1
                    print(
                        f"[import_pdf] skip page={page_idx} "
                        f"chunk={i} as cid-garbage"
                    )
                    continue
                # ------------------------------

                memory.add(
                    user_id=user_id,
                    kind=kind,
                    text=chunk,
                    meta={
                        "source": source_label,
                        "page": page_idx,
                        "chunk_index": i,
                        "page_chunk_id": f"{page_idx}-{i}",
                        "content_type": "pdf",
                    },
                )
                total += 1

    print(f"[import_pdf] skipped {skipped_cid} cid-garbage chunks")
    return total


# =============== CLI エントリポイント ===============

def main():
    parser = argparse.ArgumentParser(
        description="Import PDF into VERITAS MemoryOS"
    )
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("--user-id", default="fujishita")
    parser.add_argument("--kind", default="doc")
    parser.add_argument("--source-label", default=None)
    parser.add_argument("--max-chars", type=int, default=800)
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="Import後に vector index を再構築する場合に指定",
    )

    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    total = import_pdf(
        pdf_path=pdf_path,
        user_id=args.user_id,
        kind=args.kind,
        source_label=args.source_label,
        max_chars=args.max_chars,
    )

    print(f"✅ Imported {total} chunks from {pdf_path}")

    if args.rebuild_index:
        print("🔁 Rebuilding vector index...")
        memory.rebuild_vector_index()
        print("✅ Vector index rebuilt.")


if __name__ == "__main__":
    main()


