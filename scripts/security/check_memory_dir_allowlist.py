#!/usr/bin/env python3
"""Validate MemoryOS directory configuration for production deployments.

This checker prevents a class of configuration drift where MemoryOS would
safely fall back to the default path at runtime, but operators might miss that
`VERITAS_MEMORY_DIR` was rejected. Failing fast in CI/deployment keeps the
fallback visible before release.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Sequence


PRODUCTION_ALIASES = {"prod", "production"}
STRICT_PRODUCTION_ENV = "VERITAS_MEMORY_DIR_CHECK_REQUIRE_PRODUCTION"


def _is_strict_production_required(environ: dict[str, str]) -> bool:
    """Return whether CI must fail when production validation is skipped.

    Security rationale:
        CI skipping this check can hide drift where deployments stop validating
        MemoryOS allowlist settings. This strict mode enforces explicit
        production-profile validation in automated pipelines.
    """
    raw_value = (environ.get(STRICT_PRODUCTION_ENV, "") or "").strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def _normalize_allowlist(raw_allowlist: str) -> list[Path]:
    """Parse and normalize the configured allowlist prefixes."""
    return [
        Path(raw_prefix.strip()).expanduser().resolve(strict=False)
        for raw_prefix in raw_allowlist.split(",")
        if raw_prefix.strip()
    ]


def validate_memory_dir_configuration(
    env: dict[str, str] | None = None,
) -> tuple[bool, list[str]]:
    """Validate `VERITAS_MEMORY_DIR` / allowlist consistency for deployment.

    Returns:
        tuple[bool, list[str]]: Validation success flag and human-readable
        findings. Empty findings on success.
    """
    environ = env if env is not None else os.environ
    findings: list[str] = []
    profile = (environ.get("VERITAS_ENV", "") or "").strip().lower()
    configured_dir = (environ.get("VERITAS_MEMORY_DIR", "") or "").strip()
    raw_allowlist = (environ.get("VERITAS_MEMORY_DIR_ALLOWLIST", "") or "").strip()

    if profile not in PRODUCTION_ALIASES or not configured_dir:
        return True, findings

    candidate = Path(configured_dir).expanduser()
    if not candidate.is_absolute():
        findings.append(
            "[SECURITY] VERITAS_MEMORY_DIR must be an absolute path in "
            "production deployments."
        )
        return False, findings

    if ".." in candidate.parts:
        findings.append(
            "[SECURITY] VERITAS_MEMORY_DIR must not contain path traversal "
            "segments ('..') in production deployments."
        )
        return False, findings

    allow_prefixes = _normalize_allowlist(raw_allowlist)
    if not allow_prefixes:
        findings.append(
            "[SECURITY] VERITAS_MEMORY_DIR_ALLOWLIST must be set when "
            "VERITAS_MEMORY_DIR is configured in production."
        )
        return False, findings

    resolved_candidate = candidate.resolve(strict=False)
    if not any(
        resolved_candidate == prefix or prefix in resolved_candidate.parents
        for prefix in allow_prefixes
    ):
        findings.append(
            "[SECURITY] VERITAS_MEMORY_DIR is outside "
            "VERITAS_MEMORY_DIR_ALLOWLIST. Runtime would fall back to the "
            "default MemoryOS path, so fix the deployment configuration "
            "before release."
        )
        findings.append(f"- configured_dir: {resolved_candidate}")
        findings.append(
            "- allowlist: "
            + ", ".join(str(prefix) for prefix in allow_prefixes)
        )
        return False, findings

    return True, findings


def main(argv: Sequence[str] | None = None) -> int:
    """Run the production memory-dir configuration check."""
    del argv  # reserved for future CLI options

    environ = dict(os.environ)
    ok, findings = validate_memory_dir_configuration(environ)
    strict_required = _is_strict_production_required(environ)
    production_profile = (environ.get("VERITAS_ENV", "") or "").strip().lower()
    configured_dir = (environ.get("VERITAS_MEMORY_DIR", "") or "").strip()

    if strict_required and (
        production_profile not in PRODUCTION_ALIASES or not configured_dir
    ):
        print(
            "[SECURITY] Strict mode enabled, but production MemoryOS allowlist "
            "validation was skipped. Set VERITAS_ENV=production and provide "
            "VERITAS_MEMORY_DIR plus VERITAS_MEMORY_DIR_ALLOWLIST."
        )
        return 1

    if ok:
        if production_profile in PRODUCTION_ALIASES and configured_dir:
            print("MemoryOS production directory configuration is valid.")
        else:
            print(
                "MemoryOS production directory check skipped "
                "(non-production or unset VERITAS_MEMORY_DIR)."
            )
        return 0

    for line in findings:
        print(line)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
