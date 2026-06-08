#!/usr/bin/env python3
"""Validate generated Evaluation Governance reviewer demo outputs.

This helper is intentionally local/offline, non-runtime, and non-enforcing. It
checks expected reviewer demo files, schema shape, safety-boundary fields, and
Reviewer Evidence Packet Evaluation Governance attachments without calling
``/v1/decide``, dereferencing artifact references, using network access, or
modifying files.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "docs/en/demo/schemas"
SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
DATE_TIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$"
)

EXPECTED_FILE_NAMES = [
    "outcome-delta-attribution-1.generated.example.json",
    "outcome-delta-attribution-2.generated.example.json",
    "evaluation-drift-detection-1.generated.example.json",
    "evaluation-drift-detection-2.generated.example.json",
    "trajectory-admissibility-monitor.generated.example.json",
    "legitimacy-impact-review.generated.example.json",
    "chain-manifest.generated.example.json",
    "reviewer-evidence-packet.generated.example.json",
    "demo-summary.generated.example.json",
]

SCHEMA_FILE_NAMES_BY_ARTIFACT = {
    "outcome-delta-attribution-1.generated.example.json": (
        "outcome-delta-attribution-v1.schema.json"
    ),
    "outcome-delta-attribution-2.generated.example.json": (
        "outcome-delta-attribution-v1.schema.json"
    ),
    "evaluation-drift-detection-1.generated.example.json": (
        "evaluation-drift-detection-v1.schema.json"
    ),
    "evaluation-drift-detection-2.generated.example.json": (
        "evaluation-drift-detection-v1.schema.json"
    ),
    "trajectory-admissibility-monitor.generated.example.json": (
        "trajectory-admissibility-monitor-v1.schema.json"
    ),
    "legitimacy-impact-review.generated.example.json": (
        "legitimacy-impact-review-v1.schema.json"
    ),
    "reviewer-evidence-packet.generated.example.json": (
        "reviewer-evidence-packet-v1.schema.json"
    ),
}

CHAIN_SCHEMA_VERSION = "evaluation-governance-offline-chain-manifest-v1"
DEMO_SUMMARY_SCHEMA_VERSION = "evaluation-governance-reviewer-demo-summary-v1"
CHAIN_NON_GOALS = {
    "does_not_change_runtime_behavior",
    "does_not_establish_legitimacy",
    "does_not_certify_compliance",
    "does_not_call_v1_decide",
    "does_not_dereference_artifact_refs",
}
DEMO_SUMMARY_NON_GOALS = {
    "does_not_change_runtime_behavior",
    "does_not_call_v1_decide",
    "does_not_establish_legitimacy",
    "does_not_certify_compliance",
    "does_not_dereference_external_artifact_refs",
    "does_not_require_network_access",
}
EXPECTED_ATTACHMENT_TYPES = {
    "evaluation_receipt",
    "manifest_change_receipt",
    "outcome_delta_attribution",
    "evaluation_drift_detection",
    "trajectory_admissibility_monitor",
    "legitimacy_impact_review",
}


@dataclass(frozen=True)
class ReviewerDemoValidationResult:
    """Structured result returned by the reviewer demo validator."""

    demo_dir: Path
    expected_files_count: int
    schema_validated_count: int
    reviewer_attachment_count: int


class ReviewerDemoValidationError(ValueError):
    """Reviewer-facing validation error with an associated local file path."""

    def __init__(self, check: str, path: Path, message: str) -> None:
        super().__init__(message)
        self.check = check
        self.path = path
        self.message = message


def _jsonschema_module() -> Any | None:
    """Return the optional jsonschema module when installed locally."""
    if importlib.util.find_spec("jsonschema") is None:
        return None

    import jsonschema

    return jsonschema


def _display_path(path: Path) -> str:
    """Return a stable repository-relative path when possible."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_json(path: Path) -> dict[str, Any]:
    """Load a local JSON object without dereferencing artifact references."""
    if not path.is_file():
        raise FileNotFoundError(f"missing JSON file: {_display_path(path)}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {_display_path(path)}: {exc}") from exc

    if not isinstance(payload, dict):
        raise TypeError(f"expected JSON object in {_display_path(path)}")
    return payload


