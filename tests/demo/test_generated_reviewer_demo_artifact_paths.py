"""Regression tests for portable reviewer-facing generated artifact paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

GENERATED_REVIEWER_DEMO_DIR = Path(
    "docs/en/demo/examples/evaluation-governance-reviewer-demo-v1/generated"
)
HOST_SPECIFIC_PREFIXES = (
    "/workspace/",
    "/home/runner/",
    "/tmp/",
    "C:\\\\",
)
PATH_FIELD_NAMES = {
    "input_dir",
    "output_dir",
    "artifact_ref",
    "source_path",
    "generated_from",
}


def _walk_path_fields(payload: Any, field_name: str | None = None) -> list[str]:
    """Collect string values from reviewer path-bearing JSON fields."""
    if isinstance(payload, dict):
        values: list[str] = []
        for key, value in payload.items():
            values.extend(_walk_path_fields(value, key))
        return values
    if isinstance(payload, list):
        values = []
        for item in payload:
            values.extend(_walk_path_fields(item, field_name))
        return values
    if isinstance(payload, str) and field_name in PATH_FIELD_NAMES:
        return [payload]
    return []


def test_generated_reviewer_demo_artifact_paths_are_portable() -> None:
    generated_files = sorted(GENERATED_REVIEWER_DEMO_DIR.glob("*.json"))
    assert generated_files, "expected committed reviewer demo JSON artifacts"

    violations: list[str] = []
    for generated_file in generated_files:
        payload = json.loads(generated_file.read_text(encoding="utf-8"))
        for value in _walk_path_fields(payload):
            if any(prefix in value for prefix in HOST_SPECIFIC_PREFIXES):
                violations.append(f"{generated_file}: {value}")
            if "\\" in value:
                violations.append(f"{generated_file}: {value}")

    assert violations == []
