"""Check freshness of committed performance evidence artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from scripts.performance.export_performance_evidence import (
    FIXED_GENERATED_AT,
    OUTPUT_JSON,
    OUTPUT_MD,
    write_performance_evidence,
)

REGENERATE_COMMAND = "python -m scripts.performance.export_performance_evidence"
EXPECTED_SCHEMA_VERSION = "performance_evidence.v1"
ALLOWED_MEASUREMENT_MODES = ("deterministic_fixture", "not_measured")
REQUIRED_JSON_FIELDS = (
    "schema_version",
    "generated_at",
    "measurement_mode",
    "sample_count",
    "warmup_count",
    "metrics",
    "notes",
)


@dataclass(frozen=True)
class FreshnessResult:
    """Result of freshness verification."""

    fresh: bool
    stale_files: tuple[Path, ...]
    reasons: tuple[str, ...]


def _read_text_or_error(path: Path) -> tuple[str | None, str | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except (OSError, UnicodeDecodeError) as exc:
        return None, exc.__class__.__name__


def _load_json_or_error(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return None, exc.__class__.__name__


def _validate_json_payload(payload: Any, label: str) -> list[str]:
    reasons: list[str] = []
    if not isinstance(payload, dict):
        return [f"{label} JSON payload is not an object"]

    for field in REQUIRED_JSON_FIELDS:
        if field not in payload:
            reasons.append(f"{label} missing required field {field}")

    if (
        "schema_version" in payload
        and payload["schema_version"] != EXPECTED_SCHEMA_VERSION
    ):
        reasons.append(f"{label} schema_version must be {EXPECTED_SCHEMA_VERSION}")
    if "metrics" in payload and not isinstance(payload["metrics"], list):
        reasons.append(f"{label} metrics must be a list")
    if "notes" in payload and not isinstance(payload["notes"], list):
        reasons.append(f"{label} notes must be a list")
    if "sample_count" in payload and not isinstance(payload["sample_count"], int):
        reasons.append(f"{label} sample_count must be an int")
    if "warmup_count" in payload and not isinstance(payload["warmup_count"], int):
        reasons.append(f"{label} warmup_count must be an int")
    if "generated_at" in payload:
        reasons.extend(_validate_generated_at(payload["generated_at"], label))
    if "measurement_mode" in payload:
        reasons.extend(_validate_measurement_mode(payload["measurement_mode"], label))
    return reasons


def _validate_generated_at(value: Any, label: str) -> list[str]:
    if not isinstance(value, str):
        return [f"{label} generated_at must be a string"]

    stripped = value.strip()
    if not stripped:
        return [f"{label} generated_at must be a non-empty ISO-8601 string"]

    try:
        datetime.fromisoformat(stripped.replace("Z", "+00:00"))
    except ValueError:
        return [f"{label} generated_at must be a valid ISO-8601 datetime"]

    return []


def _validate_measurement_mode(value: Any, label: str) -> list[str]:
    if not isinstance(value, str):
        return [f"{label} measurement_mode must be a string"]

    if value not in ALLOWED_MEASUREMENT_MODES:
        allowed = ", ".join(ALLOWED_MEASUREMENT_MODES)
        return [f"{label} measurement_mode must be one of {allowed}"]

    return []


def _validate_markdown_text(text: str, label: str) -> list[str]:
    reasons: list[str] = []
    if not text.endswith("\n"):
        reasons.append(f"{label} markdown trailing newline is invalid")
    if text.endswith("\n\n"):
        reasons.append(f"{label} markdown has double trailing newline")
    if "# Performance Evidence" not in text:
        reasons.append(f"{label} markdown missing '# Performance Evidence'")
    if "## Interpretation boundaries" not in text:
        reasons.append(f"{label} markdown missing '## Interpretation boundaries'")
    if "not a production SLA" not in text:
        reasons.append(f"{label} markdown missing 'not a production SLA'")
    return reasons


def check_performance_evidence_freshness(
    committed_json_path: Path | None = None,
    committed_markdown_path: Path | None = None,
) -> FreshnessResult:
    """Compare committed artifacts with regenerated exporter output."""
    resolved_json = (
        committed_json_path if committed_json_path is not None else OUTPUT_JSON
    )
    resolved_md = (
        committed_markdown_path if committed_markdown_path is not None else OUTPUT_MD
    )

    stale_files: list[Path] = []
    reasons: list[str] = []
    committed_json_valid = False
    generated_json_valid = False
    committed_md_valid = False
    generated_md_valid = False

    committed_json, committed_json_error = _load_json_or_error(resolved_json)
    if committed_json_error is not None:
        stale_files.append(resolved_json)
        reasons.append(f"{resolved_json}: failed to load JSON ({committed_json_error})")
    else:
        committed_json_reasons = _validate_json_payload(committed_json, "committed")
        for reason in committed_json_reasons:
            stale_files.append(resolved_json)
            reasons.append(f"{resolved_json}: {reason}")
        if not committed_json_reasons:
            committed_json_valid = True

    committed_md_text, committed_md_error = _read_text_or_error(resolved_md)
    if committed_md_error is not None:
        stale_files.append(resolved_md)
        reasons.append(f"{resolved_md}: failed to read markdown ({committed_md_error})")
    else:
        committed_md_reasons = _validate_markdown_text(committed_md_text, "committed")
        for reason in committed_md_reasons:
            stale_files.append(resolved_md)
            reasons.append(f"{resolved_md}: {reason}")
        if not committed_md_reasons:
            committed_md_valid = True

    with TemporaryDirectory() as tmp_dir:
        generated_json_path = Path(tmp_dir) / "performance-evidence.latest.json"
        generated_md_path = Path(tmp_dir) / "performance-evidence.latest.md"

        try:
            write_performance_evidence(
                json_path=generated_json_path,
                markdown_path=generated_md_path,
                generated_at=FIXED_GENERATED_AT,
            )
        except Exception as exc:  # noqa: BLE001
            stale_files.append(resolved_json)
            stale_files.append(resolved_md)
            reasons.append(f"failed to generate artifacts ({exc.__class__.__name__})")
            return FreshnessResult(
                fresh=False,
                stale_files=tuple(dict.fromkeys(stale_files)),
                reasons=tuple(reasons),
            )

        generated_json, generated_json_error = _load_json_or_error(generated_json_path)
        if generated_json_error is not None:
            stale_files.append(resolved_json)
            reasons.append(
                f"{resolved_json}: generated JSON invalid ({generated_json_error})"
            )
        else:
            generated_json_reasons = _validate_json_payload(generated_json, "generated")
            for reason in generated_json_reasons:
                stale_files.append(resolved_json)
                reasons.append(f"{resolved_json}: {reason}")
            if not generated_json_reasons:
                generated_json_valid = True

        generated_md_text, generated_md_error = _read_text_or_error(generated_md_path)
        if generated_md_error is not None:
            stale_files.append(resolved_md)
            reasons.append(
                f"{resolved_md}: generated markdown invalid ({generated_md_error})"
            )
        else:
            generated_md_reasons = _validate_markdown_text(
                generated_md_text,
                "generated",
            )
            for reason in generated_md_reasons:
                stale_files.append(resolved_md)
                reasons.append(f"{resolved_md}: {reason}")
            if not generated_md_reasons:
                generated_md_valid = True

        if (
            committed_json_valid
            and generated_json_valid
            and committed_json != generated_json
        ):
            stale_files.append(resolved_json)
            reasons.append(f"{resolved_json}: JSON payload mismatch")

        if (
            committed_md_valid
            and generated_md_valid
            and committed_md_text != generated_md_text
        ):
            stale_files.append(resolved_md)
            reasons.append(f"{resolved_md}: Markdown text mismatch")

    unique_files = tuple(dict.fromkeys(stale_files))
    return FreshnessResult(
        fresh=len(unique_files) == 0,
        stale_files=unique_files,
        reasons=tuple(reasons),
    )


def main() -> int:
    """CLI entry point."""
    result = check_performance_evidence_freshness()
    if result.fresh:
        print("Performance evidence artifacts are fresh.")
        return 0

    print("Performance evidence artifacts are stale.")
    print("Changed files:")
    for stale_file in result.stale_files:
        print(f"- {stale_file.as_posix()}")
    print("Reasons:")
    for reason in result.reasons:
        print(f"- {reason}")
    print(f"Regenerate with: {REGENERATE_COMMAND}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
