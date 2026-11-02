"""Offline custody owner CLI and read-only TLS endpoint.

No service token, remote POST, runtime bind authorization, or private signing
key is exposed here. Keys and protected head floor live outside audit DB.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from scripts.validation.audit_checkpoint_signed_custody_cli_v0_1 import _read_json
from scripts.validation.audit_custody_head_store_v0_1 import (
    create_store, publish, read_head, serve_tls,
)
from veritas_os.security.hash import canonical_json_dumps


def main() -> int:
    parser = argparse.ArgumentParser(description="Isolated audit custody publisher")
    subs = parser.add_subparsers(dest="command", required=True)

    init = subs.add_parser("init")
    init.add_argument("--db", type=Path, required=True)
    init.add_argument("--signer-public-key-hex", required=True)

    publish_parser = subs.add_parser("publish")
    publish_parser.add_argument("--db", type=Path, required=True)
    publish_parser.add_argument("--reference", type=Path, required=True)
    publish_parser.add_argument("--receipt", type=Path, required=True)

    head = subs.add_parser("head")
    head.add_argument("--db", type=Path, required=True)

    serve = subs.add_parser("serve")
    serve.add_argument("--db", type=Path, required=True)
    serve.add_argument("--certificate", type=Path, required=True)
    serve.add_argument("--private-key", type=Path, required=True)
    serve.add_argument("--listen-host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8443)

    args = parser.parse_args()
    try:
        if args.command == "init":
            status = create_store(args.db, signer_public_key_hex=args.signer_public_key_hex)
        elif args.command == "publish":
            reference, receipt = _read_json(args.reference), _read_json(args.receipt)
            status = publish(args.db, reference=reference, receipt=receipt)
        elif args.command == "head":
            status, result = read_head(args.db)
            if status == "HEAD_OBSERVED":
                print(canonical_json_dumps(result))
        else:
            serve_tls(
                args.db, certificate=args.certificate, private_key=args.private_key,
                listen_host=args.listen_host, port=args.port,
            )
            return 0
    except (OSError, ValueError, TypeError):
        print("CUSTODY_OPERATION_UNAVAILABLE", file=sys.stderr)
        return 2
    if args.command != "head" or status != "HEAD_OBSERVED":
        print(status)
    return 0 if status in {"STORE_CREATED", "NEW_HEAD_PUBLISHED", "ALREADY_PUBLISHED", "HEAD_OBSERVED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
