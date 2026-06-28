#!/usr/bin/env python3
"""Validate reviewer failure reason catalog artifacts locally/offline.

The validator treats the generated JSON and Markdown catalog files as a stable
reviewer documentation contract. It validates schema shape, taxonomy coverage,
metadata fidelity, deterministic sorting, and freshness against the generator.
It does not change runtime admissibility or emitted failure reason strings.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.demo.generate_reviewer_failure_reason_catalog import (  # noqa: E402
    JSON_OUTPUT_PATH,
    MARKDOWN_OUTPUT_PATH,
    build_catalog,
    render_json,
    render_markdown,
)
from scripts.demo.reviewer_failure_reasons import (  # noqa: E402
    REVIEWER_FAILURE_REASON_CATEGORIES,
    REVIEWER_FAILURE_REASON_METADATA,
    REVIEWER_FAILURE_REASON_SEVERITIES,
    REVIEWER_FAILURE_REASONS,
)

SCHEMA_PATH = (
    REPO_ROOT
    / "docs/en/demo/schemas/reviewer-failure-reason-catalog-v1.schema.json"
)


class CatalogValidationError(ValueError):
    """Raised when the checked-in reviewer catalog is invalid."""


def _display_path(path: Path) -> str:
    """Return a stable repository-relative path when possible."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _load_json_object(path: Path) -> dict[str, Any]:
    """Load a local JSON object or raise a deterministic validation error."""
    if not path.is_file():
        raise CatalogValidationError(f"missing file: {_display_path(path)}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        message = f"invalid JSON in {_display_path(path)}: {exc}"
        raise CatalogValidationError(message) from exc
    if not isinstance(payload, dict):
        raise CatalogValidationError(
            f"expected JSON object in {_display_path(path)}"
        )
    return payload


def _validate_schema_subset(
    payload: Any,
    schema: dict[str, Any],
    path: str = "$",
) -> None:
    """Validate catalog JSON with the local JSON Schema subset it uses."""
    if "const" in schema and payload != schema["const"]:
        raise CatalogValidationError(
            f"{path} did not match const {schema['const']!r}"
        )

    expected_type = schema.get("type")
    if expected_type == "object":
        _validate_object(payload, schema, path)
    elif expected_type == "array":
        _validate_array(payload, schema, path)
    elif expected_type == "string":
        _validate_string(payload, schema, path)
    elif expected_type == "integer":
        _validate_integer(payload, schema, path)


def _validate_object(payload: Any, schema: dict[str, Any], path: str) -> None:
    """Validate object keywords used by the catalog schema."""
    if not isinstance(payload, dict):
        raise CatalogValidationError(f"{path} is not an object")

    missing = [
        field for field in schema.get("required", []) if field not in payload
    ]
    if missing:
        raise CatalogValidationError(f"{path} missing required fields: {missing}")

    properties = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        extra = set(payload) - set(properties)
        if extra:
            raise CatalogValidationError(
                f"{path} has unexpected fields: {sorted(extra)}"
            )

    for field, value in payload.items():
        if field in properties:
            _validate_schema_subset(
                value, properties[field], f"{path}.{field}"
            )


def _validate_array(payload: Any, schema: dict[str, Any], path: str) -> None:
    """Validate array keywords used by the catalog schema."""
    if not isinstance(payload, list):
        raise CatalogValidationError(f"{path} is not an array")
    min_items = schema.get("minItems")
    if min_items is not None and len(payload) < min_items:
        raise CatalogValidationError(f"{path} has too few items")
    item_schema = schema.get("items")
    if item_schema is not None:
        for index, item in enumerate(payload):
            _validate_schema_subset(item, item_schema, f"{path}[{index}]")


def _validate_string(payload: Any, schema: dict[str, Any], path: str) -> None:
    """Validate string keywords used by the catalog schema."""
    if not isinstance(payload, str):
        raise CatalogValidationError(f"{path} is not a string")
    min_length = schema.get("minLength")
    if min_length is not None and len(payload) < min_length:
        raise CatalogValidationError(f"{path} is too short")


def _validate_integer(payload: Any, schema: dict[str, Any], path: str) -> None:
    """Validate integer keywords used by the catalog schema."""
    if not isinstance(payload, int) or isinstance(payload, bool):
        raise CatalogValidationError(f"{path} is not an integer")
    minimum = schema.get("minimum")
    if minimum is not None and payload < minimum:
        raise CatalogValidationError(f"{path} is below minimum {minimum}")


def validate_catalog_payload(catalog: dict[str, Any], markdown: str) -> None:
    """Validate catalog content against taxonomy and metadata source of truth."""
    schema = _load_json_object(SCHEMA_PATH)
    _validate_schema_subset(catalog, schema)

    reasons = catalog["reasons"]
    reason_codes = [entry["reason"] for entry in reasons]
    taxonomy_reasons = sorted(REVIEWER_FAILURE_REASONS)

    if catalog["total_reasons"] != len(REVIEWER_FAILURE_REASONS):
        raise CatalogValidationError("total_reasons does not match taxonomy")
    if reason_codes != sorted(reason_codes):
        raise CatalogValidationError("catalog reasons are not sorted")
    if len(reason_codes) != len(set(reason_codes)):
        raise CatalogValidationError("catalog contains duplicate reason entries")

    unknown = sorted(set(reason_codes) - REVIEWER_FAILURE_REASONS)
    if unknown:
        raise CatalogValidationError(f"catalog contains unknown reasons: {unknown}")

    missing = sorted(REVIEWER_FAILURE_REASONS - set(reason_codes))
    if missing:
        raise CatalogValidationError(f"catalog missing taxonomy reasons: {missing}")
    if reason_codes != taxonomy_reasons:
        raise CatalogValidationError("catalog reasons do not match taxonomy order")

    expected_categories = sorted(REVIEWER_FAILURE_REASON_CATEGORIES)
    if catalog["categories"] != expected_categories:
        raise CatalogValidationError("catalog categories do not match taxonomy")

    expected_severities = sorted(REVIEWER_FAILURE_REASON_SEVERITIES)
    if catalog["severities"] != expected_severities:
        raise CatalogValidationError("catalog severities do not match taxonomy")

    for entry in reasons:
        reason = entry["reason"]
        if entry["category"] not in REVIEWER_FAILURE_REASON_CATEGORIES:
            raise CatalogValidationError(f"invalid category for {reason}")
        if entry["severity"] not in REVIEWER_FAILURE_REASON_SEVERITIES:
            raise CatalogValidationError(f"invalid severity for {reason}")
        expected = json.loads(
            json.dumps(asdict(REVIEWER_FAILURE_REASON_METADATA[reason]))
        )
        if entry != expected:
            raise CatalogValidationError(f"metadata mismatch for {reason}")
        if reason not in markdown:
            raise CatalogValidationError(f"Markdown missing reason {reason}")


def validate_catalog_files() -> None:
    """Validate checked-in catalog files and generator freshness."""
    catalog = _load_json_object(JSON_OUTPUT_PATH)
    if not MARKDOWN_OUTPUT_PATH.is_file():
        raise CatalogValidationError(
            f"missing file: {_display_path(MARKDOWN_OUTPUT_PATH)}"
        )
    markdown = MARKDOWN_OUTPUT_PATH.read_text(encoding="utf-8")
    validate_catalog_payload(catalog, markdown)

    expected_catalog = build_catalog()
    expected_json = render_json(expected_catalog)
    if JSON_OUTPUT_PATH.read_text(encoding="utf-8") != expected_json:
        raise CatalogValidationError("generated JSON catalog is stale")
    if markdown != render_markdown(expected_catalog):
        raise CatalogValidationError("generated Markdown catalog is stale")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate reviewer failure reason catalog artifacts."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="accepted for parity; validation is always check-only",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for deterministic local/offline validation."""
    parse_args(argv)
    try:
        validate_catalog_files()
    except CatalogValidationError as exc:
        print(f"Reviewer failure reason catalog validation failed: {exc}")
        return 1
    print("Reviewer failure reason catalog validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
