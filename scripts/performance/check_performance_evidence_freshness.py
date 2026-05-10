"""Check performance evidence artifacts are fresh and structurally valid."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from scripts.performance.export_performance_evidence import OUTPUT_JSON, OUTPUT_MD, write_performance_evidence

FIXED_GENERATED_AT = "1970-01-01T00:00:00+00:00"
REGENERATE_COMMAND = "python -m scripts.performance.export_performance_evidence"


def _read_text_or_error(path: Path) -> tuple[str | None, str | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except OSError as exc:
        return None, f"{path}: {exc.__class__.__name__}"


def _load_json_or_error(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, ValueError) as exc:
        return None, exc.__class__.__name__


def _validate_markdown_structure(markdown_text: str, expected_metric_names: list[str]) -> list[str]:
    reasons: list[str] = []
    required_sections = [
        "# Performance Evidence Artifact",
        "## Scope",
        "## Summary table",
        "## Metrics table",
        "## Interpretation boundaries",
        "## How to regenerate",
    ]
    for section in required_sections:
        if section not in markdown_text:
            reasons.append(f"missing section {section}")
    if REGENERATE_COMMAND not in markdown_text:
        reasons.append("missing regenerate command")
    if "not a production SLA" not in markdown_text:
        reasons.append("missing non-SLA boundary")
    for name in expected_metric_names:
        if f"| {name} |" not in markdown_text:
            reasons.append(f"missing metric row for {name}")
    return reasons


def compare_performance_evidence(
    committed_json: Path,
    committed_md: Path,
    generated_json: Path,
    generated_md: Path,
) -> tuple[list[str], list[str]]:
    stale_files: list[str] = []
    stale_reasons: list[str] = []

    committed_payload, committed_error = _load_json_or_error(committed_json)
    generated_payload, generated_error = _load_json_or_error(generated_json)
    if committed_error:
        stale_files.append(str(committed_json))
        stale_reasons.append(f"{committed_json}: failed to read JSON ({committed_error})")
    if generated_error:
        stale_files.append(str(committed_json))
        stale_reasons.append(
            f"{committed_json}: failed to generate JSON artifact ({generated_error})"
        )

    if committed_error is None and not isinstance(committed_payload, dict):
        stale_files.append(str(committed_json))
        stale_reasons.append(f"{committed_json}: JSON payload must be an object")
        committed_payload = None
    if generated_error is None and not isinstance(generated_payload, dict):
        stale_files.append(str(committed_json))
        stale_reasons.append(
            f"{committed_json}: failed to generate JSON artifact (JSON payload must be an object)"
        )
        generated_payload = None

    expected_metric_names: list[str] = []
    if committed_payload is not None and generated_payload is not None:
        required_fields = {
            "schema_version",
            "generated_at",
            "measurement_mode",
            "metrics",
            "status",
            "interpretation_boundaries",
        }
        for field in sorted(required_fields):
            if field not in committed_payload:
                stale_files.append(str(committed_json))
                stale_reasons.append(f"{committed_json}: missing required field {field}")

        if committed_payload.get("schema_version") != "performance_evidence.v1":
            stale_files.append(str(committed_json))
            stale_reasons.append(f"{committed_json}: stale schema_version")
        if committed_payload.get("measurement_mode") != generated_payload.get("measurement_mode"):
            stale_files.append(str(committed_json))
            stale_reasons.append(
                f"{committed_json}: measurement_mode differs from deterministic fixture"
            )

        committed_metrics = committed_payload.get("metrics", [])
        generated_metrics = generated_payload.get("metrics", [])
        committed_names = [m.get("name") for m in committed_metrics if isinstance(m, dict)]
        generated_names = [m.get("name") for m in generated_metrics if isinstance(m, dict)]
        expected_metric_names = committed_names
        if committed_names != generated_names:
            stale_files.append(str(committed_json))
            stale_reasons.append(f"{committed_json}: metric names/order differ")

    committed_md_text, committed_md_error = _read_text_or_error(committed_md)
    generated_md_text, generated_md_error = _read_text_or_error(generated_md)
    if committed_md_error:
        stale_files.append(str(committed_md))
        stale_reasons.append(committed_md_error)
    if generated_md_error:
        stale_files.append(str(committed_md))
        stale_reasons.append(
            f"{committed_md}: failed to generate markdown artifact "
            f"({generated_md_error.split(': ', maxsplit=1)[-1]})"
        )

    if committed_md_text is not None:
        for reason in _validate_markdown_structure(committed_md_text, expected_metric_names):
            stale_files.append(str(committed_md))
            stale_reasons.append(f"{committed_md}: {reason}")
    if generated_md_text is not None and generated_payload is not None:
        generated_names = [
            metric.get("name")
            for metric in generated_payload.get("metrics", [])
            if isinstance(metric, dict)
        ]
        for reason in _validate_markdown_structure(generated_md_text, generated_names):
            stale_files.append(str(committed_md))
            stale_reasons.append(
                f"{committed_md}: failed to generate markdown artifact ({reason})"
            )

    return sorted(set(stale_files)), sorted(set(stale_reasons))


def check_performance_evidence_freshness(
    committed_json: Path = OUTPUT_JSON,
    committed_md: Path = OUTPUT_MD,
) -> int:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        generated_json = root / committed_json.name
        generated_md = root / committed_md.name
        write_performance_evidence(
            generated_json,
            generated_md,
            generated_at=FIXED_GENERATED_AT,
            sample_count=3,
            warmup_count=0,
            deterministic_fixture=True,
        )
        stale_files, stale_reasons = compare_performance_evidence(
            committed_json=committed_json,
            committed_md=committed_md,
            generated_json=generated_json,
            generated_md=generated_md,
        )

    if stale_files:
        print("Performance evidence artifacts are stale.")
        print("Changed files:")
        for file_path in stale_files:
            print(f"- {file_path}")
        print("Reasons:")
        for reason in stale_reasons:
            print(f"- {reason}")
        print(f"Regenerate with: {REGENERATE_COMMAND}")
        return 1

    print("Performance evidence artifacts are fresh.")
    return 0


if __name__ == "__main__":
    raise SystemExit(check_performance_evidence_freshness())
