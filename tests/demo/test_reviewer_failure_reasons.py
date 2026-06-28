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


def test_generated_failure_reason_catalog_json_matches_metadata() -> None:
    """Generated JSON catalog must exactly mirror metadata source of truth."""
    import json

    from scripts.demo.generate_reviewer_failure_reason_catalog import (
        JSON_OUTPUT_PATH,
        build_catalog,
        render_json,
    )

    catalog = build_catalog()
    assert JSON_OUTPUT_PATH.read_text(encoding="utf-8") == render_json(catalog)
    assert json.loads(JSON_OUTPUT_PATH.read_text(encoding="utf-8")) == json.loads(
        render_json(catalog)
    )
    reasons = catalog["reasons"]

    assert catalog["total_reasons"] == len(taxonomy.REVIEWER_FAILURE_REASONS)
    assert catalog["categories"] == sorted(
        taxonomy.REVIEWER_FAILURE_REASON_CATEGORIES
    )
    assert catalog["severities"] == sorted(
        taxonomy.REVIEWER_FAILURE_REASON_SEVERITIES
    )
    assert [entry["reason"] for entry in reasons] == sorted(
        taxonomy.REVIEWER_FAILURE_REASONS
    )
    assert reasons == [
        {
            "reason": metadata.reason,
            "category": metadata.category,
            "severity": metadata.severity,
            "reviewer_label": metadata.reviewer_label,
            "reviewer_explanation": metadata.reviewer_explanation,
            "remediation_hint": metadata.remediation_hint,
            "affected_artifacts": metadata.affected_artifacts,
        }
        for reason, metadata in sorted(
            taxonomy.REVIEWER_FAILURE_REASON_METADATA.items()
        )
    ]


def test_generated_failure_reason_catalog_markdown_contains_taxonomy() -> None:
    """Generated Markdown catalog must include every stable reason code."""
    from scripts.demo.generate_reviewer_failure_reason_catalog import (
        build_catalog,
        render_markdown,
    )

    markdown = render_markdown(build_catalog())

    for reason in taxonomy.REVIEWER_FAILURE_REASONS:
        assert f"| {reason} |" in markdown


def test_generated_failure_reason_catalog_values_are_allowlisted() -> None:
    """Generated catalog facets must stay in taxonomy allowlists."""
    from scripts.demo.generate_reviewer_failure_reason_catalog import (
        build_catalog,
    )

    for entry in build_catalog()["reasons"]:
        assert entry["category"] in taxonomy.REVIEWER_FAILURE_REASON_CATEGORIES
        assert entry["severity"] in taxonomy.REVIEWER_FAILURE_REASON_SEVERITIES
