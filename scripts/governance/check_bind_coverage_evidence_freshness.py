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
REGENERATE_COMMAND = "python -m scripts.governance.export_bind_coverage_evidence"


def _normalize_generated_at_for_compare(
    payload: dict[str, Any],
    path: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    """Normalize generated_at for comparison or return a structural drift reason."""

    if "generated_at" not in payload:
        return None, f"{path}: missing generated_at"
    if not isinstance(payload["generated_at"], str) or not payload["generated_at"].strip():
        return None, f"{path}: invalid generated_at"

    normalized = dict(payload)
    normalized["generated_at"] = FIXED_GENERATED_AT
    return normalized, None


def _read_text_or_error(path: Path) -> tuple[str | None, str | None]:
    """Read UTF-8 text or return a compact error marker."""

    try:
        return path.read_text(encoding="utf-8"), None
    except OSError as exc:
        return None, f"{path}: {exc.__class__.__name__}"


def compare_bind_coverage_evidence(
    committed_json: Path,
    committed_md: Path,
    generated_json: Path,
    generated_md: Path,
) -> tuple[list[str], list[str]]:
    """Return stale files and reasons when committed/generated outputs differ."""

    stale_files: list[str] = []
    stale_reasons: list[str] = []
    try:
        committed_json_payload = json.loads(committed_json.read_text(encoding="utf-8"))
        generated_json_payload = json.loads(generated_json.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        stale_files.append(str(committed_json))
        stale_reasons.append(f"{committed_json}: failed to read JSON ({exc.__class__.__name__})")
        committed_json_payload = None
        generated_json_payload = None

    if not isinstance(committed_json_payload, dict):
        stale_files.append(str(committed_json))
        stale_reasons.append(f"{committed_json}: JSON payload must be an object")
        committed_json_payload = None
    if not isinstance(generated_json_payload, dict):
        stale_files.append(str(committed_json))
        stale_reasons.append(f"{committed_json}: failed to generate JSON artifact")
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
            if committed_error:
                stale_reasons.append(committed_error)
            if generated_error:
                stale_reasons.append(
                    f"{committed_json}: {generated_error.split(': ', maxsplit=1)[-1]}"
                )
        elif normalized_committed != normalized_generated:
            stale_files.append(str(committed_json))
            stale_reasons.append(f"{committed_json}: content differs from regenerated artifact")

    committed_md_text, committed_md_error = _read_text_or_error(committed_md)
    generated_md_text, generated_md_error = _read_text_or_error(generated_md)
    if committed_md_error:
        stale_files.append(str(committed_md))
        stale_reasons.append(committed_md_error)
    if generated_md_error:
        stale_files.append(str(committed_md))
        stale_reasons.append(f"{committed_md}: failed to generate markdown artifact")
    if (
        committed_md_text is not None
        and generated_md_text is not None
        and committed_md_text != generated_md_text
    ):
        stale_files.append(str(committed_md))
        stale_reasons.append(f"{committed_md}: content differs from regenerated artifact")
    return sorted(set(stale_files)), sorted(set(stale_reasons))


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
        stale_files, stale_reasons = compare_bind_coverage_evidence(
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
        if stale_reasons:
            print("Reasons:")
            for reason in stale_reasons:
                print(f"- {reason}")
        print(f"Regenerate with: {REGENERATE_COMMAND}")
        return 1

    print("Bind coverage evidence artifacts are fresh.")
    return 0


def main() -> None:
    """CLI entrypoint for freshness checks."""

    raise SystemExit(check_bind_coverage_evidence_freshness())


if __name__ == "__main__":
    main()
