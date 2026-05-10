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


def _load_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Load JSON object from path, returning a user-safe error reason on failure."""

    try:
        raw_payload = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"missing or unreadable file: {exc}"

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc.msg}"

    if not isinstance(payload, dict):
        return None, "JSON payload is not an object"
    return payload, None


def compare_bind_coverage_evidence(
    committed_json: Path,
    committed_md: Path,
    generated_json: Path,
    generated_md: Path,
) -> list[str]:
    """Return stale artifact filenames when committed and generated outputs differ."""

    stale_files: list[str] = []
    committed_json_payload, committed_json_error = _load_json_object(committed_json)
    generated_json_payload, generated_json_error = _load_json_object(generated_json)
    if committed_json_error:
        print(f"- {committed_json}: {committed_json_error}")
        stale_files.append(str(committed_json))
    if generated_json_error:
        print(f"- {generated_json}: {generated_json_error}")
        stale_files.append(str(committed_json))

    if committed_json_payload and generated_json_payload:
        committed_json_payload["generated_at"] = FIXED_GENERATED_AT
        generated_json_payload["generated_at"] = FIXED_GENERATED_AT
        if committed_json_payload != generated_json_payload:
            stale_files.append(str(committed_json))

    try:
        committed_md_payload = committed_md.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"- {committed_md}: missing or unreadable file: {exc}")
        stale_files.append(str(committed_md))
        committed_md_payload = None

    try:
        generated_md_payload = generated_md.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"- {generated_md}: missing or unreadable file: {exc}")
        stale_files.append(str(committed_md))
        generated_md_payload = None

    if (
        committed_md_payload is not None
        and generated_md_payload is not None
        and committed_md_payload != generated_md_payload
    ):
        stale_files.append(str(committed_md))

    stale_files = sorted(set(stale_files))
    return stale_files


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
