"""Read-only audit-verifier CLI requiring independently provisioned TLS + key pins.

This tool makes no remote writes, never signs, and never alters runtime
permissions. The operator must supply the trust anchors separately from DB.
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

from scripts.validation.audit_checkpoint_signed_custody_cli_v0_1 import _read_json
from scripts.validation.audit_remote_custody_https_v0_1 import (
    verify_registry_against_https_custody,
)

_SUCCESS = {
    "HISTORY_UNCHANGED_UNAUTHENTICATED",
    "HISTORY_EXTENDED_UNAUTHENTICATED",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify PostgreSQL local audit history against remote HTTPS custody head."
    )
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--anchor-endpoint", required=True)
    parser.add_argument("--expected-hostname", required=True)
    parser.add_argument("--ca-bundle", required=True, type=Path)
    parser.add_argument("--trusted-signer-public-key-hex", required=True)
    parser.add_argument("--minimum-sequence", required=True, type=int)
    args = parser.parse_args()
    try:
        reference = _read_json(args.reference)
        receipt = _read_json(args.receipt)
        outcome = asyncio.run(verify_registry_against_https_custody(
            reference=reference,
            receipt=receipt,
            endpoint=args.anchor_endpoint,
            expected_hostname=args.expected_hostname,
            ca_bundle=args.ca_bundle,
            trusted_signer_public_key_hex=args.trusted_signer_public_key_hex,
            minimum_sequence=args.minimum_sequence,
        ))
    except (OSError, ValueError, UnicodeError):
        print("AUDIT_REFERENCE_INVALID", file=sys.stderr)
        return 2
    print(outcome)
    return 0 if outcome in _SUCCESS else 2


if __name__ == "__main__":
    raise SystemExit(main())
