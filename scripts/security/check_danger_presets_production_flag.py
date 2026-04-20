#!/usr/bin/env python3
"""Validate danger preset front-end flags are disabled in production.

This check prevents accidental exposure of dangerous prompt presets in
production-like environments. The front-end variable is public by design, so
it must remain disabled when deployment profile indicates production.
"""

from __future__ import annotations

import os
import sys
from typing import Sequence

PRODUCTION_ALIASES = {"prod", "production"}
DANGER_PRESET_FLAG = "NEXT_PUBLIC_ENABLE_DANGER_PRESETS"
TRUTHY_VALUES = {"1", "true", "yes", "on"}


def _is_truthy(value: str | None) -> bool:
    """Return True when an environment variable value is explicitly enabled."""
    if value is None:
        return False
    return value.strip().lower() in TRUTHY_VALUES


def _is_production_profile(env: dict[str, str]) -> bool:
    """Return True when environment profile is production-like."""
    veritas_profile = (env.get("VERITAS_ENV", "") or "").strip().lower()
    node_profile = (env.get("NODE_ENV", "") or "").strip().lower()
    return (
        veritas_profile in PRODUCTION_ALIASES
        or node_profile in PRODUCTION_ALIASES
    )


def validate_danger_presets_flag(
    env: dict[str, str] | None = None,
) -> tuple[bool, list[str]]:
    """Validate the danger preset flag for production-like profiles."""
    environ = env if env is not None else os.environ
    findings: list[str] = []

    if not _is_production_profile(environ):
        return True, findings

    if _is_truthy(environ.get(DANGER_PRESET_FLAG)):
        findings.append(
            "[SECURITY] NEXT_PUBLIC_ENABLE_DANGER_PRESETS must be disabled "
            "in production deployments."
        )
        findings.append(
            "- action: unset the flag or set it to false/0/off before release."
        )
        return False, findings

    return True, findings


def main(argv: Sequence[str] | None = None) -> int:
    """Run danger preset production guard as a CLI check."""
    del argv  # reserved for future CLI options

    ok, _findings = validate_danger_presets_flag(dict(os.environ))
    if ok:
        print("Danger preset production flag check passed.")
        return 0

    print(
        "[SECURITY] NEXT_PUBLIC_ENABLE_DANGER_PRESETS must be disabled in "
        "production deployments."
    )
    print("- enabled_danger_preset_flag_detected: true (redacted for safe logging)")
    print("- action: unset the flag before release.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
