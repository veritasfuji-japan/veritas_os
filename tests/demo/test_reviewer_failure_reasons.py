"""Tests for reviewer/demo failure reason taxonomy constants."""

from __future__ import annotations

from pathlib import Path

from scripts.demo import reviewer_failure_reasons as taxonomy

CENTRALIZED_FAILURE_REASON_CONSTANTS = {
    name: value
    for name, value in vars(taxonomy).items()
    if name.isupper()
    and isinstance(value, str)
    and name != "REVIEWER_FAILURE_REASONS"
}

CENTRALIZED_FAILURE_REASON_VALUES = frozenset(
    CENTRALIZED_FAILURE_REASON_CONSTANTS.values()
)


def test_exported_failure_reason_constants_are_in_taxonomy() -> None:
    """Every centralized string constant must remain part of the taxonomy."""
    assert CENTRALIZED_FAILURE_REASON_CONSTANTS
    assert CENTRALIZED_FAILURE_REASON_VALUES <= taxonomy.REVIEWER_FAILURE_REASONS


def test_exported_failure_reason_constants_have_unique_values() -> None:
    """Centralized failure reason constants must not alias duplicate values."""
    values = tuple(CENTRALIZED_FAILURE_REASON_CONSTANTS.values())
    assert len(values) == len(set(values))


def test_reviewer_failure_reasons_have_no_duplicate_equivalent_values() -> None:
    """The public taxonomy must remain a unique set of string values."""
    values = tuple(taxonomy.REVIEWER_FAILURE_REASONS)
    assert len(values) == len(set(values))


def test_centralized_failure_reason_literals_stay_in_taxonomy_module() -> None:
    """Prevent reintroducing centralized reviewer/demo reason literals."""
    taxonomy_path = Path(taxonomy.__file__).resolve()
    scripts_demo_dir = taxonomy_path.parent
    offenders: list[str] = []

    for path in sorted(scripts_demo_dir.glob("*.py")):
        if path.resolve() == taxonomy_path:
            continue
        source = path.read_text(encoding="utf-8")
        for value in sorted(CENTRALIZED_FAILURE_REASON_VALUES):
            if repr(value) in source or f'"{value}"' in source:
                offenders.append(f"{path.relative_to(Path.cwd())}: {value}")

    assert offenders == []
