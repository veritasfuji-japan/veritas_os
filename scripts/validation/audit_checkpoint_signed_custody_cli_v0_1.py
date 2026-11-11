"""Offline signer/verifier CLI for independently pinned audit custody receipts.

The signer has no live DB credentials and must receive an independently
acquired checkpoint. The verifier requires a public key AND receipt-head digest
from a trust channel external to the checkpoint and database.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import stat
import sys

from scripts.validation.audit_checkpoint_signed_custody_v0_1 import (
    check_registry_against_signed_reference,
    sign_checkpoint,
)
from veritas_os.security.hash import canonical_json_dumps, sha256_of_canonical_json

_MAX_JSON = 131072


def _read_json(path: Path) -> object:
    # Read bounded bytes; an attacker-controlled FIFO or device must not
    # block the verifier. No symlinks, and no following changed file paths.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("NOT_REGULAR")
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            content = stream.read(_MAX_JSON + 1)
        if len(content) > _MAX_JSON:
            raise ValueError("TOO_LARGE")
        return json.loads(content)
    finally:
        if fd >= 0:
            os.close(fd)


def _read_restricted_raw_key(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        s = os.fstat(fd)
        if (
            not stat.S_ISREG(s.st_mode)
            or s.st_uid != os.geteuid()
            or (stat.S_IMODE(s.st_mode) & 0o077) != 0
        ):
            raise PermissionError("CUSTODY_KEY_PERMISSIONS_INVALID")
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            value = stream.read(33)
        if len(value) != 32:
            raise ValueError("CUSTODY_KEY_LENGTH_INVALID")
        return value
    finally:
        if fd >= 0:
            os.close(fd)


def _write_exclusive_json(path: Path, data: dict) -> None:
    payload = (canonical_json_dumps(data) + "\n").encode("utf-8")
    if len(payload) > _MAX_JSON:
        raise ValueError("OUTPUT_TOO_LARGE")
    fd = os.open(
        path,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if fd >= 0:
            os.close(fd)


async def _run(args: argparse.Namespace) -> int:
    try:
        reference = _read_json(args.reference)
        if args.command == "attest":
            private = _read_restricted_raw_key(args.private_key)
            receipt = sign_checkpoint(
                reference,
                private_key_raw=private,
                sequence=args.sequence,
                previous_receipt_sha256=args.previous_receipt_sha256,
            )
            _write_exclusive_json(args.output, receipt)
            print("SIGNED_LOCAL_CHECKPOINT_ATTESTATION_CREATED")
            print("receipt_head_sha256:", sha256_of_canonical_json(receipt))
            print("SIGNING IS NOT AN EXTERNAL CUSTODY OR COMPLETENESS PROOF")
            return 0
        receipt = _read_json(args.receipt)
        status = await check_registry_against_signed_reference(
            reference=reference,
            receipt=receipt,
            trusted_public_key_hex=args.trusted_public_key_hex,
            expected_head_sha256=args.expected_head_sha256,
        )
        print(status)
        return 0 if status in {
            "HISTORY_UNCHANGED_UNAUTHENTICATED",
            "HISTORY_EXTENDED_UNAUTHENTICATED",
        } else 2
    except (OSError, ValueError, TypeError, PermissionError) as exc:
        # Never print key contents or system file paths from unexpected errors.
        print("CUSTODY_INPUT_OR_STORAGE_INVALID", file=sys.stderr)
        return 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline audit custody receipt v0.1")
    subs = parser.add_subparsers(dest="command", required=True)
    attest = subs.add_parser("attest")
    attest.add_argument("--reference", type=Path, required=True)
    attest.add_argument("--private-key", type=Path, required=True)
    attest.add_argument("--output", type=Path, required=True)
    attest.add_argument("--sequence", type=int, required=True)
    attest.add_argument("--previous-receipt-sha256", required=True)
    verify = subs.add_parser("verify")
    verify.add_argument("--reference", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    verify.add_argument("--trusted-public-key-hex", required=True)
    verify.add_argument("--expected-head-sha256", required=True)
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