def _resolve_ref(ref: str, root_schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve a local JSON Schema reference within ``root_schema``."""
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


def _json_type_matches(payload: Any, expected_type: str) -> bool:
    """Return whether ``payload`` matches a JSON Schema primitive type."""
    if expected_type == "object":
        return isinstance(payload, dict)
    if expected_type == "array":
        return isinstance(payload, list)
    if expected_type == "string":
        return isinstance(payload, str)
    if expected_type == "boolean":
        return isinstance(payload, bool)
    if expected_type == "integer":
        return isinstance(payload, int) and not isinstance(payload, bool)
    if expected_type == "number":
        return isinstance(payload, (int, float)) and not isinstance(payload, bool)
    if expected_type == "null":
        return payload is None
    raise ValueError(f"unsupported schema type: {expected_type}")


def _validate_schema_subset(
    payload: Any,
    schema: dict[str, Any],
    root_schema: dict[str, Any],
    path: str = "$",
) -> None:
    """Validate schema constructs used by the reviewer demo schemas locally."""
    if "$ref" in schema:
        _validate_schema_subset(
            payload,
            _resolve_ref(str(schema["$ref"]), root_schema),
            root_schema,
            path,
        )
        return

    if "anyOf" in schema:
        errors = []
        for option in schema["anyOf"]:
            try:
                _validate_schema_subset(payload, option, root_schema, path)
                return
            except (TypeError, ValueError) as exc:
                errors.append(str(exc))
        raise ValueError(f"{path} did not match any allowed schema: {errors}")

    if "const" in schema and payload != schema["const"]:
        raise ValueError(f"{path} did not match const {schema['const']!r}")
    if "enum" in schema and payload not in schema["enum"]:
        raise ValueError(f"{path} did not match enum {schema['enum']!r}")

    expected_type = schema.get("type")
    if isinstance(expected_type, list):
        if not any(_json_type_matches(payload, item) for item in expected_type):
            raise TypeError(f"{path} is not one of {expected_type}")
        if payload is None:
            return
    elif isinstance(expected_type, str):
        if not _json_type_matches(payload, expected_type):
            raise TypeError(f"{path} is not a {expected_type}")

    if isinstance(payload, dict):
        _validate_schema_object(payload, schema, root_schema, path)
    elif isinstance(payload, list):
        _validate_schema_array(payload, schema, root_schema, path)
    elif isinstance(payload, str):
        _validate_schema_string(payload, schema, path)
    elif isinstance(payload, int) and not isinstance(payload, bool):
        _validate_schema_number(payload, schema, path)


def _validate_schema_object(
    payload: dict[str, Any],
    schema: dict[str, Any],
    root_schema: dict[str, Any],
    path: str,
) -> None:
    """Validate JSON Schema object constraints used by demo schemas."""
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
            _validate_schema_subset(
                value,
                properties[field],
                root_schema,
                f"{path}.{field}",
            )


def _validate_schema_array(
    payload: list[Any],
    schema: dict[str, Any],
    root_schema: dict[str, Any],
    path: str,
) -> None:
    """Validate JSON Schema array constraints used by demo schemas."""
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
            _validate_schema_subset(
                item,
                item_schema,
                root_schema,
                f"{path}[{index}]",
            )


def _validate_schema_string(
    payload: str, schema: dict[str, Any], path: str
) -> None:
    """Validate JSON Schema string constraints used by demo schemas."""
    min_length = schema.get("minLength")
    if min_length is not None and len(payload) < min_length:
        raise ValueError(f"{path} is too short")

    pattern = schema.get("pattern")
    if pattern is not None and re.match(pattern, payload) is None:
        raise ValueError(f"{path} does not match pattern {pattern!r}")

    is_date_time = schema.get("format") == "date-time"
    if is_date_time and DATE_TIME_PATTERN.match(payload) is None:
        raise ValueError(f"{path} is not date-time shaped")


def _validate_schema_number(
    payload: int | float, schema: dict[str, Any], path: str
) -> None:
    """Validate JSON Schema numeric constraints used by demo schemas."""
    minimum = schema.get("minimum")
    if minimum is not None and payload < minimum:
        raise ValueError(f"{path} is below minimum {minimum}")
    maximum = schema.get("maximum")
    if maximum is not None and payload > maximum:
        raise ValueError(f"{path} is above maximum {maximum}")


def validate_schema_if_available(artifact_path: Path, schema_path: Path) -> None:
    """Validate ``artifact_path`` against ``schema_path`` locally.

    The function prefers ``jsonschema`` when available. If it is not installed,
    a deterministic local subset covering the checked-in Evaluation Governance
    demo schemas is used instead. External schema refs are rejected.
    """
    artifact = load_json(artifact_path)
    schema = load_json(schema_path)
    jsonschema = _jsonschema_module()
    if jsonschema is not None:
        jsonschema.Draft202012Validator(schema).validate(artifact)
        return

    _validate_schema_subset(artifact, schema, schema)


def validate_sha256_shape(value: Any, path: Path, field_path: str) -> None:
    """Validate that ``value`` is shaped as a lowercase SHA-256 hex digest."""
    if not isinstance(value, str) or SHA256_HEX_PATTERN.fullmatch(value) is None:
        raise ReviewerDemoValidationError(
            "sha256 shape",
            path,
            f"{field_path} must be a lowercase sha256 hex string",
        )


def validate_expected_files(demo_dir: Path) -> int:
    """Require every expected generated reviewer demo file to be present."""
    missing = [
        name for name in EXPECTED_FILE_NAMES if not (demo_dir / name).is_file()
    ]
    if missing:
        raise ReviewerDemoValidationError(
            "expected files present",
            demo_dir / missing[0],
            f"missing expected file(s): {', '.join(missing)}",
        )
    return len(EXPECTED_FILE_NAMES)


def _require_string(payload: dict[str, Any], field: str, path: Path) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ReviewerDemoValidationError(
            "required shape",
            path,
            f"{field} must be a non-empty string",
        )
    return value


def _require_true(payload: dict[str, Any], field: str, path: Path, check: str) -> None:
    if payload.get(field) is not True:
        raise ReviewerDemoValidationError(check, path, f"{field} must be true")


def _require_non_goals(
    payload: dict[str, Any], required_non_goals: set[str], path: Path, check: str
) -> None:
    non_goals = payload.get("non_goals")
    if not isinstance(non_goals, list) or not all(
        isinstance(item, str) for item in non_goals
    ):
        raise ReviewerDemoValidationError(
            check,
            path,
            "non_goals must be an array of strings",
        )
    missing = sorted(required_non_goals - set(non_goals))
    if missing:
        raise ReviewerDemoValidationError(
            check,
            path,
            f"non_goals missing safety boundaries: {', '.join(missing)}",
        )


def validate_chain_manifest(path: Path) -> None:
    """Validate the chain manifest shape and non-runtime safety boundaries."""
    manifest = load_json(path)
    if manifest.get("schema_version") != CHAIN_SCHEMA_VERSION:
        raise ReviewerDemoValidationError(
            "chain manifest safety boundaries",
            path,
            f"schema_version must be {CHAIN_SCHEMA_VERSION}",
        )
    _require_string(manifest, "chain_id", path)
    _require_string(manifest, "issued_at", path)
    _require_true(manifest, "non_runtime", path, "chain manifest safety boundaries")
    _require_true(manifest, "non_enforcing", path, "chain manifest safety boundaries")
    _require_non_goals(
        manifest,
        CHAIN_NON_GOALS,
        path,
        "chain manifest safety boundaries",
    )

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ReviewerDemoValidationError(
            "chain manifest safety boundaries",
            path,
            "artifacts must be a non-empty array",
        )
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise ReviewerDemoValidationError(
                "chain manifest safety boundaries",
                path,
                f"artifacts[{index}] must be an object",
            )
        _require_string(artifact, "artifact_type", path)
        _require_string(artifact, "artifact_ref", path)
        validate_sha256_shape(
            artifact.get("artifact_hash"),
            path,
            f"artifacts[{index}].artifact_hash",
        )


def validate_demo_summary(path: Path) -> None:
    """Validate the demo summary shape and non-runtime safety boundaries."""
    summary = load_json(path)
    if summary.get("schema_version") != DEMO_SUMMARY_SCHEMA_VERSION:
        raise ReviewerDemoValidationError(
            "demo summary safety boundaries",
            path,
            f"schema_version must be {DEMO_SUMMARY_SCHEMA_VERSION}",
        )
    _require_string(summary, "demo_id", path)
    _require_string(summary, "issued_at", path)
    _require_true(summary, "non_runtime", path, "demo summary safety boundaries")
    _require_true(summary, "non_enforcing", path, "demo summary safety boundaries")
    _require_non_goals(
        summary,
        DEMO_SUMMARY_NON_GOALS,
        path,
        "demo summary safety boundaries",
    )

    artifacts = summary.get("generated_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ReviewerDemoValidationError(
            "demo summary safety boundaries",
            path,
            "generated_artifacts must be a non-empty array",
        )
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise ReviewerDemoValidationError(
                "demo summary safety boundaries",
                path,
                f"generated_artifacts[{index}] must be an object",
            )
        _require_string(artifact, "artifact_type", path)
        _require_string(artifact, "artifact_ref", path)
        validate_sha256_shape(
            artifact.get("artifact_hash"),
            path,
            f"generated_artifacts[{index}].artifact_hash",
        )


def validate_reviewer_packet_attachments(path: Path) -> int:
    """Validate Reviewer Evidence Packet Evaluation Governance attachments."""
    packet = load_json(path)
    artifacts = packet.get("evaluation_governance_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ReviewerDemoValidationError(
            "reviewer evidence packet attachments",
            path,
            "evaluation_governance_artifacts must be a non-empty array",
        )

    artifact_types: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise ReviewerDemoValidationError(
                "reviewer evidence packet attachments",
                path,
                f"evaluation_governance_artifacts[{index}] must be an object",
            )
        artifact_type = _require_string(artifact, "artifact_type", path)
        artifact_types.add(artifact_type)
        _require_string(artifact, "artifact_ref", path)
        _require_string(artifact, "schema_ref", path)
        if artifact.get("required_for_review") is not False:
            raise ReviewerDemoValidationError(
                "reviewer evidence packet attachments",
                path,
                (
                    "evaluation_governance_artifacts"
                    f"[{index}].required_for_review must be false"
                ),
            )
        validate_sha256_shape(
            artifact.get("artifact_hash"),
            path,
            f"evaluation_governance_artifacts[{index}].artifact_hash",
        )

    missing_types = sorted(EXPECTED_ATTACHMENT_TYPES - artifact_types)
    if missing_types:
        raise ReviewerDemoValidationError(
            "reviewer evidence packet attachments",
            path,
            f"missing expected attachment types: {', '.join(missing_types)}",
        )
    return len(artifacts)


def _validate_schemas(demo_dir: Path) -> int:
    """Validate generated artifacts against existing local schemas."""
    for artifact_name, schema_name in SCHEMA_FILE_NAMES_BY_ARTIFACT.items():
        artifact_path = demo_dir / artifact_name
        schema_path = SCHEMA_DIR / schema_name
        try:
            validate_schema_if_available(artifact_path, schema_path)
        except Exception as exc:  # noqa: BLE001
            raise ReviewerDemoValidationError(
                "schema validation",
                artifact_path,
                f"failed against {_display_path(schema_path)}: {exc}",
            ) from exc
    return len(SCHEMA_FILE_NAMES_BY_ARTIFACT)


def validate_reviewer_demo(demo_dir: Path) -> ReviewerDemoValidationResult:
    """Validate a generated Evaluation Governance reviewer demo directory.

    Args:
        demo_dir: Directory containing generated reviewer-facing demo artifacts.

    Returns:
        Counts for the validated expected files, schemas, and reviewer packet
        attachments.

    Raises:
        ReviewerDemoValidationError: If any reviewer-facing validation check
            fails.
        ReviewerDemoValidationError: If ``demo_dir`` does not exist.
    """
    resolved_demo_dir = demo_dir.resolve()
    if not resolved_demo_dir.is_dir():
        raise ReviewerDemoValidationError(
            "demo directory",
            resolved_demo_dir,
            "demo directory does not exist",
        )

    expected_count = validate_expected_files(resolved_demo_dir)
    schema_count = _validate_schemas(resolved_demo_dir)
    validate_chain_manifest(
        resolved_demo_dir / "chain-manifest.generated.example.json"
    )
    attachment_count = validate_reviewer_packet_attachments(
        resolved_demo_dir / "reviewer-evidence-packet.generated.example.json"
    )
    validate_demo_summary(resolved_demo_dir / "demo-summary.generated.example.json")
    return ReviewerDemoValidationResult(
        demo_dir=resolved_demo_dir,
        expected_files_count=expected_count,
        schema_validated_count=schema_count,
        reviewer_attachment_count=attachment_count,
    )


def _print_success_report(result: ReviewerDemoValidationResult) -> None:
    """Print a concise reviewer-friendly success report."""
    print("Evaluation Governance Reviewer Demo Validation")
    print()
    print("PASS expected files present")
    print("PASS schema validation")
    print("PASS chain manifest safety boundaries")
    print("PASS reviewer evidence packet attachments")
    print("PASS demo summary safety boundaries")
    print()
    print(f"Validated reviewer demo output: {result.demo_dir}")


def _print_failure_report(error: ReviewerDemoValidationError) -> None:
    """Print a concise reviewer-friendly failure report."""
    print("Evaluation Governance Reviewer Demo Validation", file=sys.stderr)
    print(f"FAIL {error.check}", file=sys.stderr)
    print(f"File: {_display_path(error.path)}", file=sys.stderr)
    print(f"Error: {error.message}", file=sys.stderr)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the reviewer demo validator."""
    parser = argparse.ArgumentParser(
        description=(
            "Validate a local, non-runtime Evaluation Governance reviewer "
            "demo output directory."
        )
    )
    parser.add_argument(
        "--demo-dir",
        required=True,
        type=Path,
        help="Directory containing generated reviewer demo artifacts.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the reviewer demo validator CLI."""
    args = _parse_args(argv)
    try:
        result = validate_reviewer_demo(args.demo_dir)
    except ReviewerDemoValidationError as exc:
        _print_failure_report(exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        path = args.demo_dir
        error = ReviewerDemoValidationError("validation", path, str(exc))
        _print_failure_report(error)
        return 1

    _print_success_report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
