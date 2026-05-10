from __future__ import annotations

import json

from scripts.performance.check_performance_evidence_freshness import (
    FIXED_GENERATED_AT,
    REGENERATE_COMMAND,
    _validate_markdown_structure,
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


def test_freshness_missing_invalid_nondict_json(tmp_path) -> None:
    missing_json = tmp_path / "missing.json"
    md_path = tmp_path / "ok.md"
    md_path.write_text("# Performance Evidence Artifact\n", encoding="utf-8")
    assert check_performance_evidence_freshness(missing_json, md_path) == 1

    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{bad", encoding="utf-8")
    assert check_performance_evidence_freshness(invalid_json, md_path) == 1

    nondict_json = tmp_path / "nondict.json"
    nondict_json.write_text("[]\n", encoding="utf-8")
    assert check_performance_evidence_freshness(nondict_json, md_path) == 1


def test_freshness_missing_markdown(tmp_path) -> None:
    json_path = tmp_path / "performance-evidence.latest.json"
    md_path = tmp_path / "missing.md"
    write_performance_evidence(
        json_path,
        tmp_path / "tmp.md",
        generated_at=FIXED_GENERATED_AT,
        sample_count=3,
        warmup_count=0,
        deterministic_fixture=True,
    )
    assert check_performance_evidence_freshness(json_path, md_path) == 1


def test_markdown_numeric_change_does_not_fail_structure() -> None:
    text = """# Performance Evidence Artifact
## Scope
## Summary table
## Metrics table
| Name | Category | p50 ms | p95 ms | p99 ms | Status | Notes |
| --- | --- | ---: | ---: | ---: | --- | --- |
| api.health.get | api_route_smoke | 999.0 | 999.0 | 999.0 | ok | x |
## Interpretation boundaries
- This artifact is CI-safe local evidence, not a production SLA.
## How to regenerate
python -m scripts.performance.export_performance_evidence
"""
    reasons = _validate_markdown_structure(text, ["api.health.get"])
    assert reasons == []


def test_markdown_missing_requirements_fail() -> None:
    reasons = _validate_markdown_structure("# Performance Evidence Artifact\n", ["api.health.get"])
    assert reasons


def test_regenerate_command_constant() -> None:
    assert REGENERATE_COMMAND == "python -m scripts.performance.export_performance_evidence"
