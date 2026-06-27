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


def test_failure_reason_metadata_catalog_covers_taxonomy() -> None:
    """Every stable failure reason must have reviewer-facing metadata."""
    assert (
        frozenset(taxonomy.REVIEWER_FAILURE_REASON_METADATA)
        == taxonomy.REVIEWER_FAILURE_REASONS
    )


def test_failure_reason_metadata_catalog_has_allowed_values() -> None:
    """Metadata entries must be complete and use allowlisted facets."""
    for reason, metadata in taxonomy.REVIEWER_FAILURE_REASON_METADATA.items():
        assert metadata.reason == reason
        assert metadata.category in taxonomy.REVIEWER_FAILURE_REASON_CATEGORIES
        assert metadata.severity in taxonomy.REVIEWER_FAILURE_REASON_SEVERITIES
        assert metadata.reviewer_label
        assert metadata.reviewer_explanation
        assert metadata.remediation_hint
        assert metadata.affected_artifacts


def test_failure_reason_metadata_lookup_helpers_are_deterministic() -> None:
    """Lookup helpers expose metadata only for known taxonomy reasons."""
    payload = {
        "cases": [
            {"failure_reasons": ["human_approval_missing"]},
            {"expected_failure_reasons": ["authority_missing"]},
        ]
    }

    metadata = taxonomy.get_failure_reason_metadata("human_approval_missing")
    assert metadata is not None
    assert metadata.reason == "human_approval_missing"
    assert taxonomy.get_failure_reason_metadata("not_in_taxonomy") is None
    assert tuple(taxonomy.failure_reason_metadata_for_payload(payload)) == (
        "authority_missing",
        "human_approval_missing",
    )


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
