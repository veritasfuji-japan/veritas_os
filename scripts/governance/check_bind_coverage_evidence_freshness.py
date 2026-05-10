"""Check bind coverage evidence artifacts are fresh against current sources."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from scripts.governance.export_bind_coverage_evidence import (
    OUTPUT_JSON,
    OUTPUT_MD,
    write_bind_coverage_evidence,
)

FIXED_GENERATED_AT = "1970-01-01T00:00:00+00:00"
REGENERATE_COMMAND = "python scripts/governance/export_bind_coverage_evidence.py"


def _normalize_generated_at_for_compare(
    payload: dict[str, Any],
    path: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    """Normalize generated_at for comparison or return a structural drift reason."""

    if "generated_at" not in payload:
        return None, f"{path}: missing generated_at"

    normalized = dict(payload)
    normalized["generated_at"] = FIXED_GENERATED_AT
    return normalized, None


def compare_bind_coverage_evidence(
    committed_json: Path,
    committed_md: Path,
    generated_json: Path,
    generated_md: Path,
) -> list[str]:
    """Return stale artifact filenames when committed and generated outputs differ."""

    stale_files: list[str] = []
    try:
        committed_json_payload = json.loads(committed_json.read_text(encoding="utf-8"))
        generated_json_payload = json.loads(generated_json.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        stale_files.append(str(committed_json))
        committed_json_payload = None
        generated_json_payload = None

    if not isinstance(committed_json_payload, dict):
        stale_files.append(str(committed_json))
        committed_json_payload = None
    if not isinstance(generated_json_payload, dict):
        stale_files.append(str(committed_json))
        generated_json_payload = None

    if committed_json_payload is not None and generated_json_payload is not None:
        normalized_committed, committed_error = _normalize_generated_at_for_compare(
            committed_json_payload,
            committed_json,
        )
        normalized_generated, generated_error = _normalize_generated_at_for_compare(
            generated_json_payload,
            generated_json,
        )
        if committed_error or generated_error:
            stale_files.append(str(committed_json))
        elif normalized_committed != normalized_generated:
            stale_files.append(str(committed_json))

    if committed_md.read_text(encoding="utf-8") != generated_md.read_text(encoding="utf-8"):
        stale_files.append(str(committed_md))
    return sorted(set(stale_files))


def check_bind_coverage_evidence_freshness(
    committed_json: Path = OUTPUT_JSON,
    committed_md: Path = OUTPUT_MD,
) -> int:
    """Return process-compatible status code for bind coverage evidence freshness."""

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        generated_json = tmp_root / committed_json.name
        generated_md = tmp_root / committed_md.name
        write_bind_coverage_evidence(
            json_path=generated_json,
            markdown_path=generated_md,
            generated_at=FIXED_GENERATED_AT,
        )
        stale_files = compare_bind_coverage_evidence(
            committed_json=committed_json,
            committed_md=committed_md,
            generated_json=generated_json,
            generated_md=generated_md,
        )

    if stale_files:
        print("Bind coverage evidence artifacts are stale.")
        print("Changed files:")
        for file_path in stale_files:
            print(f"- {file_path}")
        print(f"Regenerate with: {REGENERATE_COMMAND}")
        return 1

    print("Bind coverage evidence artifacts are fresh.")
    return 0


def main() -> None:
    """CLI entrypoint for freshness checks."""

    raise SystemExit(check_bind_coverage_evidence_freshness())


if __name__ == "__main__":
    main()
