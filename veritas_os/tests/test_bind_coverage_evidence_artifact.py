"""Tests for bind coverage evidence artifact generation."""

from __future__ import annotations

import json
from pathlib import Path

import scripts.governance.export_bind_coverage_evidence as evidence_module
from scripts.governance.export_bind_coverage_evidence import (
    EFFECT_BEARING_METHODS,
    OUTPUT_JSON,
    OUTPUT_MD,
    REPO_ROOT,
    generate_bind_coverage_evidence,
    write_bind_coverage_evidence,
)


def test_generate_bind_coverage_evidence_status_ok_and_complete() -> None:
    """Evidence should be complete when runtime routes are fully classified."""
    evidence = generate_bind_coverage_evidence()

    assert evidence["schema_version"] == "bind_coverage_evidence.v1"
    assert evidence["registry_errors"] == []
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
        if row["method"] in EFFECT_BEARING_METHODS
        and row["coverage_class"] == "unclassified"
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

    evidence = write_bind_coverage_evidence(
        json_path=json_path,
        markdown_path=markdown_path,
    )

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
        "registry_errors",
        "status",
        "routes",
    }
    assert set(payload.keys()) == allowed_top_keys
    assert payload["routes"] == sorted(
        payload["routes"], key=lambda item: (item["path"], item["method"])
    )
    assert evidence["status"] == payload["status"]


def test_default_output_paths_are_repo_root_anchored() -> None:
    """Default output paths should always anchor to repository root."""
    expected_root = Path(__file__).resolve().parents[2]

    assert REPO_ROOT == expected_root
    assert OUTPUT_JSON == expected_root / "docs/en/validation/bind-coverage-evidence.latest.json"
    assert OUTPUT_MD == expected_root / "docs/en/validation/bind-coverage-evidence.latest.md"


def test_default_output_paths_do_not_depend_on_cwd(monkeypatch, tmp_path: Path) -> None:
    """Changing CWD should not alter default artifact destination paths."""
    monkeypatch.chdir(tmp_path)

    assert OUTPUT_JSON.is_absolute()
    assert OUTPUT_MD.is_absolute()
    assert OUTPUT_JSON.parent == REPO_ROOT / "docs/en/validation"
    assert OUTPUT_MD.parent == REPO_ROOT / "docs/en/validation"


def test_non_catalog_registry_error_forces_failed_status(monkeypatch) -> None:
    """Any registry error should propagate and fail status."""
    monkeypatch.setattr(
        evidence_module,
        "validate_bind_coverage_registry",
        lambda: ["duplicate bind coverage entry: POST /x"],
    )

    evidence = evidence_module.generate_bind_coverage_evidence()
    markdown = evidence_module.render_bind_coverage_markdown(evidence)

    assert evidence["registry_errors"] == ["duplicate bind coverage entry: POST /x"]
    assert evidence["status"] == "failed"
    assert "Registry validation errors" in markdown
    assert "duplicate bind coverage entry: POST /x" in markdown


def test_catalog_registry_mismatch_is_in_subset_and_fails_status(monkeypatch) -> None:
    """Catalog mismatch errors should appear in both lists and fail status."""
    mismatch_error = "bind_governed route missing from bind target catalog: /x"
    monkeypatch.setattr(
        evidence_module,
        "validate_bind_coverage_registry",
        lambda: [mismatch_error],
    )

    evidence = evidence_module.generate_bind_coverage_evidence()

    assert mismatch_error in evidence["registry_errors"]
    assert mismatch_error in evidence["catalog_registry_mismatch"]
    assert evidence["status"] == "failed"


def test_effect_route_unclassified_forces_failed_status(monkeypatch) -> None:
    """Unclassified effect-bearing routes must fail status."""
    original_classify = evidence_module.classify_bind_coverage

    def _fake_classify(path: str, method: str):
        if method in EFFECT_BEARING_METHODS:
            return None
        return original_classify(path, method)

    monkeypatch.setattr(evidence_module, "classify_bind_coverage", _fake_classify)

    evidence = evidence_module.generate_bind_coverage_evidence()

    assert evidence["unclassified_routes"]
    assert evidence["status"] == "failed"


def test_deterministic_generated_at_produces_stable_payloads() -> None:
    """A fixed generated_at must produce stable JSON and markdown outputs."""
    fixed_generated_at = "1970-01-01T00:00:00+00:00"

    first = evidence_module.generate_bind_coverage_evidence(generated_at=fixed_generated_at)
    second = evidence_module.generate_bind_coverage_evidence(generated_at=fixed_generated_at)

    assert first == second
    assert first["generated_at"] == fixed_generated_at

    first_markdown = evidence_module.render_bind_coverage_markdown(first)
    second_markdown = evidence_module.render_bind_coverage_markdown(second)
    assert first_markdown == second_markdown
