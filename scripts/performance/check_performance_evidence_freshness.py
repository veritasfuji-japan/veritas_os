"""Check performance evidence artifacts freshness in deterministic fixture mode."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from scripts.performance.export_performance_evidence import OUTPUT_JSON, OUTPUT_MD, write_performance_evidence

FIXED_GENERATED_AT = "1970-01-01T00:00:00+00:00"
REGENERATE_COMMAND = "python -m scripts.performance.export_performance_evidence"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compare_performance_evidence(committed_json: Path, committed_md: Path, generated_json: Path, generated_md: Path) -> tuple[list[str], list[str]]:
    stale_files: list[str] = []
    reasons: list[str] = []
    committed = _load_json(committed_json)
    generated = _load_json(generated_json)

    required = {"schema_version", "generated_at", "measurement_mode", "metrics", "status", "interpretation_boundaries"}
    for field in sorted(required):
        if field not in committed:
            stale_files.append(str(committed_json))
            reasons.append(f"{committed_json}: missing required field {field}")

    if committed.get("schema_version") != "performance_evidence.v1":
        stale_files.append(str(committed_json))
        reasons.append(f"{committed_json}: stale schema_version")

    if committed.get("measurement_mode") != generated.get("measurement_mode"):
        stale_files.append(str(committed_json))
        reasons.append(f"{committed_json}: measurement_mode differs from deterministic fixture")

    committed_names = [m.get("name") for m in committed.get("metrics", []) if isinstance(m, dict)]
    generated_names = [m.get("name") for m in generated.get("metrics", []) if isinstance(m, dict)]
    if committed_names != generated_names:
        stale_files.append(str(committed_json))
        reasons.append(f"{committed_json}: metric names/order differ")

    committed_md_text = committed_md.read_text(encoding="utf-8")
    generated_md_text = generated_md.read_text(encoding="utf-8")
    for needle in ["# Performance Evidence Artifact", "## Summary table", "## Metrics table", "## Interpretation boundaries"]:
        if needle not in committed_md_text:
            stale_files.append(str(committed_md))
            reasons.append(f"{committed_md}: missing section {needle}")
    if committed_md_text != generated_md_text:
        stale_files.append(str(committed_md))
        reasons.append(f"{committed_md}: content differs from regenerated artifact")

    return sorted(set(stale_files)), sorted(set(reasons))


def check_performance_evidence_freshness(committed_json: Path = OUTPUT_JSON, committed_md: Path = OUTPUT_MD) -> int:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        generated_json = root / committed_json.name
        generated_md = root / committed_md.name
        write_performance_evidence(generated_json, generated_md, generated_at=FIXED_GENERATED_AT, sample_count=3, warmup_count=0, deterministic_fixture=True)
        stale_files, reasons = compare_performance_evidence(committed_json, committed_md, generated_json, generated_md)
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
