#!/usr/bin/env python3
"""Validate pytest warning allowlist entries with expiration dates.

This script enforces a warning governance policy by checking that each
"ignore" entry in ``[tool.pytest.ini_options].filterwarnings`` has a matching
allowlist record with an owner, reason, and non-expired deadline.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class AllowlistEntry:
    """Single allowlisted warning rule with governance metadata."""

    rule: str
    expires_on: date
    owner: str
    reason: str


@dataclass(frozen=True)
class ValidationResult:
    """Result container for policy validation."""

    errors: list[str]

    @property
    def is_valid(self) -> bool:
        """Return True when no validation errors are found."""
        return not self.errors


def _load_pytest_ignore_rules(pyproject_path: Path) -> list[str]:
    """Load only ``ignore:`` warning filter rules from pyproject.toml."""
    content = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    tool_section = content.get("tool", {})
    pytest_section = tool_section.get("pytest", {})
    ini_options = pytest_section.get("ini_options", {})
    raw_rules = ini_options.get("filterwarnings", [])
    return [str(rule) for rule in raw_rules if str(rule).startswith("ignore:")]


def _load_allowlist(allowlist_path: Path) -> dict[str, AllowlistEntry]:
    """Load allowlist entries from JSON keyed by warning rule string."""
    payload = json.loads(allowlist_path.read_text(encoding="utf-8"))
    entries: dict[str, AllowlistEntry] = {}

    for item in payload.get("entries", []):
        expires_on = datetime.strptime(item["expires_on"], "%Y-%m-%d").date()
        entry = AllowlistEntry(
            rule=item["rule"],
            expires_on=expires_on,
            owner=item["owner"],
            reason=item["reason"],
        )
        entries[entry.rule] = entry

    return entries


def validate_warning_allowlist(
    pyproject_path: Path,
    allowlist_path: Path,
    *,
    today: date | None = None,
) -> ValidationResult:
    """Validate pytest ignore rules against the warning allowlist policy."""
    check_date = today or datetime.now(tz=UTC).date()
    errors: list[str] = []

    ignore_rules = _load_pytest_ignore_rules(pyproject_path)
    allowlist_entries = _load_allowlist(allowlist_path)

    for rule in ignore_rules:
        entry = allowlist_entries.get(rule)
        if entry is None:
            errors.append(
                "Missing allowlist metadata for pytest warning rule: "
                f"{rule}"
            )
            continue
        if entry.expires_on < check_date:
            errors.append(
                "Expired warning allowlist entry: "
                f"{rule} (expired {entry.expires_on.isoformat()})"
            )

    for rule in allowlist_entries:
        if rule not in ignore_rules:
            errors.append(
                "Allowlist contains stale entry that no longer exists in "
                f"pyproject.toml: {rule}"
            )

    return ValidationResult(errors=errors)


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=Path("pyproject.toml"),
        help="Path to pyproject.toml",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=Path("config/test_warning_allowlist.json"),
        help="Path to warning allowlist JSON",
    )
    return parser.parse_args()


def main() -> int:
    """Run warning allowlist validation and print policy violations."""
    args = _parse_args()
    result = validate_warning_allowlist(args.pyproject, args.allowlist)

    if result.is_valid:
        print("Warning allowlist policy check passed.")
        return 0

    print("Warning allowlist policy check failed:")
    for error in result.errors:
        print(f"- {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
