"""Check performance evidence artifacts freshness in deterministic fixture mode."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.performance.export_performance_evidence import (
    OUTPUT_JSON,
    OUTPUT_MD,
    write_performance_evidence,
)

FIXED_GENERATED_AT = "1970-01-01T00:00:00+00:00"
REGENERATE_COMMAND = "python -m scripts.performance.export_performance_evidence"


def _read_text_or_error(path: Path) -> tuple[str | None, str | None]:
    """Read UTF-8 text or return compact error class name."""
    try:
        return path.read_text(encoding="utf-8"), None
    except OSError as exc:
        return None, exc.__class__.__name__


def _load_json_or_error(path: Path) -> tuple[Any | None, str | None]:
    """Load JSON payload or return compact error class name."""
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, ValueError) as exc:
        return None, exc.__class__.__name__


def _is_iso8601_timestamp(value: Any) -> bool:
    """Return True when value is a non-empty ISO-8601 timestamp string."""
    if not isinstance(value, str):
        return False
    normalized = value.strip()
    if not normalized:
        return False
    try:
        datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def compare_performance_evidence(
    committed_json: Path,
    committed_md: Path,
    generated_json: Path,
    generated_md: Path,
) -> tuple[list[str], list[str]]:
    stale_files: list[str] = []
    reasons: list[str] = []
    committed, committed_error = _load_json_or_error(committed_json)
    generated, generated_error = _load_json_or_error(generated_json)

    if committed_error:
        stale_files.append(str(committed_json))
        reasons.append(f"{committed_json}: failed to read JSON ({committed_error})")
    if generated_error:
        stale_files.append(str(committed_json))
        reasons.append(
            f"{committed_json}: failed to generate JSON artifact ({generated_error})"
        )

    if committed_error is None and not isinstance(committed, dict):
        stale_files.append(str(committed_json))
        reasons.append(f"{committed_json}: JSON payload must be an object")
        committed = None
    if generated_error is None and not isinstance(generated, dict):
        stale_files.append(str(committed_json))
        reasons.append(
            f"{committed_json}: failed to generate JSON artifact "
            "(JSON payload must be an object)"
        )
        generated = None

    required = {
        "schema_version",
        "generated_at",
        "measurement_mode",
        "metrics",
        "status",
        "interpretation_boundaries",
    }
    if isinstance(committed, dict):
        for field in sorted(required):
            if field not in committed:
                stale_files.append(str(committed_json))
                reasons.append(f"{committed_json}: missing required field {field}")
    if isinstance(committed, dict) and isinstance(generated, dict):
        if committed.get("schema_version") != "performance_evidence.v1":
            stale_files.append(str(committed_json))
            reasons.append(f"{committed_json}: stale schema_version")
        if generated.get("schema_version") != "performance_evidence.v1":
            stale_files.append(str(committed_json))
            reasons.append(f"{committed_json}: generated stale schema_version")
        if committed.get("schema_version") != generated.get("schema_version"):
            stale_files.append(str(committed_json))
            reasons.append(f"{committed_json}: generated schema_version mismatch")
        if "generated_at" not in committed:
            stale_files.append(str(committed_json))
            reasons.append(f"{committed_json}: missing generated_at")
        elif not _is_iso8601_timestamp(committed.get("generated_at")):
            stale_files.append(str(committed_json))
            reasons.append(f"{committed_json}: invalid generated_at")
        if "generated_at" not in generated:
            stale_files.append(str(committed_json))
            reasons.append(f"{committed_json}: generated artifact missing generated_at")
        elif not _is_iso8601_timestamp(generated.get("generated_at")):
            stale_files.append(str(committed_json))
            reasons.append(f"{committed_json}: generated artifact invalid generated_at")
        if committed.get("measurement_mode") != generated.get("measurement_mode"):
            stale_files.append(str(committed_json))
            reasons.append(
                f"{committed_json}: measurement_mode differs from deterministic fixture"
            )
        committed_names = [
            m.get("name")
            for m in committed.get("metrics", [])
            if isinstance(m, dict)
        ]
        generated_names = [
            m.get("name")
            for m in generated.get("metrics", [])
            if isinstance(m, dict)
        ]
        if committed_names != generated_names:
            stale_files.append(str(committed_json))
            reasons.append(f"{committed_json}: metric names/order differ")

    committed_md_text, committed_md_error = _read_text_or_error(committed_md)
    generated_md_text, generated_md_error = _read_text_or_error(generated_md)
    if committed_md_error:
        stale_files.append(str(committed_md))
        reasons.append(f"{committed_md}: failed to read markdown ({committed_md_error})")
    if generated_md_error:
        stale_files.append(str(committed_md))
        reasons.append(
            f"{committed_md}: failed to generate markdown artifact ({generated_md_error})"
        )
    if committed_md_text is not None:
        for needle in [
            "# Performance Evidence Artifact",
            "## Summary table",
            "## Metrics table",
            "## Interpretation boundaries",
        ]:
            if needle not in committed_md_text:
                stale_files.append(str(committed_md))
                reasons.append(f"{committed_md}: missing section {needle}")
    if (
        committed_md_text is not None
        and generated_md_text is not None
        and committed_md_text != generated_md_text
    ):
        stale_files.append(str(committed_md))
        reasons.append(f"{committed_md}: content differs from regenerated artifact")

    return sorted(set(stale_files)), sorted(set(reasons))


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
        stale_files, reasons = compare_performance_evidence(
            committed_json,
            committed_md,
            generated_json,
            generated_md,
        )
    if stale_files:
        print("Performance evidence artifacts are stale.")
        for file_path in stale_files:
            print(f"- {file_path}")
        for reason in reasons:
            print(f"- {reason}")
        print(f"Regenerate with: {REGENERATE_COMMAND}")
        return 1
    print("Performance evidence artifacts are fresh.")
    return 0


if __name__ == "__main__":
    raise SystemExit(check_performance_evidence_freshness())
