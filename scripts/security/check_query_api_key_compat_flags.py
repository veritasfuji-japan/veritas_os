#!/usr/bin/env python3
"""Validate query API key compatibility flags for production safety.

This check prevents production deployments from enabling legacy query-string
API key authentication for SSE/WebSocket endpoints. Query-string credentials are
more likely to leak via access logs, referrers, and monitoring systems.
"""

from __future__ import annotations

import os
import sys
from typing import Sequence

PRODUCTION_ALIASES = {"prod", "production"}
DISALLOWED_FLAGS = (
    "VERITAS_ALLOW_SSE_QUERY_API_KEY",
    "VERITAS_ALLOW_WS_QUERY_API_KEY",
)
TRUTHY_VALUES = {"1", "true", "yes", "on"}


def _is_truthy(value: str | None) -> bool:
    """Return True when an environment variable value is explicitly enabled."""
    if value is None:
        return False
    return value.strip().lower() in TRUTHY_VALUES


def validate_query_api_key_compat_flags(
    env: dict[str, str] | None = None,
) -> tuple[bool, list[str]]:
    """Validate query API key compatibility flags for the active profile.

    Returns:
        tuple[bool, list[str]]: Success flag and findings. Empty findings
        indicates the configuration is safe for the current profile.
    """
    environ = env if env is not None else os.environ
    profile = (environ.get("VERITAS_ENV", "") or "").strip().lower()
    findings: list[str] = []

    if profile not in PRODUCTION_ALIASES:
        return True, findings

    enabled_flags = [
        flag_name
        for flag_name in DISALLOWED_FLAGS
        if _is_truthy(environ.get(flag_name))
    ]
    if enabled_flags:
        findings.append(
            "[SECURITY] Query API key compatibility flags must be disabled in "
            "production deployments."
        )
        findings.append("- enabled_flags: " + ", ".join(enabled_flags))
        findings.append(
            "- action: unset the flags or set them to false/0/off before "
            "release."
        )
        return False, findings

    return True, findings


def main(argv: Sequence[str] | None = None) -> int:
    """Run the query API key compatibility flag validation check."""
    del argv  # reserved for future CLI options

    profile = (os.environ.get("VERITAS_ENV", "") or "").strip().lower()
    ok, findings = validate_query_api_key_compat_flags(dict(os.environ))
    if ok:
        if profile in PRODUCTION_ALIASES:
            print("Query API key compatibility flags are disabled for production.")
        else:
            print(
                "Query API key compatibility flag check skipped "
                "(non-production profile)."
            )
        return 0

    for line in findings:
        print(line)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
