"""Guards for Large Consolidation Audit Phase 2 evidence."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "audit_large_consolidation_phase2.py"
BASELINE = (
    ROOT
    / "artifacts"
    / "consolidation-audit"
    / "2026-09-10-phase2-baseline.json"
)
REPORT = (
    ROOT
    / "artifacts"
    / "consolidation-audit"
    / "2026-09-10-phase2-report.md"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "large_consolidation_audit_phase2",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def test_phase2_baseline_is_non_destructive_and_pinned() -> None:
    data = _baseline()
    assert data["format_version"] == "large-consolidation-audit-phase2-baseline/v1"
    assert data["status"] == "PHASE2_EVIDENCE_MATRICES"
    assert data["mode"] == "NON_DESTRUCTIVE"
    assert data["source_main"] == "52752dbf766d9994f2f3267af47e904748d347a6"
    assert data["frozen_proof_anchor"] == "ada46f2fe324dd3cbcff6be59d56c4f75c4a6bdc"
    assert data["phase1_pr"] == 2217
    assert all(
        finding["deletion_permitted"] is False
        for finding in data["findings"]
    )


def test_phase2_generator_protects_frozen_transitive_dependencies() -> None:
    module = _load_module()
    data = module.build_phase2()
    closure = data["frozen_dependency_closure"]

    assert closure["runtime_closure_count"] >= closure["runtime_seed_count"]
    assert closure["proof_closure_count"] >= closure["proof_seed_count"]

    for required in (
        "veritas_os/policy/native_bind_authorization.py",
        "veritas_os/policy/native_bind_authorization_consumption.py",
        "veritas_os/policy/sandbox_action_binding.py",
        "veritas_os/policy/sandbox_bind_execution.py",
        "veritas_os/policy/sandbox_reconciliation.py",
        "veritas_os/policy/sandbox_receipt_outcome.py",
        "veritas_os/policy/sandbox_recovery.py",
    ):
        assert required in closure["runtime_closure"]

    assert (
        "veritas_os/tests/test_decision_to_effect_controlled_e2e.py"
        in closure["proof_closure"]
    )
    assert "Static Python import closure only" in closure["limitation"]


def test_phase2_legacy_sha256_candidate_has_no_supported_consumer() -> None:
    module = _load_module()
    data = module.build_phase2()
    candidate = data["legacy_policy_sha256"]

    assert candidate["classification"] == "DEAD_CANDIDATE"
    assert candidate["status"] == "REMOVED"
    assert candidate["supported_runtime_script_workflow_consumers"] == []
    assert candidate["deletion_permitted"] is False


def test_phase2_trustlog_role_matrix_prevents_false_duplicate_conclusion() -> None:
    module = _load_module()
    data = module.build_phase2()
    roles = {row["symbol"]: row for row in data["trustlog_role_matrix"]}

    assert roles["verify_trust_log"]["classification"] == "ACTIVE_NON_CORE"
    assert "full encrypted" in roles["verify_trust_log"]["role"]
    assert roles["verify_trustlogs"]["classification"] == "ACTIVE_NON_CORE"
    assert "full + witness" in roles["verify_trustlogs"]["role"]
    assert roles["verify_entries"]["classification"] == "COMPATIBILITY_CANDIDATE"
    assert roles["compute_hash"]["classification"] == "COMPATIBILITY_CANDIDATE"
    assert all(row["deletion_permitted"] is False for row in roles.values())


def test_phase2_plan_overlap_matrix_records_resolved_duplicates_and_preserved_variants() -> None:
    module = _load_module()
    data = module.build_phase2()
    matrix = data["plan8_plan17_matrix"]

    assert len(matrix["files"]) == 10
    overlaps = {row["behavior"]: row for row in matrix["known_overlap_groups"]}

    replay = overlaps["replay_decision_query_param_failure_defaults_mock_true"]
    assert replay["classification"] == "ACTIVE_NON_CORE"
    assert replay["resolution"] == "CONSOLIDATED"
    assert replay["tests"] == [
        "test_routes_replay_decision_query_param_error_defaults_to_mock_true"
    ]
    assert len(replay["consolidated_from"]) == 2

    rollout = overlaps["unknown_rollout_strategy_safe_full"]
    assert rollout["classification"] == "ACTIVE_NON_CORE"
    assert rollout["resolution"] == "CONSOLIDATED"
    assert rollout["tests"] == [
        "test_pipeline_rollout_unknown_strategy_falls_back_to_safe_full"
    ]

    pipeline = overlaps["pipeline_unavailable_lazy_state_reset"]
    assert pipeline["resolution"] == "PRESERVE_DISTINCT_VARIANTS"
    assert len(pipeline["tests"]) == 2

    scheduler = overlaps["nonce_cleanup_scheduler_failure_handling"]
    assert (
        scheduler["resolution"]
        == "PARTIALLY_CONSOLIDATED_PRESERVE_DISTINCT_STATES"
    )
    assert len(scheduler["tests"]) == 2
    assert scheduler["consolidated_from"] == [
        "test_schedule_nonce_cleanup_reschedules_even_after_cleanup_error"
    ]

    nonce = overlaps["effective_nonce_max_override_fallbacks"]
    assert nonce["classification"] == "ACTIVE_NON_CORE"
    assert nonce["resolution"] == "PRESERVE_DISTINCT_BRANCHES"
    assert len(nonce["tests"]) == 3

def test_consolidation_002_removed_only_resolved_duplicate_test_names() -> None:
    module = _load_module()
    data = module.build_phase2()
    present = {
        test_name
        for row in data["plan8_plan17_matrix"]["files"]
        for test_name in row["tests"]
    }

    for removed in (
        "test_replay_decision_endpoint_query_params_error_defaults_true",
        "test_replay_decision_endpoint_defaults_mock_true_on_query_error",
        "test_rollout_enforcement_unknown_strategy_defaults_to_safe_full",
        "test_schedule_nonce_cleanup_reschedules_even_after_cleanup_error",
    ):
        assert removed not in present

    for retained in (
        "test_routes_replay_decision_query_param_error_defaults_to_mock_true",
        "test_pipeline_rollout_unknown_strategy_falls_back_to_safe_full",
        "test_decide_pipeline_unavailable_resets_lazy_state",
        "test_decide_pipeline_unavailable_resets_lazy_state_when_mutated",
        "test_schedule_nonce_cleanup_logs_and_stops_when_timer_cleared",
        "test_rate_nonce_scheduler_logs_when_cleanup_raises",
        "test_effective_nonce_max_import_error_uses_default",
        "test_effective_nonce_max_uses_default_when_server_override_is_non_int",
        "test_effective_nonce_max_prefers_server_integer_override",
    ):
        assert retained in present


def test_phase2_dry_run_matrix_records_parallelism_without_authorizing_collapse() -> None:
    module = _load_module()
    data = module.build_phase2()
    matrix = data["dry_run_family_matrix"]

    assert len(matrix["paired_suffixes"]) == 11
    assert matrix["canonical_only"] == [
        "bind_context_hash_derivation",
        "final_credential_scope_recheck",
        "final_endpoint_identity_recheck",
        "fresh_verified_source_gate",
        "runtime_risk_review",
    ]
    assert matrix["live_only"] == ["human_approval_requirement_satisfaction"]
    assert matrix["classification"] == "UNCERTAIN"
    assert matrix["deletion_permitted"] is False


def test_phase2_report_preserves_separate_human_review_for_deletion() -> None:
    report = REPORT.read_text(encoding="utf-8")
    assert "PHASE 2 / NON-DESTRUCTIVE" in report
    assert "DEAD_CANDIDATE / HIGH confidence" in report
    assert "does **not** authorize" in report
    assert "separate Human CEO review point" in report
    assert "TrustLog verifier unification" in report
    assert "dry-run family collapse" in report
