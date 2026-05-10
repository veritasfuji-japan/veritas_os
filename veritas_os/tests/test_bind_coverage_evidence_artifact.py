"""Tests for bind coverage evidence artifact generation."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.governance.export_bind_coverage_evidence import (
    EFFECT_BEARING_METHODS,
    generate_bind_coverage_evidence,
    write_bind_coverage_evidence,
)


def test_generate_bind_coverage_evidence_status_ok_and_complete() -> None:
    """Evidence should be complete when runtime routes are fully classified."""
    evidence = generate_bind_coverage_evidence()

    assert evidence["schema_version"] == "bind_coverage_evidence.v1"
    assert evidence["status"] == "ok"
    assert evidence["unclassified_routes"] == []
    assert evidence["catalog_registry_mismatch"] == []
    assert evidence["audited_exemption_missing_reason"] == []
    assert evidence["audited_exemption_missing_risk_level"] == []


def test_effect_bearing_routes_are_classified_and_sorted() -> None:
    """All effect-bearing routes must be classified and route order deterministic."""
    evidence = generate_bind_coverage_evidence()
    routes = evidence["routes"]

    assert routes == sorted(routes, key=lambda item: (item["path"], item["method"]))

    missing = [
        f"{row['method']} {row['path']}"
        for row in routes
        if row["method"] in EFFECT_BEARING_METHODS and row["coverage_class"] == "unclassified"
    ]
    assert missing == []


def test_audited_exemptions_and_bind_catalog_consistency() -> None:
    """Audited exemptions and bind-governed metadata should satisfy reviewer checks."""
    evidence = generate_bind_coverage_evidence()

    for row in evidence["audited_exemptions"]:
        assert row["reason"]
        assert row["risk_level"]

    for row in evidence["bind_governed_routes"]:
        assert row["bind_target_metadata_present"] is True


def test_write_bind_coverage_evidence_outputs_json_and_markdown(tmp_path: Path) -> None:
    """Writer should create JSON/MD artifacts with minimal nondeterministic data."""
    json_path = tmp_path / "bind.json"
    markdown_path = tmp_path / "bind.md"

    evidence = write_bind_coverage_evidence(json_path=json_path, markdown_path=markdown_path)

    assert json_path.exists()
    assert markdown_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "bind_coverage_evidence.v1"
    assert "generated_at" in payload

    allowed_top_keys = {
        "schema_version",
        "generated_at",
        "total_runtime_routes",
        "total_effect_bearing_routes",
        "classified_routes",
        "unclassified_routes",
        "bind_governed_routes",
        "audited_exemptions",
        "read_only_routes",
        "non_effect_routes",
        "catalog_bind_targets",
        "registry_bind_governed_targets",
        "catalog_registry_mismatch",
        "audited_exemption_missing_reason",
        "audited_exemption_missing_risk_level",
        "status",
        "routes",
    }
    assert set(payload.keys()) == allowed_top_keys
    assert payload["routes"] == sorted(
        payload["routes"], key=lambda item: (item["path"], item["method"])
    )
    assert evidence["status"] == payload["status"]
