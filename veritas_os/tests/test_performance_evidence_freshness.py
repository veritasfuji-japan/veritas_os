from __future__ import annotations

import json

from scripts.performance.check_performance_evidence_freshness import (
    FIXED_GENERATED_AT,
    REGENERATE_COMMAND,
    check_performance_evidence_freshness,
)
from scripts.performance.export_performance_evidence import write_performance_evidence


def test_freshness_ok(tmp_path) -> None:
    json_path = tmp_path / "performance-evidence.latest.json"
    md_path = tmp_path / "performance-evidence.latest.md"
    write_performance_evidence(
        json_path,
        md_path,
        generated_at=FIXED_GENERATED_AT,
        sample_count=3,
        warmup_count=0,
        deterministic_fixture=True,
    )
    assert check_performance_evidence_freshness(json_path, md_path) == 0


def test_freshness_fails_on_stale_schema(tmp_path) -> None:
    json_path = tmp_path / "performance-evidence.latest.json"
    md_path = tmp_path / "performance-evidence.latest.md"
    write_performance_evidence(
        json_path,
        md_path,
        generated_at=FIXED_GENERATED_AT,
        sample_count=3,
        warmup_count=0,
        deterministic_fixture=True,
    )
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload["schema_version"] = "stale"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert check_performance_evidence_freshness(json_path, md_path) == 1


def test_regenerate_command_constant() -> None:
    assert REGENERATE_COMMAND == "python -m scripts.performance.export_performance_evidence"
