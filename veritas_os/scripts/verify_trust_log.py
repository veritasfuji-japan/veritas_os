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
from pathlib import Path

from veritas_os.audit.trustlog_signed import (
    SIGNED_TRUSTLOG_JSONL,
    _read_all_entries,
    verify_signature,
)
from veritas_os.audit.trustlog_verify import verify_trustlogs
from veritas_os.logging.paths import LOG_DIR

LOG_JSONL = LOG_DIR / "trust_log.jsonl"


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
    else:
        for error in errors:
            print(
                "  - "
                f"ledger={error.get('ledger')} "
                f"index={error.get('index')} "
                f"reason={error.get('reason')} "
                f"code={error.get('code')} "
                f"tamper_suspected={error.get('tamper_suspected')}"
            )
    notes = result.get("verification_notes", [])
    print("verification_notes:")
    if not notes:
        print("  []")
        return
    for note in notes:
        print(
            "  - "
            f"ledger={note.get('ledger')} "
            f"index={note.get('index')} "
            f"reason={note.get('reason')} "
            f"code={note.get('code')}"
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
