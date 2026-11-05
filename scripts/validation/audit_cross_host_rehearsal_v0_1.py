#!/usr/bin/env python3
"""Strict verifier-side, cross-host rehearsal; no remote mutation or SSH commands.

Inputs are independently provisioned by the verifier. This tool checks the
remote head and signed local checkpoint against the current PostgreSQL audit
registry, but cannot establish the remote operator's identity or independence.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import re
import sys

from scripts.validation.audit_remote_custody_https_v0_1 import (
    verify_registry_against_https_custody,
)

_SHA = re.compile(r"^[0-9a-f]{64}$")


def _load(path: Path) -> object:
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("INPUT_FILE_INVALID")
    def unique(pairs):
        obj = {}
        for k, v in pairs:
            if k in obj:
                raise ValueError("DUPLICATE_KEY")
            obj[k] = v
        return obj
    def reject_constant(value):
        raise ValueError("INVALID_JSON_CONSTANT")
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=unique, parse_constant=reject_constant,
    )


async def run(
    *, reference: Path, receipt: Path, endpoint: str, expected_hostname: str,
    ca_bundle: Path, trusted_signer_public_key_hex: str, minimum_sequence: int,
) -> str:
    try:
        ref = _load(reference)
        signed = _load(receipt)
        if not ca_bundle.is_file() or not _SHA.fullmatch(trusted_signer_public_key_hex):
            return "EXTERNAL_TRUST_REQUIRED"
        if type(minimum_sequence) is not int or minimum_sequence < 1:
            return "EXTERNAL_TRUST_REQUIRED"
        return await verify_registry_against_https_custody(
            reference=ref, receipt=signed,
            endpoint=endpoint, expected_hostname=expected_hostname,
            ca_bundle=ca_bundle,
            trusted_signer_public_key_hex=trusted_signer_public_key_hex,
            minimum_sequence=minimum_sequence,
        )
    except (OSError, ValueError, TypeError, UnicodeError):
        return "INPUT_UNAVAILABLE"


def main() -> int:
    parser = argparse.ArgumentParser(description="Remote custody independent verifier rehearsal")
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--expected-hostname", required=True)
    parser.add_argument("--ca-bundle", required=True, type=Path)
    parser.add_argument("--trusted-signer-public-key-hex", required=True)
    parser.add_argument("--minimum-sequence", required=True, type=int)
    args = parser.parse_args()
    result = asyncio.run(run(**vars(args)))
    print(json.dumps({"verdict": result, "verified": result == "HISTORY_UNCHANGED_UNAUTHENTICATED"}, sort_keys=True))
    return 0 if result == "HISTORY_UNCHANGED_UNAUTHENTICATED" else 2


if __name__ == "__main__":
    sys.exit(main())
