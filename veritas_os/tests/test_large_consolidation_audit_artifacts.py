"""Guards for the non-destructive Large Consolidation Audit foundation."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "artifacts" / "consolidation-audit" / "2026-09-09-baseline.json"
REPORT = ROOT / "artifacts" / "consolidation-audit" / "2026-09-09-report.md"
SCRIPT = ROOT / "scripts" / "audit_large_consolidation.py"
FREEZE = ROOT / "docs" / "architecture" / "controlled-execution-proof-freeze-v1.json"

_ALLOWED = {
    "FROZEN_CORE",
    "ACTIVE_NON_CORE",
    "DUPLICATE_CANDIDATE",
    "DEAD_CANDIDATE",
    "COMPATIBILITY_CANDIDATE",
    "UNCERTAIN",
}


def _baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def _load_audit_module():
    spec = importlib.util.spec_from_file_location("large_consolidation_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_audit_baseline_is_pinned_to_post_freeze_main() -> None:
    data = _baseline()
    assert data["format_version"] == "large-consolidation-audit-baseline/v1"
    assert data["audit_status"] == "INITIAL_INVENTORY"
    assert data["audit_mode"] == "NON_DESTRUCTIVE"
    assert data["source_main"] == "fb5f2bd4cbf6229148efe97586e8c019d2a625c9"
    assert data["frozen_proof_anchor"] == "ada46f2fe324dd3cbcff6be59d56c4f75c4a6bdc"
    assert data["architecture_freeze_pr"] == 2216


def test_audit_findings_use_controlled_classifications_and_never_preapprove_deletion() -> None:
    data = _baseline()
    assert set(data["classification_vocabulary"]) == _ALLOWED
    assert data["findings"]
    for finding in data["findings"]:
        assert finding["classification"] in _ALLOWED
        assert finding["confidence"] in {"LOW", "MEDIUM", "HIGH"}
        assert finding["deletion_permitted"] is False
        assert finding["evidence"]
        assert finding["proposed_action"]


def test_initial_audit_keeps_uncertain_and_frozen_items_out_of_deletion_scope() -> None:
    data = _baseline()
    by_id = {item["id"]: item for item in data["findings"]}
    assert by_id["F-001"]["classification"] == "FROZEN_CORE"
    assert by_id["F-004"]["classification"] == "UNCERTAIN"
    assert by_id["F-005"]["classification"] == "UNCERTAIN"
    assert by_id["F-006"]["classification"] == "UNCERTAIN"
    assert all(by_id[key]["deletion_permitted"] is False for key in by_id)


def test_report_states_audit_before_deletion_and_preserves_frozen_proof() -> None:
    report = REPORT.read_text(encoding="utf-8")
    assert "INITIAL / NON-DESTRUCTIVE" in report
    assert "Audit before deletion. Uncertain means preserve." in report
    assert "FROZEN_CORE" in report
    assert "reproducible-decision-to-effect-e2e" in report
    assert "does **not** claim" in report


def test_inventory_tool_runs_and_includes_frozen_core() -> None:
    module = _load_audit_module()
    inventory = module.build_inventory()

    assert inventory["format_version"] == "large-consolidation-audit-inventory/v1"
    assert inventory["mode"] == "NON_DESTRUCTIVE"
    assert set(inventory["classifications"]) == _ALLOWED
    assert inventory["totals"]["python_files"] >= 1128
    assert inventory["totals"]["runtime_python_files"] >= 432
    assert inventory["totals"]["test_python_files"] >= 471

    frozen_manifest = json.loads(FREEZE.read_text(encoding="utf-8"))
    protected = {item["path"] for item in inventory["frozen_core"]}
    assert set(frozen_manifest["required_files"]) == protected

    families = inventory["candidate_families"]
    assert families["plan8_to_plan17_tests"]["classification"] == "DUPLICATE_CANDIDATE"
    assert families["canonical_promotion_live_adapter_dry_run"]["classification"] == "UNCERTAIN"
    assert families["live_adapter_dry_run"]["classification"] == "UNCERTAIN"
    assert families["trustlog_surfaces"]["classification"] == "UNCERTAIN"


def test_audit_foundation_changes_no_runtime_or_migration_contracts() -> None:
    baseline = _baseline()
    metrics = baseline["repository_metrics"]
    assert metrics == {
        "files": 2220,
        "python_files": 1128,
        "runtime_python_files": 432,
        "test_python_files": 471,
        "scripts_python_files": 87,
        "workflows": 15,
        "docs": 568,
    }
