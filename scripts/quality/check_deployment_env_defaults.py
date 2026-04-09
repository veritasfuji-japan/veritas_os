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
from typing import Iterable

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class TemplateRule:
    """Validation rule for an operator-facing template file."""

    relative_path: str
    required_tokens: tuple[str, ...] = ()
    forbidden_tokens: tuple[str, ...] = ()
    forbidden_env_keys: tuple[str, ...] = ()
    forbidden_env_assignments: tuple[tuple[str, str], ...] = ()


RULES = (
    TemplateRule(
        relative_path=".env.example",
        required_tokens=("VERITAS_API_BASE_URL", "VERITAS_ENV=production"),
        forbidden_tokens=(
            "NEXT_PUBLIC_API_BASE_URL",
            "NEXT_PUBLIC_VERITAS_API_BASE_URL",
        ),
        forbidden_env_assignments=(
            ("VERITAS_AUTH_ALLOW_FAIL_OPEN", "true"),
            ("VERITAS_AUTH_STORE_FAILURE_MODE", "open"),
        ),
        forbidden_env_keys=(
            "VERITAS_ENABLE_DIRECT_FUJI_API",
        ),
    ),
    TemplateRule(
        relative_path="setup.sh",
        required_tokens=(
            "VERITAS_API_BASE_URL=http://localhost:8000",
            "VERITAS_ENV=production",
        ),
        forbidden_tokens=(
            "NEXT_PUBLIC_API_BASE_URL",
            "NEXT_PUBLIC_VERITAS_API_BASE_URL",
        ),
        forbidden_env_assignments=(
            ("VERITAS_AUTH_ALLOW_FAIL_OPEN", "true"),
            ("VERITAS_AUTH_STORE_FAILURE_MODE", "open"),
        ),
        forbidden_env_keys=(
            "VERITAS_ENABLE_DIRECT_FUJI_API",
        ),
    ),
)


def _iter_env_assignments(content: str) -> Iterable[tuple[str, str]]:
    """Yield normalized ``KEY=value`` pairs from shell-style env templates.

    The parser intentionally ignores comments and optional ``export`` prefixes so
    deployment checks catch dangerous defaults even when spacing or casing varies.
    """
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        yield key.strip(), value.strip().strip("'\"")


def _collect_forbidden_assignment_violations(
    *,
    rule: TemplateRule,
    assignments: Iterable[tuple[str, str]],
) -> list[str]:
    """Return violations for forbidden env assignments in a template."""
    normalized_assignments = {
        key.strip(): value.strip().lower() for key, value in assignments
    }
    violations: list[str] = []
    for key, value in rule.forbidden_env_assignments:
        current_value = normalized_assignments.get(key)
        if current_value == value.strip().lower():
            violations.append(
                f"{rule.relative_path}: forbidden env assignment {key}={value}"
            )
    return violations


def _collect_forbidden_key_violations(
    *,
    rule: TemplateRule,
    assignments: Iterable[tuple[str, str]],
) -> list[str]:
    """Return violations when forbidden env keys appear with any value."""
    normalized_keys = {key.strip() for key, _ in assignments}
    violations: list[str] = []
    for key in rule.forbidden_env_keys:
        if key in normalized_keys:
            violations.append(
                f"{rule.relative_path}: forbidden env key present {key}"
            )
    return violations


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

    assignments = list(_iter_env_assignments(content))
    violations.extend(
        _collect_forbidden_assignment_violations(
            rule=rule,
            assignments=assignments,
        )
    )
    violations.extend(
        _collect_forbidden_key_violations(
            rule=rule,
            assignments=assignments,
        )
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
        "never ship fail-open auth flags, direct FUJI API flags, or open "
        "auth-store failure modes in default configuration."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
