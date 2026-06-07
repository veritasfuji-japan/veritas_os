#!/usr/bin/env python3
"""Validate Evaluation Governance sample bundle artifacts locally.

This helper is intentionally local/offline and schema-shape only. It does not
connect to runtime paths, dereference artifact references, verify cryptographic
hash correctness, or enforce governance behavior.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_DIR = (
    REPO_ROOT
    / "docs/en/demo/examples/evaluation-governance-sample-bundle-v1"
)
SCHEMA_DIR = REPO_ROOT / "docs/en/demo/schemas"
DATE_TIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$"
)
SAMPLE_SCHEMA_PAIRS = [
    (
        "root-authority-manifest.example.json",
        "root-authority-manifest-v1.schema.json",
    ),
    (
        "evaluation-function-manifest.example.json",
        "evaluation-function-manifest-v1.schema.json",
    ),
    (
        "manifest-change-receipt.example.json",
        "manifest-change-receipt-v1.schema.json",
    ),
    (
        "evaluation-receipt.example.json",
        "evaluation-receipt-v1.schema.json",
    ),
    (
        "outcome-delta-attribution.example.json",
        "outcome-delta-attribution-v1.schema.json",
    ),
    (
        "evaluation-drift-detection.example.json",
        "evaluation-drift-detection-v1.schema.json",
    ),
    (
        "trajectory-admissibility-monitor.example.json",
        "trajectory-admissibility-monitor-v1.schema.json",
    ),
    (
        "legitimacy-impact-review.example.json",
        "legitimacy-impact-review-v1.schema.json",
    ),
]


@dataclass(frozen=True)
class ValidationFailure:
    """A reviewer-facing schema validation failure for one artifact."""

    artifact_path: Path
    schema_path: Path
    message: str


@dataclass(frozen=True)
class ValidationResult:
    """Structured result returned by the sample bundle validator."""

    total_count: int
    passed_count: int
    failures: tuple[ValidationFailure, ...]


def _jsonschema_module() -> Any | None:
    """Return the optional jsonschema module when it is locally available."""
    try:
        import jsonschema
    except ImportError:
        return None
    return jsonschema


def _load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object from a local path."""
    if not path.is_file():
        raise FileNotFoundError(f"missing file: {_display_path(path)}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        message = f"invalid JSON in {_display_path(path)}: {exc}"
        raise ValueError(message) from exc

    if not isinstance(payload, dict):
        raise TypeError(f"expected JSON object in {_display_path(path)}")
    return payload


def _resolve_ref(ref: str, root_schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve a local JSON Schema reference within the loaded schema."""
    if not ref.startswith("#/"):
        raise ValueError(f"unsupported external schema ref: {ref}")

    current: Any = root_schema
    for part in ref[2:].split("/"):
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"unresolvable schema ref: {ref}")
        current = current[part]
    if not isinstance(current, dict):
        raise ValueError(f"schema ref does not resolve to an object: {ref}")
    return current


def _validate_with_local_subset(
    payload: Any,
    schema: dict[str, Any],
    root_schema: dict[str, Any],
    path: str = "$",
) -> None:
    """Validate the checked-in examples with a deterministic local subset.

    This fallback is used only when jsonschema is unavailable. It covers the
    schema constructs used by the Evaluation Governance sample schemas and does
    not dereference external artifact references.
    """
    if "$ref" in schema:
        _validate_with_local_subset(
            payload,
            _resolve_ref(str(schema["$ref"]), root_schema),
            root_schema,
            path,
        )
        return

    if "const" in schema and payload != schema["const"]:
        raise ValueError(f"{path} did not match const {schema['const']!r}")
    if "enum" in schema and payload not in schema["enum"]:
        raise ValueError(f"{path} did not match enum {schema['enum']!r}")

    expected_type = schema.get("type")
    if expected_type == "object":
        _validate_object(payload, schema, root_schema, path)
    elif expected_type == "array":
        _validate_array(payload, schema, root_schema, path)
    elif expected_type == "string":
        _validate_string(payload, schema, path)
    elif expected_type == "boolean" and not isinstance(payload, bool):
        raise TypeError(f"{path} is not a boolean")
    elif expected_type == "integer":
        _validate_integer(payload, schema, path)


def _validate_object(
    payload: Any,
    schema: dict[str, Any],
    root_schema: dict[str, Any],
    path: str,
) -> None:
    """Validate object constructs used by the sample schemas."""
    if not isinstance(payload, dict):
        raise TypeError(f"{path} is not an object")

    required = schema.get("required", [])
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"{path} missing required fields: {missing}")

    properties = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        extra = set(payload) - set(properties)
        if extra:
            raise ValueError(f"{path} has unexpected fields: {sorted(extra)}")

    for field, value in payload.items():
        if field in properties:
            _validate_with_local_subset(
                value,
                properties[field],
                root_schema,
                f"{path}.{field}",
            )


def _validate_array(
    payload: Any,
    schema: dict[str, Any],
    root_schema: dict[str, Any],
    path: str,
) -> None:
    """Validate array constructs used by the sample schemas."""
    if not isinstance(payload, list):
        raise TypeError(f"{path} is not an array")

    min_items = schema.get("minItems")
    if min_items is not None and len(payload) < min_items:
        raise ValueError(f"{path} has too few items")

    if schema.get("uniqueItems"):
        serialized = [json.dumps(item, sort_keys=True) for item in payload]
        if len(serialized) != len(set(serialized)):
            raise ValueError(f"{path} has duplicate items")

    item_schema = schema.get("items")
    if item_schema is not None:
        for index, item in enumerate(payload):
            _validate_with_local_subset(
                item,
                item_schema,
                root_schema,
                f"{path}[{index}]",
            )


def _validate_string(payload: Any, schema: dict[str, Any], path: str) -> None:
    """Validate string constructs used by the sample schemas."""
    if not isinstance(payload, str):
        raise TypeError(f"{path} is not a string")

    min_length = schema.get("minLength")
    if min_length is not None and len(payload) < min_length:
        raise ValueError(f"{path} is too short")

    pattern = schema.get("pattern")
    if pattern is not None and re.match(pattern, payload) is None:
        raise ValueError(f"{path} does not match pattern {pattern!r}")

    is_date_time = schema.get("format") == "date-time"
    if is_date_time and DATE_TIME_PATTERN.match(payload) is None:
        raise ValueError(f"{path} is not date-time shaped")


def _validate_integer(payload: Any, schema: dict[str, Any], path: str) -> None:
    """Validate integer constructs used by the sample schemas."""
    if not isinstance(payload, int):
        raise TypeError(f"{path} is not an integer")

    minimum = schema.get("minimum")
    if minimum is not None and payload < minimum:
        raise ValueError(f"{path} is below minimum {minimum}")


def _validate_payload(payload: dict[str, Any], schema: dict[str, Any]) -> None:
    """Validate one artifact payload against its matching schema."""
    jsonschema = _jsonschema_module()
    if jsonschema is None:
        _validate_with_local_subset(payload, schema, schema)
        return

    validator = jsonschema.Draft202012Validator(schema)
    validator.validate(payload)


def _display_path(path: Path) -> str:
    """Return a stable repository-relative path when possible."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def validate_bundle() -> ValidationResult:
    """Validate all Evaluation Governance sample artifacts against schemas."""
    failures: list[ValidationFailure] = []

    for artifact_name, schema_name in SAMPLE_SCHEMA_PAIRS:
        artifact_path = BUNDLE_DIR / artifact_name
        schema_path = SCHEMA_DIR / schema_name
        try:
            artifact = _load_json_object(artifact_path)
            schema = _load_json_object(schema_path)
            _validate_payload(artifact, schema)
        except Exception as exc:  # noqa: BLE001
            # Convert artifact-specific validation errors into report entries.
            failures.append(
                ValidationFailure(
                    artifact_path=artifact_path,
                    schema_path=schema_path,
                    message=str(exc),
                )
            )

    return ValidationResult(
        total_count=len(SAMPLE_SCHEMA_PAIRS),
        passed_count=len(SAMPLE_SCHEMA_PAIRS) - len(failures),
        failures=tuple(failures),
    )


def _print_report(result: ValidationResult) -> None:
    """Print a concise reviewer-friendly validation report."""
    failures_by_artifact = {
        failure.artifact_path.name: failure for failure in result.failures
    }

    print("Evaluation Governance Sample Bundle Validation")
    print()
    for artifact_name, _schema_name in SAMPLE_SCHEMA_PAIRS:
        failure = failures_by_artifact.get(artifact_name)
        if failure is None:
            print(f"PASS {artifact_name}")
            continue
        print(f"FAIL {artifact_name}")
        print(f"  Schema: {_display_path(failure.schema_path)}")
        print(f"  Error: {failure.message}")
    print()
    print(f"Validated {result.passed_count} / {result.total_count} artifacts.")


def main() -> int:
    """Run the sample bundle validator and return a process exit code."""
    result = validate_bundle()
    _print_report(result)
    if result.failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
