"""Tests for warning allowlist governance policy checks."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from scripts.quality.check_warning_allowlist import validate_warning_allowlist


def _write_pyproject(path: Path, filterwarnings: list[str]) -> None:
    content = "\n".join(
        [
            "[tool.pytest.ini_options]",
            "filterwarnings = [",
            *[f'  "{rule.replace(chr(92), chr(92) * 2)}",' for rule in filterwarnings],
            "]",
        ]
    )
    path.write_text(content + "\n", encoding="utf-8")


def _write_allowlist(path: Path, entries: list[dict[str, str]]) -> None:
    payload = {"entries": entries}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_validate_warning_allowlist_passes_with_valid_entries(tmp_path: Path) -> None:
    rule = "ignore:sample warning:DeprecationWarning:sample\\..*"
    pyproject_path = tmp_path / "pyproject.toml"
    allowlist_path = tmp_path / "allowlist.json"

    _write_pyproject(pyproject_path, [rule])
    _write_allowlist(
        allowlist_path,
        [
            {
                "rule": rule,
                "expires_on": "2099-01-01",
                "owner": "qa",
                "reason": "temporary upstream noise",
            }
        ],
    )

    result = validate_warning_allowlist(
        pyproject_path,
        allowlist_path,
        today=date(2026, 3, 6),
    )

    assert result.is_valid is True


def test_validate_warning_allowlist_fails_on_expired_entry(tmp_path: Path) -> None:
    rule = "ignore:sample warning:DeprecationWarning:sample\\..*"
    pyproject_path = tmp_path / "pyproject.toml"
    allowlist_path = tmp_path / "allowlist.json"

    _write_pyproject(pyproject_path, [rule])
    _write_allowlist(
        allowlist_path,
        [
            {
                "rule": rule,
                "expires_on": "2026-01-01",
                "owner": "qa",
                "reason": "temporary upstream noise",
            }
        ],
    )

    result = validate_warning_allowlist(
        pyproject_path,
        allowlist_path,
        today=date(2026, 3, 6),
    )

    assert result.is_valid is False
    assert any("Expired warning allowlist entry" in error for error in result.errors)


def test_validate_warning_allowlist_fails_on_missing_metadata(tmp_path: Path) -> None:
    pyproject_rule = "ignore:py warning:DeprecationWarning:pkg\\..*"
    stale_rule = "ignore:stale warning:DeprecationWarning:stale\\..*"

    pyproject_path = tmp_path / "pyproject.toml"
    allowlist_path = tmp_path / "allowlist.json"

    _write_pyproject(pyproject_path, [pyproject_rule])
    _write_allowlist(
        allowlist_path,
        [
            {
                "rule": stale_rule,
                "expires_on": "2099-01-01",
                "owner": "qa",
                "reason": "leftover",
            }
        ],
    )

    result = validate_warning_allowlist(
        pyproject_path,
        allowlist_path,
        today=date(2026, 3, 6),
    )

    assert result.is_valid is False
    assert any(
        "Missing allowlist metadata" in error for error in result.errors
    )
    assert any(
        "Allowlist contains stale entry" in error for error in result.errors
    )
