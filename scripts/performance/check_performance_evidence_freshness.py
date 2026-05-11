"""Check freshness of committed performance evidence artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
import json

from scripts.performance.export_performance_evidence import OUTPUT_JSON, OUTPUT_MD
from scripts.performance.export_performance_evidence import write_performance_evidence

REGENERATE_COMMAND = "python -m scripts.performance.export_performance_evidence"
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

    if payload.get("schema_version") != "performance_evidence.v1":
        reasons.append(f"{label} schema_version must be performance_evidence.v1")
    if not isinstance(payload.get("metrics"), list):
        reasons.append(f"{label} metrics must be a list")
    if not isinstance(payload.get("notes"), list):
        reasons.append(f"{label} notes must be a list")
    if not isinstance(payload.get("sample_count"), int):
        reasons.append(f"{label} sample_count must be an int")
    if not isinstance(payload.get("warmup_count"), int):
        reasons.append(f"{label} warmup_count must be an int")
    return reasons


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
    resolved_json = committed_json_path if committed_json_path is not None else OUTPUT_JSON
    resolved_md = (
        committed_markdown_path if committed_markdown_path is not None else OUTPUT_MD
    )

    stale_files: list[Path] = []
    reasons: list[str] = []

    committed_json, committed_json_error = _load_json_or_error(resolved_json)
    if committed_json_error is not None:
        stale_files.append(resolved_json)
        reasons.append(f"{resolved_json}: failed to load JSON ({committed_json_error})")
    else:
        for reason in _validate_json_payload(committed_json, "committed"):
            stale_files.append(resolved_json)
            reasons.append(f"{resolved_json}: {reason}")

    committed_md_text, committed_md_error = _read_text_or_error(resolved_md)
    if committed_md_error is not None:
        stale_files.append(resolved_md)
        reasons.append(f"{resolved_md}: failed to read markdown ({committed_md_error})")
    else:
        for reason in _validate_markdown_text(committed_md_text, "committed"):
            stale_files.append(resolved_md)
            reasons.append(f"{resolved_md}: {reason}")

    with TemporaryDirectory() as tmp_dir:
        generated_json_path = Path(tmp_dir) / "performance-evidence.latest.json"
        generated_md_path = Path(tmp_dir) / "performance-evidence.latest.md"

        try:
            write_performance_evidence(
                json_path=generated_json_path,
                markdown_path=generated_md_path,
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
            for reason in _validate_json_payload(generated_json, "generated"):
                stale_files.append(resolved_json)
                reasons.append(f"{resolved_json}: {reason}")

        generated_md_text, generated_md_error = _read_text_or_error(generated_md_path)
        if generated_md_error is not None:
            stale_files.append(resolved_md)
            reasons.append(
                f"{resolved_md}: generated markdown invalid ({generated_md_error})"
            )
        else:
            for reason in _validate_markdown_text(generated_md_text, "generated"):
                stale_files.append(resolved_md)
                reasons.append(f"{resolved_md}: {reason}")

        if committed_json is not None and generated_json is not None:
            if committed_json != generated_json:
                stale_files.append(resolved_json)
                reasons.append(f"{resolved_json}: JSON payload mismatch")

        if committed_md_text is not None and generated_md_text is not None:
            if committed_md_text != generated_md_text:
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
