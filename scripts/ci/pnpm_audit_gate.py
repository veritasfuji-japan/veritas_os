"""Run ``pnpm audit`` with explicit handling for retired npm audit endpoints.

This helper keeps production dependency audit blocking for real vulnerability
or runtime failures, while tolerating the known upstream endpoint retirement
response (HTTP 410) that currently breaks ``pnpm audit`` regardless of local
package state.

Usage:
    python scripts/ci/pnpm_audit_gate.py --prod

Exit codes:
    0  Audit passed, or failed only because of known endpoint retirement.
    >0 Any other pnpm audit failure (preserves pnpm exit code when possible).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Sequence

_ENDPOINT_RETIREMENT_SIGNATURES = (
    "ERR_PNPM_AUDIT_BAD_RESPONSE",
    "endpoint is being retired",
    "responded with 410",
)


def should_tolerate_endpoint_retirement(output: str) -> bool:
    """Return ``True`` when output matches known endpoint-retirement failures."""
    lowered = output.lower()
    return any(signature.lower() in lowered for signature in _ENDPOINT_RETIREMENT_SIGNATURES)


def run_pnpm_audit(args: Sequence[str]) -> int:
    """Execute ``pnpm audit`` and return the intended CI exit code."""
    cmd = ["pnpm", "audit", *args]
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)

    if completed.returncode == 0:
        return 0

    combined_output = f"{completed.stdout}\n{completed.stderr}"
    if should_tolerate_endpoint_retirement(combined_output):
        print(
            "::warning::pnpm audit failed due to npm audit endpoint retirement "
            "(HTTP 410).",
            file=sys.stderr,
        )
        print(
            "::warning::Treating this as a temporary upstream outage to "
            "avoid false-red CI.",
            file=sys.stderr,
        )
        print(
            "::warning::Security risk: production Node dependency "
            "vulnerability blocking is degraded until scanner migration is "
            "completed.",
            file=sys.stderr,
        )
        return 0

    return completed.returncode


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments for the audit gate wrapper."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "audit_args",
        nargs="*",
        help="Arguments passed through to `pnpm audit`.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Program entrypoint."""
    parsed = parse_args(argv or sys.argv[1:])
    return run_pnpm_audit(parsed.audit_args)


if __name__ == "__main__":
    raise SystemExit(main())
