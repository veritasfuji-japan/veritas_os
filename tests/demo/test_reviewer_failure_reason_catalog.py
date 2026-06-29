"""Tests for reviewer failure reason catalog validation."""

from __future__ import annotations

import copy
import json
import re

import pytest

from scripts.demo import reviewer_failure_reasons as taxonomy
from scripts.demo.generate_reviewer_failure_reason_catalog import (
    JSON_OUTPUT_PATH,
    MARKDOWN_OUTPUT_PATH,
    build_catalog,
    render_json,
    render_markdown,
)
from scripts.demo.validate_reviewer_failure_reason_catalog import (
    CatalogValidationError,
    SCHEMA_PATH,
    _load_json_object,
    _sha256_file,
    _validate_schema_subset,
    build_failure_reason_catalog_provenance,
    main,
    validate_catalog_payload,
    validate_catalog_files,
)

SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def _catalog_with_json_shapes() -> dict[str, object]:
    """Return generated catalog with JSON list shapes for helper tests."""
    return json.loads(render_json(build_catalog()))


def test_checked_in_catalog_json_passes_schema_validation() -> None:
    """Checked-in catalog JSON must satisfy the local schema contract."""
    schema = _load_json_object(SCHEMA_PATH)
    catalog = _load_json_object(JSON_OUTPUT_PATH)

    _validate_schema_subset(catalog, schema)


def test_catalog_validator_succeeds_on_current_generated_artifacts() -> None:
    """CI-facing validator must pass for checked-in generated artifacts."""
    assert main([]) == 0


def test_catalog_provenance_includes_artifact_hashes() -> None:
    """Catalog provenance must identify all local explanation artifacts."""
    provenance = build_failure_reason_catalog_provenance()

    for field in (
        "catalog_json_sha256",
        "catalog_markdown_sha256",
        "catalog_schema_sha256",
    ):
        assert SHA256_HEX_RE.fullmatch(provenance[field])
    assert provenance["total_reasons"] == len(taxonomy.REVIEWER_FAILURE_REASONS)
    assert provenance["catalog_json_path"].endswith(JSON_OUTPUT_PATH.name)


def test_catalog_json_hash_changes_for_temp_content(tmp_path) -> None:
    """Local SHA-256 provenance changes when catalog JSON bytes change."""
    catalog_copy = tmp_path / JSON_OUTPUT_PATH.name
    catalog_copy.write_text(
        JSON_OUTPUT_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    original_hash = _sha256_file(catalog_copy)
    catalog_copy.write_text(
        JSON_OUTPUT_PATH.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    assert _sha256_file(catalog_copy) != original_hash


def test_stale_catalog_file_fails_validator(tmp_path, monkeypatch) -> None:
    """Catalog provenance remains gated by the deterministic validator."""
    stale_json = tmp_path / JSON_OUTPUT_PATH.name
    stale_json.write_text(
        JSON_OUTPUT_PATH.read_text(encoding="utf-8").replace(
            '"total_reasons":', '"total_reasons_stale":', 1
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "scripts.demo.validate_reviewer_failure_reason_catalog.JSON_OUTPUT_PATH",
        stale_json,
    )

    with pytest.raises(CatalogValidationError):
        validate_catalog_files()


def test_generated_json_matches_metadata_source_of_truth() -> None:
    """Generated JSON must exactly match reviewer metadata source data."""
    catalog = _catalog_with_json_shapes()
    markdown = render_markdown(build_catalog())

    validate_catalog_payload(catalog, markdown)
    assert JSON_OUTPUT_PATH.read_text(encoding="utf-8") == render_json(
        build_catalog()
    )


def test_generated_markdown_contains_every_taxonomy_reason() -> None:
    """Generated Markdown must include every stable taxonomy reason."""
    markdown = MARKDOWN_OUTPUT_PATH.read_text(encoding="utf-8")

    for reason in taxonomy.REVIEWER_FAILURE_REASONS:
        assert reason in markdown


def test_missing_taxonomy_reason_fails_deterministically() -> None:
    """Catalog validation must reject missing taxonomy reasons."""
    catalog = _catalog_with_json_shapes()
    removed = catalog["reasons"].pop()
    markdown = render_markdown(build_catalog())

    with pytest.raises(CatalogValidationError, match="missing taxonomy"):
        validate_catalog_payload(catalog, markdown)
    assert removed["reason"] in taxonomy.REVIEWER_FAILURE_REASONS


def test_unknown_catalog_reason_fails_deterministically() -> None:
    """Catalog validation must reject reason codes outside taxonomy."""
    catalog = _catalog_with_json_shapes()
    catalog["reasons"][0] = copy.deepcopy(catalog["reasons"][0])
    catalog["reasons"][0]["reason"] = "not_a_taxonomy_reason"
    catalog["reasons"] = sorted(
        catalog["reasons"], key=lambda item: item["reason"]
    )
    markdown = render_markdown(build_catalog()) + "\nnot_a_taxonomy_reason\n"

    with pytest.raises(CatalogValidationError, match="unknown reasons"):
        validate_catalog_payload(catalog, markdown)


def test_category_outside_allowlist_fails_deterministically() -> None:
    """Catalog validation must reject non-taxonomy categories."""
    catalog = _catalog_with_json_shapes()
    catalog["reasons"][0] = copy.deepcopy(catalog["reasons"][0])
    catalog["reasons"][0]["category"] = "not_allowed"
    markdown = render_markdown(build_catalog())

    with pytest.raises(CatalogValidationError, match="invalid category"):
        validate_catalog_payload(catalog, markdown)


def test_severity_outside_allowlist_fails_deterministically() -> None:
    """Catalog validation must reject non-taxonomy severities."""
    catalog = _catalog_with_json_shapes()
    catalog["reasons"][0] = copy.deepcopy(catalog["reasons"][0])
    catalog["reasons"][0]["severity"] = "not_allowed"
    markdown = render_markdown(build_catalog())

    with pytest.raises(CatalogValidationError, match="invalid severity"):
        validate_catalog_payload(catalog, markdown)


def test_duplicate_reason_entry_fails_deterministically() -> None:
    """Catalog validation must reject duplicate reason entries."""
    catalog = _catalog_with_json_shapes()
    catalog["reasons"][1] = copy.deepcopy(catalog["reasons"][0])
    catalog["reasons"] = sorted(
        catalog["reasons"], key=lambda item: item["reason"]
    )
    markdown = render_markdown(build_catalog())

    with pytest.raises(CatalogValidationError, match="duplicate"):
        validate_catalog_payload(catalog, markdown)
