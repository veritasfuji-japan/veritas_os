#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Trust Log Verifier - 論文の式に準拠

検証内容:
1. sha256_prev の連続性（チェーン検証）
2. hₜ = SHA256(hₜ₋₁ || rₜ) の正しさ

Usage:
    python scripts/verify_trust_log.py
"""

import json
import hashlib
from pathlib import Path
from typing import Iterable, Any

# パスの設定（環境に応じて調整）
try:
    from veritas_os.logging.paths import LOG_DIR
    LOG_JSONL = LOG_DIR / "trust_log.jsonl"
except ImportError:
    # フォールバック
    SCRIPT_DIR = Path(__file__).parent
    REPO_ROOT = SCRIPT_DIR.parent
    LOG_DIR = REPO_ROOT / "scripts" / "logs"
    LOG_JSONL = LOG_DIR / "trust_log.jsonl"


def compute_hash(prev_hash: str | None, entry: dict) -> str:
    """
    論文の式に従ったハッシュ計算: hₜ = SHA256(hₜ₋₁ || rₜ)
    
    Args:
        prev_hash: 直前のハッシュ値 (hₜ₋₁)
        entry: 現在のエントリ (rₜ)
    
    Returns:
        計算されたハッシュ値 (hₜ)
    """
    # エントリをコピーして、sha256とsha256_prevを除外
    payload = dict(entry)
    payload.pop("sha256", None)
    payload.pop("sha256_prev", None)
    
    # rₜ を JSON化（キーをソートして一意性を保証）
    entry_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    
    # hₜ₋₁ || rₜ を結合
    if prev_hash:
        combined = prev_hash + entry_json
    else:
        # 最初のエントリの場合は rₜ のみ
        combined = entry_json
    
    # SHA-256計算
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def iter_entries(log_path: Path = LOG_JSONL) -> Iterable[dict[str, Any]]:
    """Yield JSON entries from a trust-log JSONL file.

    Invalid JSON lines are skipped with a warning so one broken line does not
    block verification of the rest of the file.
    """
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                print(f"⚠️  JSON decode error: {e}")
                continue


def verify_entries(entries: Iterable[dict[str, Any]]) -> tuple[int, list[dict[str, Any]], str | None]:
    """Verify trust-log chain/hash integrity for a stream of entries.

    Returns a tuple of (total_entries, errors, last_hash).
    """
    prev_hash = None
    total = 0
    errors: list[dict[str, Any]] = []

    for i, entry in enumerate(entries, 1):
        total = i
        sha_prev = entry.get("sha256_prev")
        sha_self = entry.get("sha256")

        if sha_prev != prev_hash:
            errors.append({
                "line": i,
                "type": "chain_break",
                "expected_prev": prev_hash,
                "actual_prev": sha_prev,
                "entry_id": entry.get("request_id", "unknown"),
            })

        calc_hash = compute_hash(sha_prev, entry)
        if calc_hash != sha_self:
            errors.append({
                "line": i,
                "type": "hash_mismatch",
                "expected": calc_hash,
                "actual": sha_self,
                "entry_id": entry.get("request_id", "unknown"),
            })

        prev_hash = sha_self

    return total, errors, prev_hash


def main():
    print("🔍 Trust Log Verification")
    print("=" * 60)
    print(f"File: {LOG_JSONL}")
    print()
    
    if not LOG_JSONL.exists():
        print("❌ trust_log.jsonl not found")
        print(f"   Expected location: {LOG_JSONL}")
        return 1
    
    total, errors, last_hash = verify_entries(iter_entries())
    
    print(f"Total entries: {total}")
    print()
    
    if errors:
        print(f"❌ Verification FAILED ({len(errors)} errors)")
        print()
        
        # エラーの種類別にカウント
        chain_breaks = sum(1 for e in errors if e['type'] == 'chain_break')
        hash_mismatches = sum(1 for e in errors if e['type'] == 'hash_mismatch')
        
        print("Error breakdown:")
        print(f"  Chain breaks:    {chain_breaks}")
        print(f"  Hash mismatches: {hash_mismatches}")
        print()
        
        # 最初の5件のエラーを詳細表示
        print("First errors:")
        for err in errors[:5]:
            print(f"  Line {err['line']}: {err['type']}")
            if err['type'] == 'chain_break':
                print(f"    Expected prev: {err['expected_prev']}")
                print(f"    Actual prev:   {err['actual_prev']}")
            else:
                print(f"    Expected hash: {err['expected'][:16]}...")
                print(f"    Actual hash:   {err['actual'][:16]}...")
            print(f"    Entry ID: {err['entry_id']}")
            print()
        
        if len(errors) > 5:
            print(f"... and {len(errors) - 5} more errors")
        
        print()
        print("💡 Note: If you recently updated trust_log.py, old logs")
        print("   may fail verification. This is expected.")
        print()
        print("   To fix:")
        print("   1. Back up old logs:")
        print("      mv scripts/logs/trust_log.jsonl scripts/logs/trust_log.jsonl.old")
        print("   2. Start fresh (next /v1/decide call will create new log)")
        
        return 1
    else:
        print("✅ Verification PASSED")
        print(f"   All {total} entries are valid")
        print("   Hash chain is intact")
        print()
        print("   Current chain head hash: " + (last_hash[:16] if total > 0 and last_hash else "N/A") + "...")
        if total > 0 and last_hash:
            print(f"   Last entry hash:  {last_hash[:16]}...")
        
        return 0


if __name__ == "__main__":
    exit(main())
