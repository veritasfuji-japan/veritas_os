#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Unified TrustLog verifier CLI.

Verifies both ledgers using one stable API:
1. full ledger chain integrity
2. witness ledger chain integrity
3. witness payload hash correctness
4. witness signature correctness
5. full_payload_hash linkage (legacy-compatible)
6. mirror receipt structure when present
"""

from __future__ import annotations

import argparse
import json
import hashlib
from pathlib import Path
from typing import Any, Iterable, Optional

from veritas_os.audit.trustlog_signed import (
    SIGNED_TRUSTLOG_JSONL,
    _read_all_entries,
    verify_signature,
)
from veritas_os.audit.trustlog_verify import verify_trustlogs
from veritas_os.logging.paths import LOG_DIR

LOG_JSONL = LOG_DIR / "trust_log.jsonl"


def compute_hash(prev_hash: str | None, entry: dict[str, Any]) -> str:
    """Compute chain hash for one full-ledger entry.

    Backward compatibility:
        Retained for existing tests/tools that import this helper directly.
    """
    payload = dict(entry)
    payload.pop("sha256", None)
    payload.pop("sha256_prev", None)
    entry_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    combined = f"{prev_hash}{entry_json}" if prev_hash else entry_json
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def iter_entries(log_path: Path = LOG_JSONL) -> Iterable[dict[str, Any]]:
    """Yield plain JSON entries from a JSONL file, skipping invalid lines."""
    with log_path.open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                yield json.loads(stripped)
            except json.JSONDecodeError:
                continue


def verify_entries(
    entries: Iterable[dict[str, Any]],
) -> tuple[int, list[dict[str, Any]], str | None]:
    """Verify hash-chain continuity and per-entry hash correctness.

    Backward compatibility:
        Retained for existing tests/tools that rely on tuple output.
    """
    prev_hash = None
    total = 0
    errors: list[dict[str, Any]] = []

    for idx, entry in enumerate(entries, 1):
        total = idx
        sha_prev = entry.get("sha256_prev")
        sha_self = entry.get("sha256")

        if sha_prev != prev_hash:
            errors.append(
                {
                    "line": idx,
                    "type": "chain_break",
                    "expected_prev": prev_hash,
                    "actual_prev": sha_prev,
                    "entry_id": entry.get("request_id", "unknown"),
                }
            )

        expected_hash = compute_hash(sha_prev, entry)
        if expected_hash != sha_self:
            errors.append(
                {
                    "line": idx,
                    "type": "hash_mismatch",
                    "expected": expected_hash,
                    "actual": sha_self,
                    "entry_id": entry.get("request_id", "unknown"),
                }
            )

        prev_hash = sha_self

    return total, errors, prev_hash


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify TrustLog ledgers")
    parser.add_argument("--full-log", type=Path, default=LOG_JSONL)
    parser.add_argument("--witness-log", type=Path, default=SIGNED_TRUSTLOG_JSONL)
    parser.add_argument("--max-entries", type=int, default=None)
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    return parser.parse_args()


def _print_human(result: dict) -> None:
    print("🔍 Unified TrustLog Verification")
    print("=" * 60)
    for key in (
        "total_entries",
        "valid_entries",
        "invalid_entries",
        "chain_ok",
        "signature_ok",
        "linkage_ok",
        "mirror_ok",
        "last_hash",
    ):
        print(f"{key}: {result.get(key)}")

    print("detailed_errors:")
    errors = result.get("detailed_errors", [])
    if not errors:
        print("  []")
        return
    for error in errors:
        print(
            "  - "
            f"ledger={error.get('ledger')} "
            f"index={error.get('index')} "
            f"reason={error.get('reason')}"
        )


def main() -> int:
    args = _parse_args()
    witness_entries = _read_all_entries(args.witness_log)
    result = verify_trustlogs(
        full_log_path=args.full_log,
        witness_entries=witness_entries,
        verify_signature_fn=verify_signature,
        max_entries=args.max_entries,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_human(result)

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
