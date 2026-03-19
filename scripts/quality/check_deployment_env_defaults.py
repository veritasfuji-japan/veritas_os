#!/usr/bin/env python3
"""Smoke-check deployment templates for unsafe or stale env defaults.

This guard focuses on operator-facing templates and setup scripts so
production-impacting environment misconfigurations are caught before
deployment.
"""

from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class TemplateRule:
    """Validation rule for an operator-facing template file."""

    relative_path: str
    required_tokens: tuple[str, ...] = ()
    forbidden_tokens: tuple[str, ...] = ()


RULES = (
    TemplateRule(
        relative_path=".env.example",
        required_tokens=("VERITAS_API_BASE_URL",),
        forbidden_tokens=(
            "NEXT_PUBLIC_API_BASE_URL",
            "NEXT_PUBLIC_VERITAS_API_BASE_URL",
            "VERITAS_AUTH_ALLOW_FAIL_OPEN=true",
        ),
    ),
    TemplateRule(
        relative_path="setup.sh",
        required_tokens=("VERITAS_API_BASE_URL=http://localhost:8000",),
        forbidden_tokens=(
            "NEXT_PUBLIC_API_BASE_URL",
            "NEXT_PUBLIC_VERITAS_API_BASE_URL",
            "VERITAS_AUTH_ALLOW_FAIL_OPEN=true",
        ),
    ),
)


def _validate_rule(rule: TemplateRule) -> list[str]:
    """Return human-readable violations for the given template rule."""
    path = REPO_ROOT / rule.relative_path
    if not path.exists():
        return [f"Missing required template file: {rule.relative_path}"]

    content = path.read_text(encoding="utf-8")
    violations: list[str] = []

    for token in rule.required_tokens:
        if token not in content:
            violations.append(
                f"{rule.relative_path}: missing required token {token!r}"
            )

    for token in rule.forbidden_tokens:
        if token in content:
            violations.append(
                f"{rule.relative_path}: forbidden token present {token!r}"
            )

    return violations


def main() -> int:
    """Run the deployment-template smoke check."""
    violations: list[str] = []
    for rule in RULES:
        violations.extend(_validate_rule(rule))

    if not violations:
        print("Deployment env templates passed smoke checks.")
        return 0

    print("[SECURITY] Deployment env template issues detected:")
    for violation in violations:
        print(f"- {violation}")
    print(
        "\nUse server-only VERITAS_* variables in operator-facing templates and "
        "never ship fail-open auth flags in default configuration."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
