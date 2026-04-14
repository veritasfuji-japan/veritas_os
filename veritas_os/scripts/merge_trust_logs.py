#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERITAS TrustLog Merger - 完全版

複数の TrustLog ファイルをマージして重複を除去し、
created_at でソートしたうえで sha256 / sha256_prev を再計算します。

- request_id をキーに重複排除（同一IDは created_at が新しい方を採用）
- created_at / timestamp がない古いエントリもそのまま取り込み（ソート時は空文字扱い）
- 出力ファイルは JSONL (1 行 = 1 JSON)

Usage (デフォルトパスを使う):
    python merge_trust_logs.py

Usage (出力先を指定):
    python merge_trust_logs.py --out /path/to/trust_log_merged.jsonl
"""

from __future__ import annotations

import argparse
import json
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

# ===== パス設定 =====
# Canonical runtime paths — all outputs go to runtime/<namespace>/
from veritas_os.scripts._runtime_paths import (  # noqa: E402
    LOG_DIR as _CANONICAL_LOG_DIR,
)

# The canonical log directory replaces both old scripts/logs candidates.
PKG_ROOT = Path(__file__).resolve().parents[1]          # .../veritas_os
PKG_SCRIPTS_DIR = PKG_ROOT / "scripts"

# デフォルトで見るログディレクトリ: canonical runtime path
LOG_DIR_CANDIDATES = [_CANONICAL_LOG_DIR]

def _pick_default_logs_dir() -> Path:
    for d in LOG_DIR_CANDIDATES:
        if d.exists():
            return d
    # Create canonical directory if it doesn't exist
    _CANONICAL_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return _CANONICAL_LOG_DIR


DEFAULT_LOGS_DIR = _pick_default_logs_dir()

# デフォルトソースファイル候補
DEFAULT_SRC_FILES = [
    DEFAULT_LOGS_DIR / "trust_log.jsonl",
    DEFAULT_LOGS_DIR / "trust_log.json",
    DEFAULT_LOGS_DIR / "trust_log_backup.jsonl",
    DEFAULT_LOGS_DIR / "trust_log_backup.json",
    PKG_SCRIPTS_DIR / "trust_log_archive.jsonl",
]

DEFAULT_OUT_PATH = DEFAULT_LOGS_DIR / "trust_log_merged.jsonl"


# ===== 基本ユーティリティ =====

def _sha256(s: str) -> str:
    """UTF-8 文字列から SHA-256 ハッシュを計算"""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _normalize_for_hash(entry: Dict[str, Any]) -> str:
    """
    TrustLog の sha256 計算用にエントリを正規化。
    - sha256 / sha256_prev を除外して JSON 化
    - sort_keys=True で順序を固定
    """
    payload = dict(entry)
    payload.pop("sha256", None)
    payload.pop("sha256_prev", None)
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _stable_entry_fingerprint(entry: Dict[str, Any]) -> str:
    """Return a deterministic fingerprint for entries without request_id."""
    return _sha256(_normalize_for_hash(entry))


def load_any_json(path: Path) -> List[Dict[str, Any]]:
    """
    JSON / JSONL / JSON with items[] をいい感じに読み込む。

    優先順:
    1. json.loads(text) に成功した場合:
       - list        → そのまま返す
       - dict+items  → dict["items"] を返す
       - dict 単体   → [dict] として返す
    2. json.loads に失敗した場合:
       - JSONL とみなして 1 行ごとに json.loads
    """
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return []

        # ---- まずは普通に JSON としてパースを試みる ----
        try:
            data = json.loads(text)
            # list の場合
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
            # dict の場合
            if isinstance(data, dict):
                if "items" in data and isinstance(data["items"], list):
                    return [d for d in data["items"] if isinstance(d, dict)]
                # 単一オブジェクトとして扱う
                return [data]
        except json.JSONDecodeError:
            # 通常 JSON でなければ JSONL とみなす
            pass

        # ---- JSONL モード ----
        items: List[Dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    items.append(obj)
            except json.JSONDecodeError as e:
                print(f"⚠️  Skipping invalid JSON line in {path.name}: {e}")
        return items

    except FileNotFoundError:
        print(f"⏭️  File not found: {path}")
        return []
    except Exception as e:
        print(f"❌ Error loading {path}: {e}")
        return []


def recompute_hash_chain(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    created_at順に並んだ TrustLog エントリに対して、
    sha256 / sha256_prev のチェーンを再計算する。

    hₜ = SHA256(hₜ₋₁ || rₜ)
    """
    new_items: List[Dict[str, Any]] = []
    prev_hash: Optional[str] = None

    for item in items:
        # 元を壊さないようにコピー
        e = dict(item)

        # sha フィールドは一旦消してから再度計算
        e.pop("sha256", None)
        e.pop("sha256_prev", None)

        e["sha256_prev"] = prev_hash

        entry_json = _normalize_for_hash(e)
        if prev_hash:
            combined = prev_hash + entry_json
        else:
            combined = entry_json

        e["sha256"] = _sha256(combined)
        prev_hash = e["sha256"]

        new_items.append(e)

    return new_items


