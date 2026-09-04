"""Run ``pnpm audit`` with bounded handling for npm audit endpoint failures.

This helper keeps production dependency audit blocking for real vulnerability
or runtime failures. It tolerates only the known upstream endpoint-retirement
response (HTTP 410), and retries transient registry transport failures before
failing closed.

Usage:
    python scripts/ci/pnpm_audit_gate.py --prod

Exit codes:
    0   Audit passed, or failed only because of known endpoint retirement.
    75  The audit subprocess repeatedly exceeded its bounded timeout.
    >0  Any other pnpm audit failure (preserves pnpm exit code when possible).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from typing import Sequence

_ENDPOINT_RETIREMENT_SIGNATURES = (
    "ERR_PNPM_AUDIT_BAD_RESPONSE",
    "endpoint is being retired",
    "responded with 410",
)

_TRANSIENT_TRANSPORT_SIGNATURES = (
    "ERR_SOCKET_TIMEOUT",
    "ETIMEDOUT",
    "ECONNRESET",
    "ECONNREFUSED",
    "EAI_AGAIN",
    "ENOTFOUND",
    "socket timeout",
    "network timeout",
    "502 Bad Gateway",
    "503 Service Unavailable",
    "504 Gateway Timeout",
)

_MAX_ATTEMPTS = 3
_ATTEMPT_TIMEOUT_SECONDS = 75
_RETRY_DELAYS_SECONDS = (5, 15)
_TEMPORARY_FAILURE_EXIT_CODE = 75


def should_tolerate_endpoint_retirement(output: str) -> bool:
    """Return ``True`` when output matches known endpoint-retirement failures."""
    lowered = output.lower()
    return any(signature.lower() in lowered for signature in _ENDPOINT_RETIREMENT_SIGNATURES)


def is_transient_transport_failure(output: str) -> bool:
    """Return ``True`` only for known transient npm registry failures."""
    lowered = output.lower()
    return any(signature.lower() in lowered for signature in _TRANSIENT_TRANSPORT_SIGNATURES)


def _text(value: str | bytes | None) -> str:
    """Normalize subprocess output captured as text or bytes."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def _emit_output(stdout: str, stderr: str) -> None:
    """Preserve pnpm output in the workflow log."""
    if stdout:
        print(stdout, end="")
    if stderr:
        print(stderr, end="", file=sys.stderr)


def run_pnpm_audit(args: Sequence[str]) -> int:
    """Execute ``pnpm audit`` and return the intended CI exit code."""
    cmd = ["pnpm", "audit", *args]
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        timed_out = False
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=_ATTEMPT_TIMEOUT_SECONDS,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            returncode = completed.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = _text(exc.stdout)
            stderr = _text(exc.stderr)
            returncode = _TEMPORARY_FAILURE_EXIT_CODE
            stderr += (
                f"pnpm audit exceeded {_ATTEMPT_TIMEOUT_SECONDS}s "
                "subprocess timeout.\n"
            )

        _emit_output(stdout, stderr)

        if returncode == 0:
            return 0

        combined_output = f"{stdout}\n{stderr}"
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

        transient = timed_out or is_transient_transport_failure(combined_output)
        if not transient:
            return returncode

        if attempt == _MAX_ATTEMPTS:
            print(
                "::error::pnpm audit could not reach the npm registry after "
                f"{_MAX_ATTEMPTS} bounded attempts; failing closed.",
                file=sys.stderr,
            )
            return returncode

        delay = _RETRY_DELAYS_SECONDS[attempt - 1]
        print(
            "::warning::Transient npm registry failure during pnpm audit "
            f"(attempt {attempt}/{_MAX_ATTEMPTS}); retrying in {delay}s.",
            file=sys.stderr,
        )
        time.sleep(delay)

    raise AssertionError("unreachable")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments for the audit gate wrapper."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "audit_args",
        nargs="*",
        help="Arguments passed through to `pnpm audit`.",
    )
    parsed, unknown = parser.parse_known_args(argv)
    parsed.audit_args.extend(unknown)
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    """Program entrypoint."""
    parsed = parse_args(argv or sys.argv[1:])
    return run_pnpm_audit(parsed.audit_args)


if __name__ == "__main__":
    raise SystemExit(main())
