"""Guards for Large Consolidation Audit Phase 2 evidence."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

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


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True,
    ).strip()


@pytest.fixture
def audit_checkout(tmp_path, monkeypatch):
    """Use real Git metadata and a minimal, independently editable audit input."""
    root = tmp_path / "checkout"
    root.mkdir()
    _git(root, "init", "-q")
    freeze = root / "freeze.json"
    freeze.write_text('{"required_files": []}\n', encoding="utf-8")
    (root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "-c", "user.name=Audit Test", "-c", "user.email=audit@example.invalid",
         "-c", "commit.gpgsign=false", "commit", "-qm", "initial")
    module = _load_module()
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "FREEZE", freeze)
    # Neither process CWD nor CI metadata is the authority for the checkout.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "0" * 40)
    return module, root


def test_generated_provenance_identifies_actual_detached_checkout(audit_checkout) -> None:
    module, root = audit_checkout
    _git(root, "checkout", "--detach", "-q")
    data = module.build_phase2()
    observed = data["observed_checkout"]
    assert observed == {
        "tested_sha": _git(root, "rev-parse", "HEAD"),
        "head_tree_sha": _git(root, "rev-parse", "HEAD^{tree}"),
        "worktree_dirty": False,
    }
    assert data["source_main"] == _baseline()["source_main"]
    assert observed["tested_sha"] != data["source_main"]


@pytest.mark.parametrize("state", ["unstaged", "staged", "deleted", "untracked"])
def test_generated_provenance_marks_local_changes(audit_checkout, state) -> None:
    module, root = audit_checkout
    head, tree = _git(root, "rev-parse", "HEAD"), _git(root, "rev-parse", "HEAD^{tree}")
    if state == "untracked":
        (root / "new.py").write_text("# local input\n", encoding="utf-8")
    elif state == "deleted":
        (root / ".gitignore").unlink()
    else:
        (root / ".gitignore").write_text("ignored.txt\nother.txt\n", encoding="utf-8")
        if state == "staged":
            _git(root, "add", ".gitignore")
    assert module.build_phase2()["observed_checkout"] == {
        "tested_sha": head, "head_tree_sha": tree, "worktree_dirty": True,
    }


def test_provenance_updates_after_real_commit(audit_checkout) -> None:
    module, root = audit_checkout
    before = module.build_phase2()["observed_checkout"]
    (root / "new.py").write_text("# committed input\n", encoding="utf-8")
    _git(root, "add", "new.py")
    _git(root, "-c", "user.name=Audit Test", "-c", "user.email=audit@example.invalid",
         "-c", "commit.gpgsign=false", "commit", "-qm", "next")
    after = module.build_phase2()["observed_checkout"]
    assert after["tested_sha"] == _git(root, "rev-parse", "HEAD")
    assert after["head_tree_sha"] == _git(root, "rev-parse", "HEAD^{tree}")
    assert after["tested_sha"] != before["tested_sha"]
    assert after["head_tree_sha"] != before["head_tree_sha"]
    assert after["worktree_dirty"] is False


def test_ignored_files_are_not_claimed_as_git_dirtiness(audit_checkout) -> None:
    module, root = audit_checkout
    (root / "ignored.txt").write_text("ignored audit input\n", encoding="utf-8")
    assert module.build_phase2()["observed_checkout"]["worktree_dirty"] is False


@pytest.mark.parametrize("state", ["no_repository", "nested_directory", "no_commit", "no_git"])
def test_missing_checkout_identity_cannot_generate_report(audit_checkout, tmp_path, monkeypatch, state) -> None:
    module, root = audit_checkout
    if state == "no_git":
        monkeypatch.setenv("PATH", "")
    else:
        root = root / "nested" if state == "nested_directory" else tmp_path / "unidentified"
        root.mkdir()
        if state == "no_commit":
            _git(root, "init", "-q")
        monkeypatch.setattr(module, "ROOT", root)
    with pytest.raises(RuntimeError, match="checkout provenance"):
        module.build_phase2()


def test_checkout_change_during_scan_cannot_generate_report(audit_checkout, monkeypatch) -> None:
    module, root = audit_checkout
    original = module._build_python_graph

    def changed_graph():
        (root / "new.py").write_text("# created during scan\n", encoding="utf-8")
        return original()

    monkeypatch.setattr(module, "_build_python_graph", changed_graph)
    with pytest.raises(RuntimeError, match="checkout provenance changed"):
        module.build_phase2()


def test_cli_records_pre_output_checkout_state(audit_checkout) -> None:
    _, root = audit_checkout
    script = root / "scripts" / SCRIPT.name
    script.parent.mkdir()
    shutil.copyfile(SCRIPT, script)
    freeze = root / "docs/architecture/controlled-execution-proof-freeze-v1.json"
    freeze.parent.mkdir(parents=True)
    freeze.write_text('{"required_files": []}\n', encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "-c", "user.name=Audit Test", "-c", "user.email=audit@example.invalid",
         "-c", "commit.gpgsign=false", "commit", "-qm", "generator")
    output = root / "report.json"
    subprocess.run([sys.executable, str(script), "--output", str(output)],
                   check=True, capture_output=True, text=True, timeout=30)
    first = json.loads(output.read_text(encoding="utf-8"))
    assert first["observed_checkout"]["worktree_dirty"] is False
    assert _git(root, "status", "--porcelain", "--untracked-files=all")
    subprocess.run([sys.executable, str(script), "--output", str(output)],
                   check=True, capture_output=True, text=True, timeout=30)
    second = json.loads(output.read_text(encoding="utf-8"))
    assert second["observed_checkout"]["worktree_dirty"] is True