# ===== メイン処理 =====

def merge_trust_logs(
    src_files: List[Path],
    out_path: Path,
    recompute_hash: bool = True,
) -> None:
    """TrustLog ファイルをマージして out_path に JSONL で出力。"""
    print("🔄 VERITAS TrustLog Merger")
    print("=" * 60)

    uniq: Dict[str, Dict[str, Any]] = {}
    total_loaded = 0

    for src in src_files:
        if not src.exists():
            print(f"⏭️  Skipping {src} (not found)")
            continue

        items = load_any_json(src)
        total_loaded += len(items)
        print(f"📄 Loaded {len(items)} items from {src}")

        for item in items:
            if not isinstance(item, dict):
                continue

            # created_at の無い古いログには timestamp を流用
            if "created_at" not in item and "timestamp" in item:
                item["created_at"] = item.get("timestamp")

            rid = item.get("request_id")
            if rid:
                # 同じ request_id は created_at が新しい方を優先
                existing = uniq.get(rid)
                if not existing:
                    uniq[rid] = item
                else:
                    if (item.get("created_at") or "") > (existing.get("created_at") or ""):
                        uniq[rid] = item
            else:
                # request_id が無いエントリは created_at/timestamp をキーとして扱う
                ts_key = (
                    item.get("created_at")
                    or item.get("timestamp")
                    or _stable_entry_fingerprint(item)
                )
                existing = uniq.get(ts_key)
                if not existing:
                    uniq[ts_key] = item
                else:
                    # 同じ ts_key の場合は後勝ちにしておく
                    uniq[ts_key] = item

    print(f"\n📊 Total loaded: {total_loaded}")
    print(f"📊 Unique entries (by request_id / timestamp): {len(uniq)}")
    print(f"📊 Duplicates removed: {total_loaded - len(uniq)}")

    # created_at / timestamp でソート
    items = sorted(
        uniq.values(),
        key=lambda x: (x.get("created_at") or x.get("timestamp") or ""),
    )

    # 必要に応じてハッシュチェーンを再計算
    if recompute_hash:
        print("🔐 Recomputing sha256 / sha256_prev chain ...")
        items = recompute_hash_chain(items)

    # 出力先ディレクトリを作成
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # JSONL として書き出し
    with out_path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"\n✅ Merged {len(items)} unique logs → {out_path}")
    print("   Output format: JSONL (one JSON per line)")
    if recompute_hash:
        print("   Note: sha256 / sha256_prev chain has been recomputed.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge VERITAS TrustLog files.")
    parser.add_argument(
        "--out",
        type=str,
        default=str(DEFAULT_OUT_PATH),
        help=f"Output JSONL path (default: {DEFAULT_OUT_PATH})",
    )
    parser.add_argument(
        "--no-rehash",
        action="store_true",
        help="Do NOT recompute sha256 / sha256_prev chain (ただし原則おすすめしません)",
    )
    parser.add_argument(
        "--src",
        type=str,
        nargs="*",
        help=(
            "Source trust_log paths (override defaults). "
            "未指定ならデフォルト候補を使用。"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.src:
        src_files = [Path(p).expanduser() for p in args.src]
    else:
        src_files = DEFAULT_SRC_FILES

    out_path = Path(args.out).expanduser()
    recompute_hash = not args.no_rehash

    merge_trust_logs(src_files=src_files, out_path=out_path, recompute_hash=recompute_hash)


if __name__ == "__main__":
    main()
