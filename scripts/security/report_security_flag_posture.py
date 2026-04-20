#!/usr/bin/env python3
"""Emit a redacted summary of security-sensitive compatibility flag posture.

This helper centralizes operator-facing visibility for flags that can relax
security posture (query API key compatibility and front-end danger presets).
The report intentionally avoids printing raw environment variable values.
"""

from __future__ import annotations

import os
import sys
from typing import Mapping, Sequence

TRUTHY_VALUES = {"1", "true", "yes", "on"}
SECURITY_FLAGS = (
    "VERITAS_ALLOW_SSE_QUERY_API_KEY",
    "VERITAS_ALLOW_WS_QUERY_API_KEY",
    "NEXT_PUBLIC_ENABLE_DANGER_PRESETS",
)


def _is_truthy(value: str | None) -> bool:
    """Return True when an environment variable value is explicitly enabled."""
    if value is None:
        return False
    return value.strip().lower() in TRUTHY_VALUES


def _normalized_profile(env: Mapping[str, str]) -> str:
    """Return the most relevant deployment profile label for observability."""
    veritas_env = (env.get("VERITAS_ENV", "") or "").strip().lower()
    node_env = (env.get("NODE_ENV", "") or "").strip().lower()
    if veritas_env:
        return f"VERITAS_ENV={veritas_env}"
    if node_env:
        return f"NODE_ENV={node_env}"
    return "unknown"


def build_security_flag_posture(
    env: Mapping[str, str] | None = None,
) -> dict[str, bool | str]:
    """Build a redacted snapshot for security-sensitive runtime flags."""
    environ = env if env is not None else os.environ
    posture: dict[str, bool | str] = {
        "profile": _normalized_profile(environ),
    }
    for flag_name in SECURITY_FLAGS:
        posture[flag_name] = _is_truthy(environ.get(flag_name))
    return posture


def main(argv: Sequence[str] | None = None) -> int:
    """Print a redacted security flag summary for operators and CI logs."""
    del argv  # reserved for future CLI options

    posture = build_security_flag_posture(dict(os.environ))
    print("[SECURITY] Security flag posture summary (values redacted).")
    print(f"- profile: {posture['profile']}")
    for flag_name in SECURITY_FLAGS:
        state = "enabled" if posture[flag_name] else "disabled"
        print(f"- {flag_name}: {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
