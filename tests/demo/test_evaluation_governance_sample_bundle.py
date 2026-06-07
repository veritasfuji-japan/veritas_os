import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

BUNDLE_DIR = Path(
    "docs/en/demo/examples/evaluation-governance-sample-bundle-v1"
)
SCHEMA_DIR = Path("docs/en/demo/schemas")

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

DATE_TIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$"
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonschema_module() -> Any | None:
    if importlib.util.find_spec("jsonschema") is None:
        return None
    import jsonschema

    return jsonschema


def _resolve_ref(ref: str, root_schema: dict[str, Any]) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise AssertionError(f"unsupported external schema ref: {ref}")

    current: Any = root_schema
    for part in ref[2:].split("/"):
        current = current[part]
    assert isinstance(current, dict)
    return current


def _validate_with_local_subset(
    payload: Any,
    schema: dict[str, Any],
    root_schema: dict[str, Any],
    path: str = "$",
) -> None:
    if "$ref" in schema:
        _validate_with_local_subset(
            payload,
            _resolve_ref(schema["$ref"], root_schema),
            root_schema,
            path,
        )
        return

    if "const" in schema:
        assert payload == schema["const"], f"{path} did not match const"
    if "enum" in schema:
        assert payload in schema["enum"], f"{path} did not match enum"

    expected_type = schema.get("type")
    if expected_type == "object":
        assert isinstance(payload, dict), f"{path} is not an object"
        required = schema.get("required", [])
        missing = [field for field in required if field not in payload]
        assert not missing, f"{path} missing required fields: {missing}"

        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = set(payload) - set(properties)
            assert not extra, f"{path} has unexpected fields: {sorted(extra)}"

        for field, value in payload.items():
            if field in properties:
                _validate_with_local_subset(
                    value,
                    properties[field],
                    root_schema,
                    f"{path}.{field}",
                )
    elif expected_type == "array":
        assert isinstance(payload, list), f"{path} is not an array"
        min_items = schema.get("minItems")
        if min_items is not None:
            assert len(payload) >= min_items, f"{path} has too few items"
        if schema.get("uniqueItems"):
            serialized = [json.dumps(item, sort_keys=True) for item in payload]
            assert len(serialized) == len(set(serialized)), (
                f"{path} has duplicate items"
            )
        if "items" in schema:
            for index, item in enumerate(payload):
                _validate_with_local_subset(
                    item,
                    schema["items"],
                    root_schema,
                    f"{path}[{index}]",
                )
    elif expected_type == "string":
        assert isinstance(payload, str), f"{path} is not a string"
        min_length = schema.get("minLength")
        if min_length is not None:
            assert len(payload) >= min_length, f"{path} is too short"
        pattern = schema.get("pattern")
        if pattern is not None:
            assert re.match(pattern, payload), f"{path} does not match pattern"
        if schema.get("format") == "date-time":
            assert DATE_TIME_RE.match(payload), f"{path} is not date-time shaped"
    elif expected_type == "boolean":
        assert isinstance(payload, bool), f"{path} is not a boolean"
    elif expected_type == "integer":
        assert isinstance(payload, int), f"{path} is not an integer"
        minimum = schema.get("minimum")
        if minimum is not None:
            assert payload >= minimum, f"{path} is below minimum"


def _validate_sample(payload: dict[str, Any], schema: dict[str, Any]) -> None:
    jsonschema = _jsonschema_module()
    if jsonschema is not None:
        validator = jsonschema.Draft202012Validator(schema)
        validator.validate(payload)
        return

    _validate_with_local_subset(payload, schema, schema)


def test_sample_bundle_readme_exists() -> None:
    assert (BUNDLE_DIR / "README.md").is_file()


@pytest.mark.parametrize(("sample_name", "schema_name"), SAMPLE_SCHEMA_PAIRS)
def test_sample_json_artifacts_validate_against_schemas(
    sample_name: str,
    schema_name: str,
) -> None:
    sample = _load_json(BUNDLE_DIR / sample_name)
    schema = _load_json(SCHEMA_DIR / schema_name)

    assert isinstance(sample, dict)
    _validate_sample(sample, schema)


def test_all_bundled_json_files_are_covered_by_schema_validation() -> None:
    expected_files = {sample_name for sample_name, _schema_name in SAMPLE_SCHEMA_PAIRS}
    bundled_files = {path.name for path in BUNDLE_DIR.glob("*.json")}

    assert bundled_files == expected_files
