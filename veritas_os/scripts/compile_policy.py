"""CLI entrypoint for VERITAS Policy Compiler v0.1."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from veritas_os.policy.compiler import compile_policy_to_bundle
from veritas_os.policy.models import PolicyValidationError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile VERITAS source policy")
    parser.add_argument("source", help="Path to source policy YAML/JSON")
    parser.add_argument(
        "--output-dir",
        default="artifacts/policy_compiler",
        help="Output directory for compiled bundle artifacts",
    )
    parser.add_argument(
        "--compiled-at",
        default=None,
        help="Optional ISO-8601 UTC timestamp for deterministic manifests",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        result = compile_policy_to_bundle(
            source_policy_path=Path(args.source),
            output_dir=Path(args.output_dir),
            compiled_at=args.compiled_at,
        )
    except PolicyValidationError as exc:
        print(f"policy compile failed: {exc}", file=sys.stderr)
        return 2

    print(f"bundle_dir={result.bundle_dir}")
    print(f"manifest={result.manifest_path}")
    print(f"archive={result.archive_path}")
    print(f"semantic_hash={result.semantic_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
