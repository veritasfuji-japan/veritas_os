"""Operator-only CLI for local registry checkpoint capture and pinned checks.

`capture` writes an unsigned checkpoint. It prints the canonical SHA-256;
operators MUST retain that SHA independently of the registry and JSON file.
This CLI does not publish, sign or authenticate any checkpoint.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

from scripts.validation.audit_registry_checkpoint_v0_1 import (
    _digest,
    capture_checkpoint,
    check_registry_against_pin,
)
from veritas_os.security.hash import canonical_json_dumps

_MAX_REFERENCE_BYTES = 131072


async def _capture(path: Path) -> int:
    status, checkpoint = await capture_checkpoint()
    if status != "SNAPSHOT_READY_UNAUTHENTICATED" or checkpoint is None:
        print(status, file=sys.stderr)
        return 2
    content = (canonical_json_dumps(checkpoint) + "\n").encode("utf-8")
    if len(content) > _MAX_REFERENCE_BYTES:
        print("INCOMPLETE", file=sys.stderr)
        return 2
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except OSError:
        print("OUTPUT_UNAVAILABLE", file=sys.stderr)
        return 2
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
    except OSError:
        print("OUTPUT_UNAVAILABLE", file=sys.stderr)
        return 2
    print("SNAPSHOT_READY_UNAUTHENTICATED")
    print("checkpoint_file:", str(path))
    print("canonical_pinned_sha256:", _digest(checkpoint))
    print("PIN THIS HASH IN AN INDEPENDENT, ACCESS-CONTROLLED LOCATION")
    return 0


async def _verify(path: Path, pin: str) -> int:
    try:
        if not path.is_file() or path.stat().st_size > _MAX_REFERENCE_BYTES:
            print("REFERENCE_INVALID", file=sys.stderr)
            return 2
        reference = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        print("REFERENCE_INVALID", file=sys.stderr)
        return 2
    status = await check_registry_against_pin(
        reference=reference, pinned_reference_sha256=pin,
    )
    print(status)
    return 0 if status in {
        "HISTORY_UNCHANGED_UNAUTHENTICATED",
        "HISTORY_EXTENDED_UNAUTHENTICATED",
    } else 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Locally check bounded PostgreSQL audit history against a separately pinned hash."
    )
    subs = parser.add_subparsers(dest="command", required=True)
    capture = subs.add_parser("capture")
    capture.add_argument("--output", required=True, type=Path)
    verify = subs.add_parser("verify")
    verify.add_argument("--reference", required=True, type=Path)
    verify.add_argument("--pinned-sha256", required=True)
    args = parser.parse_args()
    if args.command == "capture":
        return asyncio.run(_capture(args.output))
    return asyncio.run(_verify(args.reference, args.pinned_sha256))


if __name__ == "__main__":
    raise SystemExit(main())
